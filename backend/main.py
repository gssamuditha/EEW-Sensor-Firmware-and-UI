import asyncio
import csv
import io
import time
import json
import psutil
import socket
import uuid
import sys
import subprocess
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from database import init_db, get_settings, update_settings
from mseed_writer import mseed_writer
from filters import FILTER_PRESETS
from sensor import sensor_manager, process_historical_data_task, CHANNEL_NAMES, SENSOR_VARIANT, CHANNEL_UNITS
from https_publisher import https_publisher
from concurrent.futures import ProcessPoolExecutor

# Use a ProcessPool to run heavy numpy/scipy operations entirely out-of-process, bypassing the GIL.
# process_pool = ProcessPoolExecutor(max_workers=2)
process_pool = ProcessPoolExecutor(max_workers=2, max_tasks_per_child=50)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    mseed_writer.start()
    
    # Run sensor init in a thread to avoid blocking the asyncio event loop
    # (RealSensor.init_sensor sleeps ~11s, calibrate sleeps ~100s)
    loop = asyncio.get_running_loop()
    await asyncio.to_thread(sensor_manager.start, loop)
    
    # Start HTTPS telemetry / metadata publisher (non-blocking daemon thread)
    https_publisher.start(sensor_manager)
    
    # Background task for miniSEED retention
    from retention import run_retention_task
    retention_task = asyncio.create_task(run_retention_task(3600))
    
    yield
    sensor_manager.stop()
    mseed_writer.stop()
    https_publisher.stop()
    retention_task.cancel()
    process_pool.shutdown(wait=False)

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TargetModel(BaseModel):
    name: str
    ip: str
    port: int
    format: str = 'corrected'  # 'corrected' (m/s²) or 'raw' (demeaned 24-bit ADC counts)

class SettingsModel(BaseModel):
    targets: list[TargetModel]
    latitude: float
    longitude: float
    elevation: float | None = 0.0
    floor_unit: int | None = 0
    total_floors: int | None = 1
    data_forwarding: bool = True
    device_name: str | None = None
    device_id: str | None = None
    owner_name: str | None = None
    owner_email: str | None = None
    calibration_time: int | None = None
    retention_days: int | None = None
    is_configured: bool | None = None

class WifiConnectModel(BaseModel):
    ssid: str
    password: str = ""

class WifiActionModel(BaseModel):
    ssid: str

class WifiToggleModel(BaseModel):
    enabled: bool

class FilterModel(BaseModel):
    low_hz: float
    high_hz: float

    @field_validator('low_hz')
    @classmethod
    def low_hz_positive(cls, v):
        if v < 0.01:
            raise ValueError('low_hz must be >= 0.01')
        return v

    @field_validator('high_hz')
    @classmethod
    def high_hz_valid(cls, v):
        if v > 50.0:
            raise ValueError('high_hz must be <= 50.0')
        return v


# ---------------------------------------------------------------------------
# Wi-Fi Manager helpers
# ---------------------------------------------------------------------------

_cached_ssid = None
_last_ssid_check = 0

def _get_wifi_radio_status():
    """Check if the Wi-Fi radio is currently enabled."""
    if sys.platform == 'win32':
        return True
    try:
        result = subprocess.run(
            ['sudo', '/usr/bin/nmcli', 'radio', 'wifi'],
            capture_output=True, text=True, timeout=2
        )
        return 'enabled' in result.stdout.lower()
    except Exception:
        return True

def _get_active_ssid():
    """Return the SSID of the currently active Wi-Fi connection, or None. Cached for 10 seconds."""
    global _cached_ssid, _last_ssid_check
    if time.time() - _last_ssid_check < 10:
        return _cached_ssid
        
    if sys.platform == 'win32':
        return "Senz Cloud"  # mock for Windows dev
        
    try:
        result = subprocess.run(
            ['sudo', '/usr/bin/nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'],
            capture_output=True, text=True, timeout=2
        )
        for line in result.stdout.split('\n'):
            if line.startswith('yes:'):
                _cached_ssid = line.split('yes:', 1)[1].strip()
                _last_ssid_check = time.time()
                return _cached_ssid
    except Exception:
        pass
        
    _cached_ssid = None
    _last_ssid_check = time.time()
    return None

