# EEW Sensor - UDP Latency Evaluation Guide

## Overview

This guide documents the scientific methodology and toolchain for evaluating
end-to-end timing delays in the EEW sensor UDP datacast pipeline over ZeroTier.

---

## System Architecture

`
[ADXL354BEZ Accelerometer]
        |  SPI @ 200 Hz (oversampled)
        v
[ADS1220 ADC]  ->  [Raspberry Pi 4 - sensor.py]
                         |
                         |  Software PLL (chrony-disciplined UTC)
                         |  Anti-aliasing IIR + decimation -> 100 SPS
                         |  Buffer 25 samples -> 1 UDP packet / 250 ms
                         |
                         v
                [ZeroTier VPN Tunnel]
                   |           |
                Relay (DERP)  P2P (direct punch-through)
                         |
                         v
               [PC / Server - udp_latency_analyzer.py]
                  time.time() immediately on recvfrom()
`

### Delay Budget (worst-case path)

| Component | Min | Typical | Max |
|-----------|-----|---------|-----|
| Firmware buffer accumulation | 0 ms | 125 ms | 250 ms |
| ZeroTier P2P | 2 ms | 15 ms | 50 ms |
| ZeroTier relay (DERP) | 20 ms | 80 ms | 200 ms |
| OS receive jitter (PC) | 0 ms | 2 ms | 10 ms |
| NTP clock offset bias | varies | <10 ms | varies |
| **Total (P2P path)** | **~2 ms** | **~140 ms** | **~310 ms** |
| **Total (relay path)** | **~20 ms** | **~205 ms** | **~460 ms** |

---

## Tools

| Script | Purpose |
|--------|---------|
| udp_latency_analyzer.py | Main scientific receiver - live dashboard, CSV, figures |
| clock_offset_probe.py | Cristian algorithm clock offset estimator (run on PC) |
| clock_echo_server.py | Echo server counterpart (run on RPi) |
| latency_analysis.py | Offline analysis - publication-quality figures |

---

## Quick Start

### Step 1 - Install dependencies on your PC

`powershell
pip install numpy matplotlib scipy windows-curses
`

### Step 2 - Ensure NTP is synchronized

**On PC (Windows):**
`powershell
w32tm /query /status
# Should show Phase Offset < 50 ms, ideally < 10 ms

# Force resync if needed:
w32tm /resync /force
`

**On RPi:**
`ash
chronyc tracking
# Look for System time offset < 10 ms
`

### Step 3 - Run the analyzer

Make sure your EEW sensor is configured to UDP-cast to your PC ZeroTier IP, port 2098.

`powershell
# With live curses dashboard (recommended):
python udp_latency_analyzer.py

# Plain stdout (fallback):
python udp_latency_analyzer.py --no-dashboard

# Fixed 5-minute run:
python udp_latency_analyzer.py --duration 300
`

**Output files** (saved in current directory):
- udp_latency_data_<TIMESTAMP>.csv     - raw per-packet measurements
- udp_latency_report_<TIMESTAMP>.txt   - statistical summary
- udp_latency_<TIMESTAMP>_owd.png      - OWD time series
- udp_latency_<TIMESTAMP>_hist.png     - histogram + log-normal fit
- udp_latency_<TIMESTAMP>_cdf.png      - empirical CDF
- udp_latency_<TIMESTAMP>_jitter.png   - jitter time series

---

## Step 4 - Clock Offset Verification (Cristian Algorithm)

This cross-checks your NTP synchronization without relying on NTP itself.

**On RPi:**
`ash
python clock_echo_server.py
`

**On PC:**
`powershell
python clock_offset_probe.py --host <zerotier_ip_of_rpi>
`

Runs 100 UDP echo probes and outputs the estimated clock offset.
If offset > 20 ms, correct your OWD values:
`powershell
python latency_analysis.py data.csv --clock-offset 23.5
`

---

## Step 5 - Offline Analysis

`powershell
python latency_analysis.py udp_latency_data_<TIMESTAMP>.csv

# With clock offset correction:
python latency_analysis.py data.csv --clock-offset <offset_ms>

# With warmup trimming:
python latency_analysis.py data.csv --trim-start 10 --output-dir results/
`

Generates 5 figures:
1. OWD time series with rolling mean + percentile lines
2. OWD histogram with log-normal distribution fit
3. Empirical CDF (P50/P95/P99 annotated)
4. Jitter (PDV) time series
5. Box-per-minute whisker plot

---

## Loopback Self-Test

`powershell
python udp_latency_analyzer.py --selftest --duration 30 --no-dashboard
`

Expected loopback OWD ~250 ms (simulated firmware buffer delay, not real network).

---

## CSV Column Reference

| Column | Description |
|--------|-------------|
| seq | Sequential packet counter |
| recv_utc | PC receive time (Unix epoch, seconds, us precision) |
| packet_ts | Packet origin timestamp from sensor (UTC epoch) |
| channel | Seismic channel: ENZ / ENN / ENE |
| owd_ms | One-Way Delay in milliseconds |
| jitter_ms | RFC 3550 EWMA jitter (Packet Delay Variation) |
| n_samples | Number of acceleration samples in this packet (should be 25) |
| clock_offset_ms | NTP offset at capture start |
| is_loss_gap | 1 if a gap was detected before this packet |

---

## Scientific Interpretation

### What OWD includes

OWD = t_recv_pc - packet_timestamp_rpi

The packet_timestamp is the first sample scheduled ADC acquisition time
from the Software PLL (sensor.py ~line 530: t = next_loop_utc).

OWD = firmware_buffering + network_transit + OS_recv_jitter

Since each packet buffers 25 samples at 100 SPS, firmware buffering
contributes 0 to 250 ms (mean ~125 ms).

### Jitter (PDV)

RFC 3550 EWMA formula:
  J_n = J_(n-1) + 0.0625 * (|OWD_n - OWD_(n-1)| - J_(n-1))

High jitter (>30 ms) suggests OS scheduling variability, ZeroTier path
switching, or network congestion.

### Packet Loss Detection

Loss flagged when consecutive packet timestamp gap > 600 ms (2.4x expected 250 ms).

---

## ZeroTier Path Check

`ash
zerotier-cli peers
`

P2P path: 5-30 ms added latency.
Relay (DERP): 30-200 ms added latency.

To force P2P: ensure UDP port 9993 is open on both firewalls.

---

## Recommended Research Test Protocol

1. **Baseline (loopback):** --selftest --duration 60
2. **LAN baseline (no ZeroTier):** Direct WiFi, 300s
3. **ZeroTier capture:** Minimum 300s, recommended 3600s (1 hour)
4. **Diurnal variation:** --duration 86400 --no-dashboard (24h run)
5. **Post-analysis:** python latency_analysis.py <csv> --clock-offset <ms>

Report should include: mean, std, P50, P95, P99, loss rate, distribution fit,
jitter mean, ZeroTier path type.
