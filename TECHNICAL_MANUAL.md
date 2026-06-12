# Technical Documentation Manual

**System:** Edge-Based Earthquake Early Warning (EEW) Sensor Node & Live Telemetry Dashboard Gateway  
**Version:** 1.0.0  
**Target Platform:** Raspberry Pi 3/4 (Linux)  
**Authors:** CRISiS Lab & Development Team  

---

## 1. System Overview

The Edge-Based Earthquake Early Warning (EEW) Sensor Node is an integrated, low-latency telemetry device designed to capture, process, and transmit high-fidelity seismic data in real-time. By utilizing a Raspberry Pi equipped with an ADXL354 triaxial analog accelerometer and three discrete 24-bit ADCs (ADS1220), the system guarantees precise 100 Hz sampling.

The gateway features a robust, multithreaded **FastAPI backend** handling hardware interfacing, data persistence, and remote UDP telemetry forwarding. A bundled **React/Vite frontend dashboard** provides an intuitive localized interface for real-time waveform visualization, Wi-Fi configuration, and historical data extraction.

### 1.1 Core Capabilities
- **Real-Time Data Acquisition:** Triaxial (Z, X, Y) acceleration tracking mapped to geological components (ENZ, ENN, ENE) at 100 Samples Per Second (SPS).
- **Dual-Stream Telemetry:** Simultaneously streams low-latency JSON payloads via WebSockets to local clients and forwards dense UDP packets to external data centers.
- **Offline Resilience:** Auto-caches 24 hours of seismic data locally in a SQLite database with background eviction.
- **Edge Configuration:** On-board API allowing zero-downtime reconfiguration of target UDP endpoints and headless Wi-Fi management.

---

## 2. System Architecture

The software architecture relies on a decoupled, asynchronous pipeline optimized for edge IoT devices where hardware constraints are critical. 

```mermaid
graph TD
    subgraph Hardware Layer
        ADXL354[ADXL354 Accelerometer] -->|Analog Voltage| ADC[3x ADS1220 24-bit ADCs]
        ADC -->|SPI Data & DRDY Interrupts| RPi[Raspberry Pi GPIO]
    end

    subgraph Edge Backend [Python FastAPI Server]
        RPi -->|spidev / RPi.GPIO| SM(Sensor Manager Thread)
        
        SM -->|100 Hz Stream| Buffer{In-Memory Queue}
        
        Buffer -->|Real-Time (Per Sample)| WS[WebSocket Broadcaster]
        Buffer -->|Batch (Every 50 Samples)| DB[(SQLite Local Storage)]
        Buffer -->|Batch (Every 25 Samples)| UDP[UDP Network Forwarder]
        
        API[FastAPI Controllers] --> DB
        API --> System[Linux nmcli / systemd]
    end

    subgraph Client Layer [React Dashboard / External]
        WS -->|Live JSON| LiveChart[Live Waveform UI]
        API <-->|REST Config| ConfigUI[Settings / Wi-Fi UI]
        DB -->|CSV Dump| ExportUI[Data Export UI]
        
        UDP -->|Raw Packets| Remote[Remote EEW Data Centers]
    end
```

---

## 3. Hardware Interfacing & Pinout Specifications

The sensor relies on precise timing for data-ready (`DRDY`) interrupts and SPI communications.

### 3.1 GPIO Pin Mapping

| Logical Function | Physical Pin (BOARD) | Periphery Target |
|------------------|----------------------|------------------|
| **SPI MOSI**     | Pin 19               | ADC DIN (All)    |
| **SPI MISO**     | Pin 21               | ADC DOUT (All)   |
| **SPI SCLK**     | Pin 23               | ADC SCLK (All)   |
| **CS - Z Axis**  | Pin 35               | ADC 0 CS         |
| **CS - X Axis**  | Pin 33               | ADC 1 CS         |
| **CS - Y Axis**  | Pin 36               | ADC 2 CS         |
| **DRDY - Z**     | Pin 11               | ADC 0 DRDY       |
| **DRDY - X**     | Pin 15               | ADC 1 DRDY       |
| **DRDY - Y**     | Pin 13               | ADC 2 DRDY       |
| **STBY (Standby)**| Pin 22               | ADXL354 STBY     |

### 3.2 Sensor Configuration Parameters

> [!IMPORTANT]
> The following parameters are critical for achieving accurate conversions from raw ADC codes to metric acceleration ($m/s^2$). Modify these variables in `backend/sensor.py` if hardware changes are made.

```python
# --- Hardware & ADC Definitions ---
CS_PINS = [35, 33, 36]        # Chip Select: Acc Z, Acc X, Acc Y
DRDY_PINS = [11, 15, 13]      # Data Ready Interrupts
VREF_ADCS = [1.8, 1.8, 1.8]   # Precision Voltage Reference for ADCs
FULL_SCALE = 8388607          # 24-bit signed integer max (2^23 - 1)
CHANNEL_NAMES = ['ENZ', 'ENN', 'ENE'] # SEED standard channel nomenclature

# --- Signal Processing Constraints ---
SAMPLES_PER_PACKET = 25       # Packet boundary for UDP payloads
SAMPLE_INTERVAL = 0.0035      # Calibrated timing to achieve 100.0 SPS
ACC_SENSITIVITY_V_PER_G = 0.4 # ADXL354 sensitivity metric
G_TO_MS2 = 9.80665            # Standard gravity conversion factor
```

---

## 4. Software Modules

To provide a deeper understanding of the system's software integration, the following architecture diagram illustrates how the frontend components interact with the FastAPI backend, which in turn manages hardware state and database persistence.

