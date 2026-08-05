# EEW Sensor Firmware & UI

A real-time **Earthquake Early Warning (EEW)** sensor system built for deployment on a **Raspberry Pi**. The system reads triaxial acceleration data from an **ADXL354** accelerometer via SPI-connected ADCs, streams it over WebSocket, stores it in a local SQLite database, and visualizes it through a React-based dashboard — all served from a single FastAPI backend.

> **Developed at [CRISiS Lab](https://www.crisislab.org.nz/) and [SLIIT](https://www.sliit.lk/)**

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Module Descriptions](#module-descriptions)
  - [Backend Modules](#backend-modules)
  - [Frontend Modules](#frontend-modules)
  - [Legacy Firmware](#legacy-firmware)
  - [Deployment Scripts](#deployment-scripts)
- [Hardware Requirements](#hardware-requirements)
- [Wiring Diagram](#wiring-diagram)
- [Software Prerequisites](#software-prerequisites)
- [Development Setup (Windows / Mac / Linux PC)](#development-setup-windows--mac--linux-pc)
- [**Professional Deployment (CI/CD Pipeline)**](#professional-deployment-cicd-pipeline)
  - [How it works](#how-it-works)
  - [Publishing a release](#publishing-a-release)
  - [First-time Pi installation](#first-time-pi-installation)
  - [OTA updates](#ota-updates)
- [Raspberry Pi Setup (Legacy / Development)](#raspberry-pi-setup)
  - [1. OS Installation](#1-os-installation)
  - [2. Enable SPI Interface](#2-enable-spi-interface)
  - [3. Clone and Install](#3-clone-and-install)
  - [4. Build the Frontend](#4-build-the-frontend)
  - [5. Manual Run (Test)](#5-manual-run-test)
- [Configure Autorun on Boot](#configure-autorun-on-boot)
  - [Using the Setup Script](#using-the-setup-script)
  - [Manual systemd Configuration](#manual-systemd-configuration)
  - [Managing the Service](#managing-the-service)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Architecture Overview

![Alt text for the image](docs\Architecture_diagram.png)


---

## Project Structure

```
EEW-Sensor-Firmware-and-UI/
├── backend/
│   ├── main.py              # FastAPI application entry point
│   ├── sensor.py            # Sensor hardware abstraction & data pipeline
│   ├── database.py          # SQLite data persistence layer
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── main.jsx         # React entry point
│   │   ├── App.jsx          # Router & layout setup
│   │   ├── TimeZoneContext.jsx  # Global timezone state provider
│   │   ├── index.css        # Tailwind CSS v4 theme
│   │   ├── components/
│   │   │   ├── Layout.jsx   # Main layout wrapper
│   │   │   ├── Sidebar.jsx  # Navigation sidebar
│   │   │   └── LiveChart.jsx # Real-time uPlot waveform charts
│   │   └── views/
│   │       ├── Dashboard.jsx # Main telemetry dashboard
│   │       ├── Export.jsx    # CSV data export page
│   │       ├── Settings.jsx  # UDP target & location config
│   │       ├── Analysis.jsx  # Placeholder for future analysis
│   │       └── Expanded.jsx  # Full-screen chart view
│   ├── dist/                 # Pre-built production bundle
│   ├── package.json          # Node.js dependencies
│   ├── vite.config.js        # Vite dev server & proxy config
│   ├── tailwind.config.js    # Tailwind CSS configuration
│   └── index.html            # HTML template
├── ADXL354.py                # Legacy standalone firmware (deprecated)
├── setup_service.sh          # Systemd auto-start installer script
├── .gitignore
└── README.md                 # This file
```

---

## Module Descriptions

### Backend Modules

#### `main.py` — FastAPI Application Server

The central server that ties all backend components together.

| Feature | Details |
|---------|---------|
| **Lifespan Management** | Initializes database, starts sensor thread, runs hourly data cleanup |
| **REST API** | `GET/POST /api/settings` — UDP target & location config |
| | `GET /api/system_status` — CPU, disk, uptime, IP, SPS stats |
| | `GET /api/export?start=&end=` — CSV data export |
| **WebSocket** | `WS /ws/stream` — Real-time sample stream (100 SPS) |
| **Static Serving** | Serves the React `dist/` build for single-binary deployment |
| **CORS** | Allows all origins for LAN access |

#### `sensor.py` — Hardware Abstraction Layer

Manages the ADXL354 accelerometer via three SPI-connected 24-bit ADCs.

| Class | Purpose |
|-------|---------|
| `MockSensor` | Generates random data for development on non-Pi machines (auto-selected on Windows) |
| `RealSensor` | Full hardware driver: GPIO control, SPI communication, ADC initialization, zero-level calibration, voltage-to-m/s² conversion |
| `SensorManager` | Orchestrates the acquisition loop: reads at 100 SPS, pushes samples to WebSocket subscribers, batches to SQLite, relays via UDP, tracks SPS stats |

**Key Parameters:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `CS_PINS` | `[35, 33, 36]` | GPIO chip-select pins for Z, X, Y ADCs |
| `DRDY_PINS` | `[11, 15, 13]` | GPIO data-ready pins |
| `VREF_ADCS` | `1.8V` | ADC reference voltage |
| `FULL_SCALE` | `8388607` | 24-bit ADC max code (2²³ - 1) |
| `ACC_SENSITIVITY_V_PER_G` | `0.4 V/g` | ADXL354 sensitivity |
| `SAMPLES_PER_PACKET` | `25` | Samples per UDP packet |
| `SAMPLE_INTERVAL` | `10 ms` | Target 100 SPS timing |

#### `database.py` — SQLite Persistence

| Function | Description |
|----------|-------------|
| `init_db()` | Creates `sensor_data` and `settings` tables with default values |
| `insert_batch(records)` | Bulk inserts `(timestamp, z, x, y)` tuples |
| `cleanup_old_data()` | Deletes records older than 24 hours |
| `get_data_for_export(start, end)` | Retrieves time-ranged data for CSV export |
| `get_settings()` / `update_settings()` | CRUD for UDP targets and geolocation |

---

### Frontend Modules

Built with **React 19**, **Tailwind CSS v4**, **uPlot** for charts, and **Vite** as the build tool.

#### Components

| Component | File | Description |
|-----------|------|-------------|
| `Layout` | `Layout.jsx` | Flex container with sidebar + main content area |
| `Sidebar` | `Sidebar.jsx` | Navigation bar with links to Dashboard, Export, Analysis, Settings |
| `LiveChart` | `LiveChart.jsx` | Real-time waveform visualization using uPlot. Renders 3 synchronized channel plots (ENZ, ENN, ENE) with a 5-second rolling window, pause/resume, and expanded view |
| `ChannelPlot` | `LiveChart.jsx` | Individual channel plot with auto-scaling Y axis, timezone-aware X axis labels, and latest value display |

#### Views

| View | Route | Description |
|------|-------|-------------|
| `Dashboard` | `/dashboard` | Main telemetry page: device details, live charts, network status, CPU/disk usage, server actions |
| `Export` | `/export` | Time-range selector with timezone-aware datetime pickers → CSV download |
| `Settings` | `/settings` | Configure sensor latitude/longitude and UDP relay targets (add/remove IP:port pairs) |
| `Analysis` | `/analysis` | Placeholder for future trigger log analysis |
| `Expanded` | `/expanded` | Full-screen chart view (opens in new tab) |

#### Context Providers

| Provider | Description |
|----------|-------------|
| `TimeZoneContext` | Global timezone selector with `localStorage` persistence. Available timezones: UTC, US East/West, London, Tokyo, Colombo, Auckland |

---

### Legacy Firmware

#### `ADXL354.py` (Root Directory)

The **original standalone** sensor firmware — predates the FastAPI architecture. Reads the same hardware, streams data via UDP only, with no web UI. **This file is superseded by `backend/sensor.py`** but is kept for reference.

---

### Deployment Scripts

#### `setup_service.sh`

A bash script that:
1. Validates it's run from the project root
2. Checks that a Python virtual environment exists
3. Creates a systemd service file (`eew-sensor.service`)
4. Sets correct file permissions
5. Enables and starts the service for boot autorun

---

## Hardware Requirements

| Component | Specification |
|-----------|--------------|
| **SBC** | Raspberry Pi 3 Model B (4GB+ RAM recommended) |
| **Power** | 5V 3A USB-C (official Raspberry Pi power supply recommended) |
| **Storage** | 8GB+ microSD (Class 10 / A2 recommended) |
| **Network** | Ethernet or Wi-Fi for dashboard access |

---

## Wiring Diagram

### GPIO Pin Mapping (BOARD Numbering)

| Function | GPIO Pin (BOARD) | Connected To |
|----------|-----------------|--------------|
| SPI MOSI | Pin 19 | ADC DIN (all 3) |
| SPI MISO | Pin 21 | ADC DOUT (all 3) |
| SPI SCLK | Pin 23 | ADC SCLK (all 3) |
| CS - Z Axis | Pin 35 | ADC 0 CS |
| CS - X Axis | Pin 33 | ADC 1 CS |
| CS - Y Axis | Pin 36 | ADC 2 CS |
| DRDY - Z | Pin 11 | ADC 0 DRDY |
| DRDY - X | Pin 15 | ADC 1 DRDY |
| DRDY - Y | Pin 13 | ADC 2 DRDY |
| Self-Test 1 | Pin 16 | ADXL354 ST1 |
| Self-Test 2 | Pin 18 | ADXL354 ST2 |
| Standby | Pin 22 | ADXL354 STBY |

---

## Software Prerequisites

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.9+ | Backend runtime |
| Node.js | 18+ | Frontend build toolchain |
| npm | 9+ | Package management |
| pip | 21+ | Python package management |

---

## Development Setup (Windows / Mac / Linux PC)

The system includes a **mock sensor** that auto-activates on non-Raspberry Pi machines, allowing full UI development without hardware.

### 1. Clone the Repository

```bash
git clone https://github.com/gssamuditha/EEW-Sensor-Firmware-and-UI.git
cd EEW-Sensor-Firmware-and-UI
```

### 2. Backend Setup

```bash
# Create and activate virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / Mac
source .venv/bin/activate

# Install dependencies (skip Pi-specific packages on dev machines)
pip install fastapi uvicorn[standard] websockets pydantic psutil
```

### 3. Frontend Setup

```bash
cd frontend
npm install
```

### 4. Run in Development Mode

**Terminal 1 — Backend:**
```bash
cd backend
python main.py
# Server starts at http://localhost:8000
```

**Terminal 2 — Frontend (with hot reload):**
```bash
cd frontend
npm run dev
# Vite dev server at http://localhost:5173 (proxies API to :8000)
```

Open `http://localhost:5173` in your browser. The mock sensor will generate random acceleration data.

---

## Professional Deployment (CI/CD Pipeline)

> This is the **recommended way to deploy** the EEW Sensor to production units. The Raspberry Pi receives only a compiled binary — no Python source code is ever copied to the device.

### How it works

```
Your PC  →  git push --tags v1.2.3  →  GitHub (private repo)
                                             │
                                   GitHub Actions CI/CD
                                   ┌─────────────────────┐
                                   │ 1. npm run build     │
                                   │    (React → dist/)   │
                                   │ 2. Nuitka compile    │
                                   │    (Python → ARM64   │
                                   │     binary)          │
                                   │ 3. dpkg-deb package  │
                                   │ 4. GitHub Release    │
                                   └─────────────────────┘
                                             │
                                   eew-sensor_1.2.3_arm64.deb
                                             │
Raspberry Pi 3 (64-bit OS)  ←  auto_update.sh downloads & installs .deb
├── /opt/eew-sensor/backend/run_server   ← compiled ARM64 binary
├── /opt/eew-sensor/frontend/            ← built React app
└── /opt/eew-sensor/backend/eew_sensor.db ← preserved user data
```

### Publishing a release

On your development PC, tag a commit and push:

```bash
git tag v1.2.3
git push origin v1.2.3
```

GitHub Actions will automatically:
1. Build the React frontend (`npm run build`)
2. Compile the Python backend to a native ARM64 binary using Nuitka (inside a Docker ARM64 container via QEMU — no cross-compiler needed)
3. Package everything as `eew-sensor_1.2.3_arm64.deb`
4. Create a GitHub Release with the `.deb` and a SHA256 checksum file

> **First build time**: 20–40 minutes (Nuitka compiles scipy/numpy/obspy under QEMU emulation). Subsequent builds are faster thanks to ccache.

### First-time Pi installation

Flash **64-bit Raspberry Pi OS Lite** (arm64) and SSH in. Then run:

```bash
curl -fsSL https://raw.githubusercontent.com/gssamuditha/EEW-Sensor-Firmware-and-UI/main/setup_service.sh | bash
```

This single command:
- Downloads the latest `.deb` from GitHub Releases
- Verifies the SHA256 checksum
- Installs with `dpkg -i` (systemd hooks start the service automatically)
- Schedules the OTA auto-updater via cron

**No git, Python, pip, or npm required on the Pi.**

### OTA updates

Sensors check for new releases every 30 minutes automatically (configurable in `auto_update.sh` via `DESIRED_CRON`). The update process:
1. Queries GitHub Releases API for the latest tag
2. Downloads the new `.deb` and verifies SHA256
3. Backs up the database and saves all user settings
4. Installs with `dpkg -i` (service restarts automatically via postinst)
5. Restores user settings and runs a database integrity check
6. Rolls back to the previous installation if anything fails

### Verify no source code on the device

```bash
ls /opt/eew-sensor/backend/    # should show run_server binary + .so files, no .py files
ls /opt/eew-sensor/frontend/   # should show index.html + assets/, no .jsx/.tsx files
```

---

## Raspberry Pi Setup

### 1. OS Installation

1. Download **Raspberry Pi OS Lite (64-bit)** from [raspberrypi.com/software](https://www.raspberrypi.com/software/)
2. Flash to microSD using **Raspberry Pi Imager**
3. In Imager settings, configure:
   - Hostname: `eew-sensor` (or your choice)
   - Enable SSH
   - Configure Wi-Fi (if not using Ethernet)
   - Set username/password
4. Boot the Pi and SSH in:
   ```bash
   ssh pi@eew-sensor.local
   ```

### 2. Enable SPI Interface

```bash
sudo raspi-config
```

Navigate to: **Interface Options → SPI → Enable**

Reboot:
```bash
sudo reboot
```

Verify SPI is active:
```bash
ls /dev/spidev*
# Should show: /dev/spidev0.0  /dev/spidev0.1
```

### 3. Clone and Install

```bash
# Install system dependencies
sudo apt update
sudo apt install -y python3-venv python3-pip git nodejs npm

# Clone the project
git clone https://github.com/gssamuditha/EEW-Sensor-Firmware-and-UI.git
cd EEW-Sensor-Firmware-and-UI

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install ALL dependencies (including Pi-specific packages)
pip install -r backend/requirements.txt
```

### 4. Build the Frontend

```bash
cd frontend
npm install
npm run build    # Output goes to frontend/dist/
cd ..
```

> The build step produces a static `dist/` folder that the FastAPI backend serves directly — no separate frontend server is needed in production.

### 5. Manual Run (Test)

```bash
source .venv/bin/activate
cd backend
python main.py
```

Open a browser on any device on the same network and navigate to:
```
http://<pi-ip-address>:8000
```

The sensor will:
1. Initialize GPIO pins and SPI bus
2. Wake the ADXL354 from standby (~10 seconds)
3. Settle GPIO pins (~1 second)
4. Run zero-level calibration (~100 seconds)
5. Begin streaming at 100 samples/sec

---

## Configure Autorun on Boot

### Using the Setup Script

The included `setup_service.sh` automates the entire systemd configuration:

```bash
# From the project root directory on the Pi
cd /home/pi/EEW-Sensor-Firmware-and-UI
chmod +x setup_service.sh
./setup_service.sh
```

This script will:
- Create a systemd service file at `/etc/systemd/system/eew-sensor.service`
- Set the working directory to `backend/`
- Run uvicorn on **port 80** (standard HTTP — no port number needed in browser)
- Grant the `CAP_NET_BIND_SERVICE` capability (allows non-root binding to port 80)
- Configure `Restart=always` with a 5-second delay
- Enable the service to start on every boot

After running, the dashboard is accessible at:
```
http://cl.local
```

### Manual systemd Configuration

If you prefer to set things up manually:

**1. Create the service file:**

```bash
sudo nano /etc/systemd/system/eew-sensor.service
```

**2. Paste the following content:**

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

> ⚠️ **Important:** Adjust `User`, `WorkingDirectory`, and `ExecStart` paths to match your actual installation directory and username.

**3. Enable and start:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable eew-sensor.service
sudo systemctl start eew-sensor.service
```

### Managing the Service

| Action | Command |
|--------|---------|
| Check status | `sudo systemctl status eew-sensor.service` |
| View live logs | `sudo journalctl -u eew-sensor.service -f` |
| Stop the service | `sudo systemctl stop eew-sensor.service` |
| Restart the service | `sudo systemctl restart eew-sensor.service` |
| Disable autorun | `sudo systemctl disable eew-sensor.service` |
| View last 100 log lines | `sudo journalctl -u eew-sensor.service -n 100` |

---

## API Reference

### REST Endpoints

| Method | Endpoint | Description | Parameters |
|--------|----------|-------------|------------|
| `GET` | `/api/settings` | Get current configuration | — |
| `POST` | `/api/settings` | Update configuration | JSON body: `{ targets: [{ip, port}], latitude, longitude }` |
| `GET` | `/api/system_status` | System health metrics | — |
| `GET` | `/api/export` | Download CSV data | Query: `start` (Unix epoch), `end` (Unix epoch) |

### WebSocket

| Endpoint | Description | Message Format |
|----------|-------------|----------------|
| `WS /ws/stream` | Real-time acceleration data | `{ t: float, ENZ: float, ENN: float, ENE: float }` |

**Channel naming convention:**
- `ENZ` — Vertical (Z) axis acceleration (m/s²)
- `ENN` — North (X) axis acceleration (m/s²)
- `ENE` — East (Y) axis acceleration (m/s²)

---

## Configuration

### Settings Page (Web UI)

Access `http://<pi-ip>/settings` to configure:

- **Sensor Location:** Latitude and longitude (stored in SQLite, used for metadata)
- **UDP Targets:** One or more IP:Port pairs where sensor packets are relayed in real-time

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PYTHONUNBUFFERED` | `1` (set by systemd) | Ensures log output appears immediately in `journalctl` |

### Sensor Parameters (Code-Level)

Edit `backend/sensor.py` to modify:

| Parameter | Location | Default | Description |
|-----------|----------|---------|-------------|
| `VREF_ADCS` | Line 14 | `[1.8, 1.8, 1.8]` | ADC reference voltages |
| `ACC_SENSITIVITY_V_PER_G` | Line 22 | `0.4` | ADXL354 sensitivity (V/g) |
| `calibration_time_sec` | `calibrate()` | `100` | Zero-level calibration duration (seconds) |
| `SAMPLES_PER_PACKET` | Line 17 | `25` | Samples batched per UDP packet |

---

## Troubleshooting

### Service won't start

```bash
# Check logs for errors
sudo journalctl -u eew-sensor.service -n 50

# Common issues:
# 1. Virtual environment not found — ensure .venv exists
# 2. Frontend not built — run npm run build in frontend/
# 3. SPI not enabled — run sudo raspi-config
# 4. Permission denied — check file ownership
sudo chown -R pi:pi /home/pi/EEW-Sensor-Firmware-and-UI
```

### DRDY Timeout Errors

```
Sensor read error: DRDY timeout on ADC 0
```

This means the ADC data-ready pin didn't assert within 150ms. Check:
- Wiring connections (especially DRDY and CS pins)
- SPI is enabled (`ls /dev/spidev*`)
- ADC power supply is stable

### Dashboard Shows "Waiting for data..."

- The sensor takes ~2 minutes to initialize and calibrate on first boot
- Check that the backend is running: `sudo systemctl status eew-sensor.service`
- Verify WebSocket connection in browser DevTools → Network → WS tab

### Can't Access Dashboard from Another Device

- Ensure both devices are on the same network
- Log in to the Pi and check the logs: `sudo journalctl -u eew-sensor.service -f`
- Check the Pi's IP: `hostname -I`
- Verify the service is listening: `ss -tlnp | grep 80`
- Try accessing by IP directly: `http://192.168.x.x`

---

## License

This project is developed by CRISiS Lab and SLIIT for research purposes.
