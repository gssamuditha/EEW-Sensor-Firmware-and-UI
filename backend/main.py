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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from database import init_db, cleanup_old_data, get_data_for_export, get_settings, update_settings, stop_db_writer, get_data_availability
from filters import FILTER_PRESETS
from sensor import sensor_manager, process_historical_data_task, CHANNEL_NAMES
from concurrent.futures import ProcessPoolExecutor

# Use a ProcessPool to run heavy numpy/scipy operations entirely out-of-process, bypassing the GIL.
process_pool = ProcessPoolExecutor(max_workers=2)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Run sensor init in a thread to avoid blocking the asyncio event loop
    # (RealSensor.init_sensor sleeps ~11s, calibrate sleeps ~100s)
    loop = asyncio.get_running_loop()
    await asyncio.to_thread(sensor_manager.start, loop)
    
    # Background task for cleanup
    async def cleanup_task():
        while True:
            await asyncio.sleep(3600)  # Every hour
            cleanup_old_data()
            
    task = asyncio.create_task(cleanup_task())
    yield
    sensor_manager.stop()
    stop_db_writer()
    task.cancel()
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

class SettingsModel(BaseModel):
    targets: list[TargetModel]
    latitude: float
    longitude: float
    data_forwarding: bool = True
    device_name: str | None = None
    calibration_time: int | None = None

class WifiConnectModel(BaseModel):
    ssid: str
    password: str = ""

class WifiActionModel(BaseModel):
    ssid: str

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

def _get_active_ssid():
    """Return the SSID of the currently active Wi-Fi connection, or None."""
    if sys.platform == 'win32':
        return "Senz Cloud"  # mock for Windows dev
    try:
        result = subprocess.run(
            ['sudo', '/usr/bin/nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split('\n'):
            if line.startswith('yes:'):
                return line.split('yes:', 1)[1].strip()
    except Exception:
        pass
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
    networks, active_ssid = _get_saved_networks()
    return {"networks": networks, "active_ssid": active_ssid}

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

@app.get("/api/settings")
def api_get_settings():
    s = get_settings()
    targets_str = s.get("targets", '[{"name": "Main Server", "ip": "127.0.0.1", "port": 2098}]')
    try:
        targets_raw = json.loads(targets_str)
        targets = []
        for t in targets_raw:
            targets.append({
                "name": t.get("name", "Unknown Node"),
                "ip": t.get("ip", "127.0.0.1"),
                "port": t.get("port", 2098)
            })
    except Exception:
        targets = [{"name": "Main Server", "ip": "127.0.0.1", "port": 2098}]
        
    return {
        "targets": targets, 
        "latitude": float(s.get("latitude", 0.0)),
        "longitude": float(s.get("longitude", 0.0)),
        "device_name": s.get("device_name", "CRISIS-NODE-01"),
        "calibration_time": int(s.get("calibration_time", 60)),
        "data_forwarding": s.get("data_forwarding", "true").lower() == "true",
        "active_wifi": _get_active_ssid()
    }

@app.post("/api/settings")
def api_set_settings(settings: SettingsModel):
    targets_json = json.dumps([{"name": t.name, "ip": t.ip, "port": t.port} for t in settings.targets])
    settings_dict = {
        "targets": targets_json,
        "latitude": settings.latitude,
        "longitude": settings.longitude,
        "data_forwarding": "true" if settings.data_forwarding else "false"
    }
    if settings.device_name is not None:
        settings_dict["device_name"] = settings.device_name
    if settings.calibration_time is not None:
        settings_dict["calibration_time"] = settings.calibration_time
        
    update_settings(settings_dict)
    return {"status": "ok"}

def _check_internet():
    """Check if outbound internet connectivity is available."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError:
        return False

@app.get("/api/system_status")
def api_system_status():
    try:
        cpu = psutil.cpu_percent(interval=0.1) # short blocking is okay for this stats
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
            
        mac = ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) 
                        for ele in range(0,8*6,8)][::-1])
                        
        return {
            "cpu_percent": cpu,
            "disk_percent": disk,
            "uptime": uptime_str,
            "local_ip": ip,
            "mac_address": mac,
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
    
    data = get_data_for_export(start, end)
    if not data:
        raise HTTPException(status_code=404, detail="No data found for this time range")
        
    import numpy as np
    from filters import obspy_resample_trace
    
    arr = np.array(data, dtype=np.float64)
    raw_t = arr[:, 0]
    
    # Mathematically Resample to EXACT 100.0 SPS using ObsPy Lanczos
    t_100, z_100 = obspy_resample_trace(raw_t, arr[:, 1], input_sps=200.0, target_sps=100.0)
    _, x_100 = obspy_resample_trace(raw_t, arr[:, 2], input_sps=200.0, target_sps=100.0)
    _, y_100 = obspy_resample_trace(raw_t, arr[:, 3], input_sps=200.0, target_sps=100.0)
    
    if format.lower() == "mseed":
        try:
            from obspy import Trace, Stream, UTCDateTime
            stream = Stream()
            starttime = UTCDateTime(t_100[0])
            
            for name, ch_data in [('ENZ', z_100), ('ENN', x_100), ('ENE', y_100)]:
                tr = Trace(data=ch_data.astype(np.float32))
                tr.stats.network = "XX"
                tr.stats.station = "EEWS"
                tr.stats.channel = name
                tr.stats.sampling_rate = 100.0
                tr.stats.starttime = starttime
                stream.append(tr)
                
            output = io.BytesIO()
            stream.write(output, format='MSEED')
            output.seek(0)
            
            response = StreamingResponse(output, media_type="application/vnd.fdsn.mseed")
            response.headers["Content-Disposition"] = f"attachment; filename=eew_export_{int(time.time())}.mseed"
            return response
        except ImportError:
            raise HTTPException(status_code=500, detail="ObsPy is not installed. MSEED export requires ObsPy.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"MSEED generation failed: {e}")
            
    else:
        output = io.StringIO()
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(["time", "ENZ", "ENN", "ENE"])
        for i in range(len(t_100)):
            writer.writerow([f"{t_100[i]:.6f}", f"{z_100[i]:.6f}", f"{x_100[i]:.6f}", f"{y_100[i]:.6f}"])
            
        response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
        response.headers["Content-Disposition"] = f"attachment; filename=eew_export_{int(time.time())}.csv"
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
async def api_analysis_window(start: float = None, end: float = None, seconds: float = None):
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
        
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        process_pool, 
        process_historical_data_task, 
        start, end, low_hz, high_hz, 4000
    )
    return result


@app.get("/api/analysis/availability")
def api_analysis_availability():
    """Return the earliest and latest data timestamps in the DB."""
    return get_data_availability()


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

# Serve the compiled React frontend directly from FastAPI
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