```mermaid
graph TD
    subgraph Frontend [React / Vite Dashboard]
        UI[User Interface]
        Chart[Live Chart Component]
        SettingsUI[Settings Config]
        ExportUI[Data Export Tool]
    end

    subgraph Backend [FastAPI Application Server]
        API[REST API Router]
        WS[WebSocket Manager]
        SM[Sensor Manager Thread]
        Static[Static File Server]
    end

    subgraph Database [SQLite DB]
        DB_Data[(sensor_data table)]
        DB_Settings[(settings table)]
    end

    %% Frontend to Backend Connections
    UI -.->|Fetches Assets| Static
    Chart <==>|ws://.../ws/stream (100Hz JSON)| WS
    SettingsUI <-->|HTTP GET/POST /api/settings| API
    ExportUI -->|HTTP GET /api/export| API

    %% Backend internal connections
    WS <--|Reads data| SM
    API -->|Reads/Writes| DB_Settings
    API -->|Queries| DB_Data
    SM -->|Batch Writes| DB_Data
    
    %% Background task
    API -.->|Hourly Cleanup Task| DB_Data
```

### 4.1 Backend Engine (`main.py` & `sensor.py`)
- **FastAPI Lifecycle Context:** Starts the sensor manager in an independent `threading.Thread` on boot, keeping the `asyncio` event loop free for networking.
- **Hardware Threading:** The `SensorManager` executes a strict timing loop utilizing a hybrid sleep-and-busy-wait approach to achieve exactly $100\text{ Hz}$ throughput, minimizing jitter caused by Python garbage collection.
- **Network Interface Manager:** Employs Linux `nmcli` to execute Wi-Fi network switching securely from the UI via background subprocesses.

### 4.2 Data Persistence (`database.py`)
- Implements thread-safe SQLite operations using `sqlite3` and `threading.Lock`. 
- Incorporates a self-maintaining retention policy: a background daemon purges data older than 24 hours (`86400` seconds) to prevent SD card saturation.

### 4.3 Frontend Dashboard (`React` & `Vite`)
- Served statically from the FastAPI root (`/assets`).
- Renders high-performance `<canvas>` graphs using `uPlot`, capable of drawing thousands of points smoothly on low-power devices.
- Uses localized state management to adjust timestamps to user-defined timezones seamlessly.

---

## 5. Network Protocol & API Reference

### 5.1 Real-Time WebSocket Telemetry
- **Endpoint:** `ws://<device-ip>:8000/ws/stream`
- **Data Frequency:** 100 messages/second.
- **Payload Schema:**
```json
{
  "t": 1684391234.56789,
  "ENZ": 0.00245,
  "ENN": -0.01520,
  "ENE": 0.00891
}
```

### 5.2 External UDP Data Forwarding
- UDP packets are aggregated to reduce overhead (25 samples per packet).
- Data sequence format: `['CHANNEL_NAME', base_timestamp, val1, val2, ... val25]`
- Target arrays dynamically configured via REST API and persisted in SQLite.

### 5.3 REST API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/api/system_status` | Returns system resource telemetry (CPU, RAM, Uptime) |
| `POST` | `/api/settings`      | Modifies device metadata and UDP transmission targets |
| `GET`  | `/api/wifi/networks` | Scans for available 802.11 environments via `nmcli` |
| `POST` | `/api/wifi/connect`  | Provisions new SSID/Password profiles and initiates handshakes |
| `GET`  | `/api/export`        | Initiates streaming download of local CSV records based on epoch timestamps |

---

## 6. Deployment & Service Configuration

The edge node utilizes `systemd` to achieve high availability. The background service assumes `CAP_NET_BIND_SERVICE` permissions to bind to Port 80 without executing the entire runtime as `root`.

**systemd Service Blueprint (`eew-sensor.service`):**
```ini
[Unit]
Description=EEW Sensor Backend & UI Service
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/EEW-Sensor-Firmware-and-UI/backend
AmbientCapabilities=CAP_NET_BIND_SERVICE
ExecStart=/home/pi/EEW-Sensor-Firmware-and-UI/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 80
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

---

## 7. User Interface Guide

### 7.1 Dashboard Overview
The main interface provides immediate situational awareness regarding seismic triggers and device health.

> ![Live Dashboard Overview](assets/placeholder_dashboard.png)
> *Placeholder: Insert screenshot of the main dashboard illustrating the 3-channel waveform graph and resource status cards.*

### 7.2 Sensor Configuration
Users interact with the UI to declare the edge node's geographic coordinates, assign an identifier, and determine the data aggregation policy.

> ![Settings Interface](assets/placeholder_settings.png)
> *Placeholder: Insert screenshot of the Settings pane detailing the UDP target input fields and Wi-Fi manager modal.*

---

## 8. Maintenance & Troubleshooting

| Symptom | Diagnostic Step | Resolution |
|---------|-----------------|------------|
| **DRDY Timeout Error** | Execute `ls /dev/spidev*` to confirm SPI kernel objects exist. | Enable SPI using `raspi-config`. Verify integrity of jumper cables on GPIO Pins 11, 15, and 13. |
| **High Jitter / Variable SPS** | Monitor `system_status` API for CPU throttling. | Ensure background `apt` updates are disabled. The Pi 4 requires adequate thermal cooling to prevent CPU throttling which distorts the `time.sleep()` interrupt loops. |
| **UI Displays "Waiting for data..."** | Check network inspector in browser for WebSocket (`101 Switching Protocols`) status. | If WebSocket connects but no data flows, the sensor may be executing the 100-second zero-level calibration block. Wait 2 minutes. |
| **Wi-Fi Module Unresponsive** | Run `sudo nmcli radio wifi`. | The `NetworkManager` backend might be conflicted by `wpa_supplicant`. Verify `nmcli` is the designated wireless daemon in `raspi-config`. |