def _get_saved_networks():
    """Return list of dicts: [{ssid, is_active}, ...]."""
    if sys.platform == 'win32':
        # Mock data for Windows development
        active = "Senz Cloud"
        return [
            {"ssid": "Senz Cloud", "is_active": True},
            {"ssid": "Home Network", "is_active": False},
        ], active
    try:
        active = _get_active_ssid()
        result = subprocess.run(
            ['sudo', '/usr/bin/nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'],
            capture_output=True, text=True, timeout=5
        )
        networks = []
        for line in result.stdout.split('\n'):
            line_lower = line.lower()
            if '802-11-wireless' in line_lower or ':wifi' in line_lower:
                name = line.split(':')[0]
                if name:
                    networks.append({
                        "ssid": name,
                        "is_active": (name == active)
                    })
        return networks, active
    except Exception:
        return [], None

def _delayed_wifi_switch(ssid, password=None):
    """Execute the actual network switch after a delay.
    
    This runs in a background thread so the HTTP response can be sent first.
    The 3-second delay gives the frontend time to receive the 200 OK and
    display the network-switch modal before the Pi drops its current connection.
    """
    time.sleep(3)
    try:
        if password:
            # New network: use 'dev wifi connect' which creates a profile + connects
            subprocess.run(
                ["sudo", "/usr/bin/nmcli", "dev", "wifi", "connect", ssid, "password", password],
                capture_output=True, text=True, timeout=30
            )
        else:
            # Saved network: try 'connection up' first (faster), fallback to 'dev wifi connect'
            result = subprocess.run(
                ["sudo", "/usr/bin/nmcli", "connection", "up", "id", ssid],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                subprocess.run(
                    ["sudo", "/usr/bin/nmcli", "dev", "wifi", "connect", ssid],
                    capture_output=True, text=True, timeout=30
                )
    except Exception:
        pass  # Nothing we can do — the frontend is already disconnected

# ---------------------------------------------------------------------------
# Wi-Fi API endpoints
# ---------------------------------------------------------------------------

@app.get("/api/wifi/networks")
def api_wifi_networks():
    """Return all saved Wi-Fi profiles and flag which one is currently active."""
    wifi_enabled = _get_wifi_radio_status()
    networks, active_ssid = _get_saved_networks()
    return {"networks": networks, "active_ssid": active_ssid, "wifi_enabled": wifi_enabled}

@app.post("/api/wifi/toggle")
def api_wifi_toggle(toggle: WifiToggleModel):
    """Enable or disable the Wi-Fi radio."""
    if sys.platform == 'win32':
        return {"status": "ok", "message": f"Wi-Fi {'enabled' if toggle.enabled else 'disabled'}"}
    
    try:
        subprocess.run(
            ["sudo", "/usr/bin/nmcli", "radio", "wifi", "on" if toggle.enabled else "off"],
            capture_output=True, text=True, timeout=10
        )
        return {"status": "ok", "message": f"Wi-Fi {'enabled' if toggle.enabled else 'disabled'}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/wifi/connect")
def api_wifi_connect(wifi: WifiConnectModel):
    """Save a new Wi-Fi network and initiate connection (with graceful delay)."""
    if not wifi.ssid:
        return {"status": "error", "message": "SSID is required"}
    if not wifi.password:
        return {"status": "error", "message": "Password is required"}
    
    # Respond immediately, then switch in background
    threading.Thread(
        target=_delayed_wifi_switch,
        args=(wifi.ssid, wifi.password),
        daemon=True
    ).start()
    
    return {"status": "ok", "message": f"Connecting to {wifi.ssid}..."}

@app.post("/api/wifi/connect_saved")
def api_wifi_connect_saved(wifi: WifiActionModel):
    """Switch to a previously saved Wi-Fi network (with graceful delay)."""
    if not wifi.ssid:
        return {"status": "error", "message": "SSID is required"}
    
    # Respond immediately, then switch in background
    threading.Thread(
        target=_delayed_wifi_switch,
        args=(wifi.ssid,),
        daemon=True
    ).start()
    
    return {"status": "ok", "message": f"Connecting to {wifi.ssid}..."}

@app.post("/api/wifi/forget")
def api_wifi_forget(wifi: WifiActionModel):
    """Delete a saved Wi-Fi network profile."""
    if not wifi.ssid:
        return {"status": "error", "message": "SSID is required"}
    
    if sys.platform == 'win32':
        return {"status": "ok"}
    
    try:
        result = subprocess.run(
            ["sudo", "/usr/bin/nmcli", "connection", "delete", "id", wifi.ssid],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            return {"status": "error", "message": error_msg}
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/system/restart")
def api_system_restart():
    subprocess.Popen(["sudo", "/sbin/reboot"])
    return {"status": "ok"}

@app.post("/api/system/shutdown")
def api_system_shutdown():
    subprocess.Popen(["sudo", "/sbin/poweroff"])
    return {"status": "ok"}

@app.get("/api/settings")
def api_get_settings():
    s = get_settings()
    targets_str = s.get("targets", '[{"name": "Crisislab Server", "ip": "10.241.144.172", "port": 2098}]')
    try:
        targets_raw = json.loads(targets_str)
        targets = []
        for t in targets_raw:
            targets.append({
                "name": t.get("name", "Unknown Node"),
                "ip": t.get("ip", "10.241.144.172"),
                "port": t.get("port", 2098),
                "format": t.get("format", "corrected"),
            })
    except Exception:
        targets = [{"name": "Crisislab Server", "ip": "10.241.144.172", "port": 2098, "format": "corrected"}]
        
    return {
        "targets": targets, 
        "latitude": float(s.get("latitude", 0.0)),
        "longitude": float(s.get("longitude", 0.0)),
        "elevation": float(s.get("elevation", 0.0)),
        "floor_unit": int(s.get("floor_unit", 0)),
        "total_floors": int(s.get("total_floors", 1)),
        "device_name": s.get("device_name", "CRISIS-NODE-01"),
        "device_id": s.get("device_id", "T0021"),
        "owner_name": s.get("owner_name", ""),
        "owner_email": s.get("owner_email", ""),
        "calibration_time": int(s.get("calibration_time", 60)),
        "retention_days": int(s.get("retention_days", 7)),
        "archive_size_bytes": mseed_writer.get_archive_size_bytes(),
        "data_forwarding": s.get("data_forwarding", "true").lower() == "true",
        "is_configured": s.get("is_configured", "false").lower() == "true",
        "active_wifi": _get_active_ssid(),
        # Hardware variant info (read-only, set by setup_service.sh or manual DB edit)
        "sensor_variant": SENSOR_VARIANT,
        "channel_names": CHANNEL_NAMES,
        "channel_units": {ch: CHANNEL_UNITS[i] for i, ch in enumerate(CHANNEL_NAMES)},
    }

@app.post("/api/settings")
def api_set_settings(settings: SettingsModel):
    targets_json = json.dumps([
        {"name": t.name, "ip": t.ip, "port": t.port, "format": t.format}
        for t in settings.targets
    ])
    settings_dict = {
        "targets": targets_json,
        "latitude": settings.latitude,
        "longitude": settings.longitude,
        "elevation": settings.elevation if settings.elevation is not None else 0.0,
        "floor_unit": settings.floor_unit if settings.floor_unit is not None else 0,
        "total_floors": settings.total_floors if settings.total_floors is not None else 1,
        "data_forwarding": "true" if settings.data_forwarding else "false"
    }
    if settings.device_name is not None:
        settings_dict["device_name"] = settings.device_name
    if settings.device_id is not None:
        settings_dict["device_id"] = settings.device_id
    if settings.owner_name is not None:
        settings_dict["owner_name"] = settings.owner_name
    if settings.owner_email is not None:
        settings_dict["owner_email"] = settings.owner_email
    if settings.calibration_time is not None:
        settings_dict["calibration_time"] = settings.calibration_time
    if settings.retention_days is not None:
        settings_dict["retention_days"] = settings.retention_days
    if settings.is_configured is not None:
        settings_dict["is_configured"] = "true" if settings.is_configured else "false"
        
    update_settings(settings_dict)

    # Refresh device_id cache and push updated metadata to the central server
    https_publisher.refresh_settings()
    
    # Fetch the definitively saved settings from the database
    updated_s = get_settings()
    https_publisher.send_metadata({
        "device_id":    updated_s.get("device_id", "T0021"),
        "ts":           time.time(),
        "device_name":  updated_s.get("device_name", "CRISIS-NODE-01"),
        "owner_name":   updated_s.get("owner_name", ""),
        "owner_email":  updated_s.get("owner_email", ""),
        "latitude":     float(updated_s.get("latitude", 0.0)),
        "longitude":    float(updated_s.get("longitude", 0.0)),
        "elevation_m":  float(updated_s.get("elevation", 0.0)),
        "floor":        int(updated_s.get("floor_unit", 0)),
        "total_floors": int(updated_s.get("total_floors", 1)),
    })

    return {"status": "ok"}

# ---------------------------------------------------------------------------
# Device Metadata / Instrument Response endpoint
# ---------------------------------------------------------------------------

from metadata import build_stationxml

@app.get("/api/metadata/stationxml")
def api_metadata_stationxml():
    """Download the FDSN StationXML instrument response file for this node.

    The file encodes the full sensitivity chain
    (ADXL354BEZ → ADA4522-1 RC LPF → ADS1220 ADC) so that any FDSN-aware
    analysis tool (ObsPy, SeisComP, SEISAN …) can deconvolve raw ADC counts
    into physical acceleration units (m/s²).

    ObsPy usage::

        inv = read_inventory('<device>_response.xml')
        st.attach_response(inv)
        acc = st.remove_response(output='ACC')   # → m/s²
    """
    s           = get_settings()
    device_name = s.get("device_name", "CRISIS-NODE-01")
    device_id   = s.get("device_id", "UNKNOWN-ID")
    latitude    = float(s.get("latitude",   0.0))
    longitude   = float(s.get("longitude",  0.0))
    elevation   = float(s.get("elevation",  0.0))

    xml_content = build_stationxml(device_name, device_id, latitude, longitude, elevation)
    filename    = f"{device_name}_response.xml"

    return StreamingResponse(
        iter([xml_content]),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )




_cached_internet = False
_last_internet_check = 0

def _check_internet():
    """Check if outbound internet connectivity is available (cached for 10s)."""
    global _cached_internet, _last_internet_check
    if time.time() - _last_internet_check < 10:
        return _cached_internet
        
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=0.5)
        _cached_internet = True
    except OSError:
        _cached_internet = False
        
    _last_internet_check = time.time()
    return _cached_internet

# Cache MAC address exactly once per boot since it never changes
MAC_ADDRESS = ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) for ele in range(0,8*6,8)][::-1])

