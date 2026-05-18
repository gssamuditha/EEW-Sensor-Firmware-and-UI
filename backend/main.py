import asyncio
import csv
import io
import time
import json
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
    sensor_manager.start()
    
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
    ip: str
    port: int

class SettingsModel(BaseModel):
    targets: list[TargetModel]
    latitude: float
    longitude: float

@app.get("/api/settings")
def api_get_settings():
    s = get_settings()
    targets_str = s.get("targets", '[{"ip": "127.0.0.1", "port": 2098}]')
    try:
        targets = json.loads(targets_str)
    except:
        targets = [{"ip": "127.0.0.1", "port": 2098}]
        
    return {
        "targets": targets, 
        "latitude": float(s.get("latitude", 0.0)),
        "longitude": float(s.get("longitude", 0.0))
    }

@app.post("/api/settings")
def api_set_settings(settings: SettingsModel):
    targets_json = json.dumps([{"ip": t.ip, "port": t.port} for t in settings.targets])
    update_settings(targets_json, settings.latitude, settings.longitude)
    return {"status": "ok"}

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
    queue = asyncio.Queue(maxsize=100)
    sensor_manager.subscribe(queue)
    try:
        while True:
            t, z, x, y = await queue.get()
            # Send small dict to minimize overhead
            await websocket.send_json({"t": t, "z": z, "x": x, "y": y})
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
        # Serve index.html as a fallback for React Router
        index_path = os.path.join(frontend_dist_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"error": "Frontend build not found"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
