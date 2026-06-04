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
from pydantic import BaseModel

from database import init_db, cleanup_old_data, get_data_for_export, get_settings, update_settings
from sensor import sensor_manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Run sensor init in a thread to avoid blocking the asyncio event loop
    # (RealSensor.init_sensor sleeps ~11s, calibrate sleeps ~100s)
    await asyncio.to_thread(sensor_manager.start)
    
    # Background task for cleanup
    async def cleanup_task():
        while True:
            await asyncio.sleep(3600)  # Every hour
            cleanup_old_data()
            
    task = asyncio.create_task(cleanup_task())
    yield
    sensor_manager.stop()
    task.cancel()

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

# ---------------------------------------------------------------------------
# Wi-Fi Manager helpers
# ---------------------------------------------------------------------------

def _get_active_ssid():
    """Return the SSID of the currently active Wi-Fi connection, or None."""
    if sys.platform == 'win32':
        return "Senz Cloud"  # mock for Windows dev
    try:
        result = subprocess.run(
            ['sudo', 'nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'],
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
            ['sudo', 'nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'],
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
                ["sudo", "nmcli", "dev", "wifi", "connect", ssid, "password", password],
                capture_output=True, text=True, timeout=30
            )
        else:
            # Saved network: try 'connection up' first (faster), fallback to 'dev wifi connect'
            result = subprocess.run(
                ["sudo", "nmcli", "connection", "up", "id", ssid],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                subprocess.run(
                    ["sudo", "nmcli", "dev", "wifi", "connect", ssid],
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
            ["sudo", "nmcli", "connection", "delete", "id", wifi.ssid],
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
    subprocess.Popen(["sudo", "reboot"])
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
def api_export(start: float, end: float):
    if end < start:
        raise HTTPException(status_code=400, detail="End time must be after start time")
    
    data = get_data_for_export(start, end)
    
    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(["time", "ENZ", "ENN", "ENE"])
    for row in data:
        # row: timestamp, z, x, y
        t, z, x, y = row
        writer.writerow([f"{t:.6f}", f"{z:.6f}", f"{x:.6f}", f"{y:.6f}"])
        
    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=eew_export_{int(time.time())}.csv"
    return response

@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    queue = asyncio.Queue(maxsize=1000)
    sensor_manager.subscribe(queue)
    try:
        while True:
            t, z, x, y = await queue.get()
            await websocket.send_json({"t": t, "ENZ": z, "ENN": x, "ENE": y})
    except WebSocketDisconnect:
        pass
    finally:
        sensor_manager.unsubscribe(queue)

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