@app.get("/api/system_status")
def api_system_status():
    try:
        cpu = psutil.cpu_percent(interval=None) # Non-blocking return since last call
        disk = psutil.disk_usage('/').percent
        uptime_sec = int(time.time() - psutil.boot_time())
        days = uptime_sec // (24 * 3600)
        uptime_sec = uptime_sec % (24 * 3600)
        hours = uptime_sec // 3600
        minutes = (uptime_sec % 3600) // 60
        uptime_str = f"{days}d {hours}h {minutes}m"
        
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            s.connect(('10.254.254.254', 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
            
        return {
            "cpu_percent": cpu,
            "disk_percent": disk,
            "uptime": uptime_str,
            "local_ip": ip,
            "mac_address": MAC_ADDRESS,
            "internet_status": _check_internet(),
            "server_status": True,
            "hardware_sps": sensor_manager.hardware_sps,
            "avg_sps": sensor_manager.avg_sps
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/export")
def api_export(start: float, end: float, format: str = "csv"):
    if end < start:
        raise HTTPException(status_code=400, detail="End time must be after start time")
    
    from mseed_writer import read_waveform_range
    st = read_waveform_range(start, end)
    if not st or len(st) == 0:
        raise HTTPException(status_code=404, detail="No data found in archive for this time range")
    
    st.merge(method=1, fill_value='interpolate')
    
    if format.lower() == "mseed":
        try:
            import zipfile
            output = io.BytesIO()
            with zipfile.ZipFile(output, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
                for tr in st:
                    tr_out = io.BytesIO()
                    tr.write(tr_out, format='MSEED', encoding='INT32', reclen=512)
                    tr_out.seek(0)
                    
                    year = tr.stats.starttime.year
                    jday = tr.stats.starttime.julday
                    fname = f"{tr.stats.network}.{tr.stats.station}.{tr.stats.location}.{tr.stats.channel}.D.{year}.{jday:03d}"
                    zf.writestr(fname, tr_out.getvalue())
            
            output.seek(0)
            response = StreamingResponse(output, media_type="application/zip")
            response.headers["Content-Disposition"] = f"attachment; filename=eew_export_{int(time.time())}.zip"
            return response
        except ImportError:
            raise HTTPException(status_code=500, detail="ObsPy is not installed.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"MSEED generation failed: {e}")
            
    else:
        try:
            # Build channel dict dynamically from CHANNEL_NAMES
            chans = {tr.stats.channel: tr for tr in st}
            ref_tr = None
            for ch in CHANNEL_NAMES:
                if ch in chans:
                    ref_tr = chans[ch]
                    break

            if not ref_tr:
                raise ValueError(f"No channels from {CHANNEL_NAMES} found in archive")

            times = ref_tr.times(type="timestamp")
            ch_data = {}
            for ch in CHANNEL_NAMES:
                ch_data[ch] = chans[ch].data if ch in chans else [0] * len(times)

            min_len = min(len(times), *(len(ch_data[ch]) for ch in CHANNEL_NAMES))

            def iter_csv():
                # Header: time, CH0, CH1, ...
                yield "time," + ",".join(CHANNEL_NAMES) + "\n"
                chunk = []
                for i in range(min_len):
                    row = f"{times[i]:.6f}" + ",".join(str(ch_data[ch][i]) for ch in CHANNEL_NAMES)
                    chunk.append(row + "\n")
                    if len(chunk) >= 10000:
                        yield "".join(chunk)
                        chunk.clear()
                if chunk:
                    yield "".join(chunk)

            response = StreamingResponse(iter_csv(), media_type="text/csv")
            response.headers["Content-Disposition"] = f"attachment; filename=eew_export_{int(time.time())}.csv"
            return response
        except Exception as e:
             raise HTTPException(status_code=500, detail=f"CSV generation failed: {e}")


@app.get("/api/export/all")
def api_export_all():
    """Stream the entire SDS archive as a single ZIP file."""
    from database import get_settings
    s = get_settings()
    archive_root = s.get('archive_root', '/home/crisislab/data/archive')
    
    if not os.path.isdir(archive_root):
        raise HTTPException(status_code=404, detail="Archive directory not found")
        
    def iter_zip():
        import zipfile
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_name = tmp.name
            with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zf:
                for dirpath, _, filenames in os.walk(archive_root):
                    for fname in filenames:
                        full_path = os.path.join(dirpath, fname)
                        arcname = os.path.relpath(full_path, archive_root)
                        zf.write(full_path, arcname)
                        
        with open(tmp_name, 'rb') as f:
            while chunk := f.read(8192):
                yield chunk
        os.remove(tmp_name)
        
    response = StreamingResponse(iter_zip(), media_type="application/zip")
    response.headers["Content-Disposition"] = f"attachment; filename=eew_full_archive_{int(time.time())}.zip"
    return response

@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    # 50 batches × 25 samples = ~12.5 s of backlog before drops
    queue = asyncio.Queue(maxsize=50)
    sensor_manager.subscribe(queue)
    try:
        while True:
            batch = await queue.get()
            await websocket.send_json(batch)
    except WebSocketDisconnect:
        pass
    finally:
        sensor_manager.unsubscribe(queue)

# ---------------------------------------------------------------------------
# Analysis endpoints
# ---------------------------------------------------------------------------

@app.get("/api/analysis/filter")
def api_get_filter():
    """Return current bandpass filter parameters."""
    return sensor_manager.get_filter_params()

@app.post("/api/analysis/filter")
def api_set_filter(params: FilterModel):
    """Update bandpass filter cutoff frequencies."""
    if params.low_hz >= params.high_hz:
        raise HTTPException(status_code=400, detail="low_hz must be less than high_hz")
    sensor_manager.update_filter(params.low_hz, params.high_hz)
    return {"status": "ok", **sensor_manager.get_filter_params()}

@app.get("/api/analysis/window")
async def api_analysis_window(request: Request, start: float = None, end: float = None, seconds: float = None):
    """Return filtered historical data for a time range.
    
    Accepts either:
      - start + end (absolute epoch timestamps)
      - seconds (shorthand for 'last N seconds' — backward compat)
    
    Max window: 3600 seconds (1 hour).
    """
    import time as _time
    now = _time.time()

    if seconds is not None:
        # Backward-compatible mode: 'last N seconds'
        if seconds < 300 or seconds > 3600:
            raise HTTPException(status_code=400, detail="seconds must be between 300 and 3600")
        end = now
        start = now - seconds
    elif start is not None and end is not None:
        if end < start:
            raise HTTPException(status_code=400, detail="end must be after start")
        window = end - start
        if window < 300 or window > 3600:
            raise HTTPException(status_code=400, detail="Window must be between 5 minutes and 1 hour")
        # Don't allow queries into the future
        if start > now:
            raise HTTPException(status_code=400, detail="Start time is in the future")
    else:
        # Default: last 5 minutes
        end = now
        start = now - 300

    # Run in a separate PROCESS — entirely bypasses Python GIL so the 
    # sensor reading hardware thread is completely uninterrupted.
    with sensor_manager._filter_lock:
        high_hz = sensor_manager._filters[CHANNEL_NAMES[0]].high_hz
        low_hz = sensor_manager._filters[CHANNEL_NAMES[0]].low_hz
        
    from database import get_settings
    settings_snapshot = get_settings()
    
    # Check if client disconnected before starting heavy task
    if await request.is_disconnected():
        return {}

    # Flush the RAM buffer to SD card immediately so the subprocess
    # can read data right up to the exact millisecond of this request.
    from mseed_writer import mseed_writer
    await asyncio.to_thread(mseed_writer.flush)
        
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        process_pool, 
        process_historical_data_task, 
        start, end, low_hz, high_hz, 4000, settings_snapshot
    )
    return result


@app.get("/api/analysis/availability")
def api_analysis_availability():
    """Return the earliest and latest data timestamps in the SDS archive."""
    return mseed_writer.get_archive_availability()


@app.get("/api/analysis/presets")
def api_analysis_presets():
    """Return available filter presets."""
    return {"presets": FILTER_PRESETS}

@app.websocket("/ws/analysis")
async def websocket_analysis(websocket: WebSocket):
    """Stream filtered (bandpass) data batches to the analysis frontend."""
    await websocket.accept()
    queue = asyncio.Queue(maxsize=50)
    sensor_manager.subscribe_analysis(queue)
    try:
        while True:
            batch = await queue.get()
            await websocket.send_json(batch)
    except WebSocketDisconnect:
        pass
    finally:
        sensor_manager.unsubscribe_analysis(queue)

@app.get("/api/stream/stats")
def api_stream_stats():
    """Returns WebSocket batch delivery stats for client-side health monitoring."""
    total = sensor_manager._ws_batches_sent + sensor_manager._ws_batches_dropped
    drop_rate = (
        sensor_manager._ws_batches_dropped / total * 100 if total > 0 else 0.0
    )
    return {
        "batches_sent": sensor_manager._ws_batches_sent,
        "batches_dropped": sensor_manager._ws_batches_dropped,
        "drop_rate_pct": round(drop_rate, 2),
        "hardware_sps": sensor_manager.hardware_sps,
        "avg_sps": sensor_manager.avg_sps,
    }

import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Serve the compiled React frontend directly from FastAPI.
# In production the systemd service sets EEW_FRONTEND_DIST=/opt/eew-sensor/frontend.
# In development the path is resolved relative to this source file.
_env_frontend = os.environ.get("EEW_FRONTEND_DIST", "")
if _env_frontend:
    frontend_dist_path = os.path.abspath(_env_frontend)
else:
    frontend_dist_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
if os.path.exists(frontend_dist_path):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist_path, "assets")), name="assets")
    
    @app.get("/{catchall:path}")
    def serve_react_app(catchall: str):
        # Prevent directory traversal
        if ".." in catchall:
            raise HTTPException(status_code=400, detail="Invalid path")
            
        # If the requested path is a specific file (like logo.png, favicon.svg) in the dist folder, serve it
        if catchall:
            file_path = os.path.join(frontend_dist_path, catchall)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                return FileResponse(file_path)
                
        # Serve index.html as a fallback for React Router
        index_path = os.path.join(frontend_dist_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"error": "Frontend build not found"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
