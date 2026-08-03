import time
import socket
import threading
import asyncio
import random
import sys
import json


from filters import BandpassFilter, minmax_downsample, FILTER_PRESETS
import numpy as np
from mseed_writer import mseed_writer

def process_historical_data_task(start_time: float, end_time: float, low_hz: float, high_hz: float, target_display_points: int = 4000, settings_snapshot: dict = None) -> dict:
    """
    Top-level standalone function to query miniSEED and apply DSP.
    Designed to run in a separate ProcessPoolExecutor to avoid blocking the GIL.
    """
    import numpy as np
    from mseed_writer import read_waveform_range
    from filters import BandpassFilter, minmax_downsample
    
    window_seconds = end_time - start_time
    
    # ObsPy returns a Stream object with Traces
    st = read_waveform_range(start_time, end_time, settings=settings_snapshot)
    
    if not st or len(st) == 0:
        return {
            "timestamps": [],
            "samples": {ch: [] for ch in CHANNEL_NAMES},
            "sps": 100,
            "window_seconds": window_seconds,
        }
        
    from obspy import UTCDateTime
    st.trim(starttime=UTCDateTime(start_time), endtime=UTCDateTime(end_time), pad=True, fill_value=0)

    raw = {}
    timestamps = None
    
    # For each expected channel, extract data, detrend, and scale
    for ch in CHANNEL_NAMES:
        # channel codes in miniSEED are usually 3 chars (e.g. ENZ)
        tr = st.select(channel=ch)
        if len(tr) > 0:
            # Merge in case there are gaps
            tr.merge(method=1, fill_value='interpolate')
            t_obj = tr[0]
            
            # Extract raw counts and timestamps
            counts = t_obj.data.astype(np.float64)
            # Ensure timestamps aligns with the longest trace
            if timestamps is None or len(t_obj.times('timestamp')) > len(timestamps):
                timestamps = t_obj.times('timestamp')
                
            # Detrend (remove mean) to bypass need for exact RAW_COUNTS_ZERO at boot
            if len(counts) > 0:
                counts = counts - np.mean(counts)
                
            # Scale to m/s²
            ms2 = counts * INSTRUMENT_SENSITIVITY_MS2_PER_COUNT
            raw[ch] = ms2
        else:
            raw[ch] = np.array([])
            
    # If no data found, return empty
    if timestamps is None or len(timestamps) == 0:
        return {
            "timestamps": [],
            "samples": {ch: [] for ch in CHANNEL_NAMES},
            "sps": 100,
            "window_seconds": window_seconds,
        }

    filtered = {}
    for ch in CHANNEL_NAMES:
        if len(raw[ch]) < 13:
            filtered[ch] = raw[ch]
        else:
            filt = BandpassFilter(low_hz=low_hz, high_hz=high_hz, fs=100.0, order=4)
            filtered[ch] = filt.apply_zerophase(raw[ch])

    result_samples = {}
    out_t = []
    for ch in CHANNEL_NAMES:
        if len(filtered[ch]) > 0:
            # slice arrays to match shortest length just in case they differ by 1 sample
            min_len = min(len(timestamps), len(filtered[ch]))
            ds_t, ds_v = minmax_downsample(timestamps[:min_len], filtered[ch][:min_len], target_display_points)
            result_samples[ch] = ds_v.tolist()
            if len(out_t) == 0:
                out_t = ds_t.tolist()
        else:
            result_samples[ch] = []

    return {
        "timestamps": out_t,
        "samples": result_samples,
        "sps": 100,
        "unit": "m/s²",
        "window_seconds": window_seconds,
        "raw_sample_count": len(timestamps),
        "display_points": len(out_t),
    }

# === ADC Config ===
CS_PINS = [35, 33, 36]        # Acc Z, Acc X, Acc Y
DRDY_PINS = [11, 15, 13]
VREF_ADCS = [1.8, 1.8, 1.8]
FULL_SCALE = 8388607
CHANNEL_NAMES = ['ENZ', 'ENN', 'ENE']
SAMPLES_PER_PACKET = 25
SAMPLE_INTERVAL = 0.0035  # 100 sps

# === Accelerometer Settings ===
ACC_ZERO_VOLTAGES = [0.0, 0.0, 0.0]  # Calibrated zero voltages (V) per axis
RAW_COUNTS_ZERO = [0, 0, 0]          # Calibrated zero level in raw ADC counts per axis
ACC_SENSITIVITY_V_PER_G = 0.4        # ADXL354BEZ ±2g range: 400 mV/g (ratiometric to 1.8V)
G_TO_MS2 = 9.80665                   # Standard gravity (m/s²)

# === Instrument Sensitivity Constants (for StationXML response file) ===
# Chain: ADXL354BEZ → ADA4522 RC LPF → ADS1220 (Gain=1, Vref=1.8V, 24-bit)
#
# Derivation (counts → m/s²):
#   voltage  = raw_counts × VREF / FULL_SCALE
#   g_val    = voltage / SENSITIVITY_V_per_g
#   ms2      = g_val × G_TO_MS2
#   ∴  ms2   = raw_counts × (VREF × G_TO_MS2) / (FULL_SCALE × SENSITIVITY_V_per_g)
#
# INSTRUMENT_SENSITIVITY_MS2_PER_COUNT
#   = (VREF × G_TO_MS2) / (FULL_SCALE × SENSITIVITY_V_per_g)
#   = (1.8 × 9.80665)  / (8388607 × 0.4)
#   ≈ 5.261e-6 m/s² / count
#
# Inverse  (overall instrument sensitivity: m/s² → counts):
#   = FULL_SCALE × SENSITIVITY_V_per_g / (VREF × G_TO_MS2)
#   ≈ 190,067 counts / (m/s²)
INSTRUMENT_SENSITIVITY_MS2_PER_COUNT = (VREF_ADCS[0] * G_TO_MS2) / (FULL_SCALE * ACC_SENSITIVITY_V_PER_G)

# === Sensor Control Pins ===
ST1 = 16
ST2 = 18
STBY = 22

class MockSensor:
    def __init__(self):
        self.sample_interval = 0.01  # 100 sps
        self.channels = ['ENZ', 'ENN', 'ENE']
        
    def init_sensor(self):
        print("Mock sensor initialized")
        
    def calibrate(self, calibration_time_sec=1):
        print("Mock sensor calibrated")
        time.sleep(1)
        
    def read_all(self):
        # Generate realistic-looking acceleration noise in m/s²
        t = time.time()
        z = 0.5 * random.random() + 0.1
        x = 0.5 * random.random() - 0.2
        y = 0.5 * random.random() + 0.05
        return (t, z, x, y)

    def read_all_raw(self):
        """Return mock signed 24-bit ADC counts (simulates what raw hardware returns)."""
        # Timestamp is no longer generated here — the SensorManager hw_loop
        # computes all sample times from a monotonic counter anchored to NTP.
        z = int((0.5 * random.random() + 0.1) / INSTRUMENT_SENSITIVITY_MS2_PER_COUNT)
        x = int((0.5 * random.random() - 0.2) / INSTRUMENT_SENSITIVITY_MS2_PER_COUNT)
        y = int((0.5 * random.random() + 0.05) / INSTRUMENT_SENSITIVITY_MS2_PER_COUNT)
        return (z, x, y)


class RealSensor:
    def __init__(self):
        import spidev
        import RPi.GPIO as GPIO
        self.spidev = spidev
        self.GPIO = GPIO
        
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 4000000
        self.spi.mode = 0b01
        
    def init_sensor(self):
        self.GPIO.setwarnings(False)
        self.GPIO.setmode(self.GPIO.BOARD)

        self.GPIO.setup(ST1, self.GPIO.OUT)
        self.GPIO.setup(ST2, self.GPIO.OUT)
        self.GPIO.setup(STBY, self.GPIO.OUT)

        self.GPIO.output(ST1, self.GPIO.LOW)
        self.GPIO.output(ST2, self.GPIO.LOW)
        self.GPIO.output(STBY, self.GPIO.HIGH)
        time.sleep(10)

        for cs in CS_PINS:
            self.GPIO.setup(cs, self.GPIO.OUT)
            self.GPIO.output(cs, self.GPIO.HIGH)

        for drdy in DRDY_PINS:
            self.GPIO.setup(drdy, self.GPIO.IN, pull_up_down=self.GPIO.PUD_UP)
            
        time.sleep(1)
        self._adc_init_all()
        for _ in range(5):
            self._start_conversion_all()
            for i in range(3):
                try:
                    self._read_adc(i)
                except Exception:
                    pass
            time.sleep(0.01)
            
    def _adc_init_all(self):
        for i in range(3):
            self.GPIO.output(CS_PINS[i], self.GPIO.LOW)
            time.sleep(0.000001)
            self.spi.xfer2([0x06])
            time.sleep(0.1)
            # Reg 0: 0x81 (AIN0/AIN1, PGA disabled)
            # Reg 1: 0x80 (330 SPS, Normal mode, Single-shot) 
            # Reg 2: 0x40 (VREF external)
            self.spi.xfer2([0x42, 0x81, 0x80, 0x40])
            self.spi.xfer2([0x08])
            self.GPIO.output(CS_PINS[i], self.GPIO.HIGH)
            time.sleep(0.1)

    def _start_conversion_all(self):
        for cs in CS_PINS:
            self.GPIO.output(cs, self.GPIO.LOW)
        self.spi.xfer2([0x08])
        for cs in CS_PINS:
            self.GPIO.output(cs, self.GPIO.HIGH)

    def _read_adc(self, i, return_raw=False):
        self.GPIO.output(CS_PINS[i], self.GPIO.LOW)
        start = time.time()
        while self.GPIO.input(DRDY_PINS[i]):
            if time.time() - start > 0.15:
                raise TimeoutError(f"DRDY timeout on ADC {i}")
            pass
        data = self.spi.xfer2([0x00, 0x00, 0x00])
        self.GPIO.output(CS_PINS[i], self.GPIO.HIGH)
        raw = (data[0] << 16) | (data[1] << 8) | data[2]
        if raw & (1 << 23):
            raw -= (1 << 24)
        if return_raw:
            return raw
        voltage = (raw / FULL_SCALE) * VREF_ADCS[i]
        return voltage
        
    def calibrate(self, calibration_time_sec=100):
        print(f"Starting accelerometer zero-level calibration for {calibration_time_sec} seconds...")
        samples_v   = [[], [], []]  # Voltage samples per axis
        samples_raw = [[], [], []]  # Raw ADC count samples per axis
        start_time = time.time()
        while time.time() - start_time < calibration_time_sec:
            self._start_conversion_all()
            for axis in range(3):
                raw_cnt = self._read_adc(axis, return_raw=True)
                voltage = (raw_cnt / FULL_SCALE) * VREF_ADCS[axis]
                samples_v[axis].append(voltage)
                samples_raw[axis].append(raw_cnt)
            time.sleep(SAMPLE_INTERVAL)

        for i in range(3):
            ACC_ZERO_VOLTAGES[i] = sum(samples_v[i]) / len(samples_v[i])
            RAW_COUNTS_ZERO[i]   = int(round(sum(samples_raw[i]) / len(samples_raw[i])))

        print("Calibration complete.")
        print(f"Zero voltages  — Z: {ACC_ZERO_VOLTAGES[0]:.6f} V, X: {ACC_ZERO_VOLTAGES[1]:.6f} V, Y: {ACC_ZERO_VOLTAGES[2]:.6f} V")
        print(f"Zero raw counts— Z: {RAW_COUNTS_ZERO[0]}, X: {RAW_COUNTS_ZERO[1]}, Y: {RAW_COUNTS_ZERO[2]}")

    def read_all(self):
        """Read all axes and return corrected acceleration in m/s²."""
        self._start_conversion_all()
        readings = []
        for i in range(3):
            voltage = self._read_adc(i)
            zero_voltage = ACC_ZERO_VOLTAGES[i]
            g_val = (voltage - zero_voltage) / ACC_SENSITIVITY_V_PER_G
            ms2 = g_val * G_TO_MS2
            readings.append(ms2)
        return (time.time(), readings[0], readings[1], readings[2])

    def read_all_raw(self):
        """Read all axes and return TRUE signed 24-bit ADC counts (no offset removed).

        The zero offset (RAW_COUNTS_ZERO) is NOT subtracted here — raw counts include
        the full DC bias from gravity loading and manufacturing tolerances. This matches
        the Raspberry Shake behaviour: unmodified hardware counts are sent over UDP,
        and the DC offset is removed by the receiver (e.g. tr.detrend('demean') before
        ObsPy remove_response()). The offset values are documented in the StationXML
        <Comment> elements for reference.
        """
        self._start_conversion_all()
        readings = []
        for i in range(3):
            raw_cnt = self._read_adc(i, return_raw=True)
            readings.append(raw_cnt)  # NO subtraction — true hardware counts
        # Timestamp is NOT included here — the SensorManager hw_loop computes
        # all sample times from a monotonic counter anchored to NTP, eliminating
        # per-sample time.time() jitter entirely.
        return (readings[0], readings[1], readings[2])

class SensorManager:
    def __init__(self, use_mock=False):
        self.use_mock = use_mock
        if use_mock:
            self.sensor = MockSensor()
        else:
            self.sensor = RealSensor()
            
        self.running = False
        self.thread = None
        self.subscribers = []  # asyncio queues (raw stream)
        self._sub_lock = threading.Lock()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.hardware_sps = 0
        self.avg_sps = 0
        self._ws_batches_sent = 0
        self._ws_batches_dropped = 0

        # --- Analysis / Filter state ---
        self.analysis_subscribers = []  # asyncio queues (filtered stream)
        self._analysis_lock = threading.Lock()
        # Per-axis bandpass filters (default: earthquake band 0.1–20 Hz)
        self._filters = {
            ch: BandpassFilter(low_hz=0.1, high_hz=20.0, fs=100.0, order=4)
            for ch in CHANNEL_NAMES
        }
        self.avg_sps = 0.0
        
        self._loop = None
        self._hw_thread = None
        self._analytics_thread = None
        
        import queue
        self._analytics_queue = queue.Queue(maxsize=1000)
        # _cached_targets: list of dicts with keys: ip, port, format ('corrected'|'raw')
        self._cached_targets = []
        self._cached_data_forwarding = True
        self._filter_lock = threading.Lock()

        # Timing state is managed entirely inside _hw_loop using the Software PLL
        # approach (time.time() + chrony discipline). No shared state needed here.
        
    def start(self, loop=None):
        if self.running:
            return
            
        self._loop = loop
        
        from database import get_settings
        settings = get_settings()
        cal_time = int(settings.get('calibration_time', 60))
        
        self.sensor.init_sensor()
        self.sensor.calibrate(calibration_time_sec=cal_time)
        self.running = True
        
        self._hw_thread = threading.Thread(target=self._hw_loop, daemon=True, name="sensor-hw")
        self._analytics_thread = threading.Thread(target=self._analytics_loop, daemon=True, name="sensor-analytics")
        self._hw_thread.start()
        self._analytics_thread.start()
        
    def stop(self):
        self.running = False
        if self._hw_thread:
            self._hw_thread.join()
        if self._analytics_thread:
            self._analytics_thread.join()
        self.sock.close()
            
    def subscribe(self, queue):
        with self._sub_lock:
            self.subscribers.append(queue)
        
    def unsubscribe(self, queue):
        with self._sub_lock:
            if queue in self.subscribers:
                self.subscribers.remove(queue)

    # --- Analysis subscriber methods ---
    def subscribe_analysis(self, queue):
        with self._analysis_lock:
            self.analysis_subscribers.append(queue)

    def unsubscribe_analysis(self, queue):
        with self._analysis_lock:
            if queue in self.analysis_subscribers:
                self.analysis_subscribers.remove(queue)

    def update_filter(self, low_hz: float, high_hz: float):
        """Update bandpass filter cutoffs. Resets real-time filter state."""
        with self._filter_lock:
            for ch in CHANNEL_NAMES:
                self._filters[ch].update_params(low_hz, high_hz)

    def get_filter_params(self) -> dict:
        """Return current filter parameters."""
        with self._filter_lock:
            return self._filters[CHANNEL_NAMES[0]].params

    def get_historical_filtered(self, start_time: float, end_time: float,
                                target_display_points: int = 4000) -> dict:
        """
        Backward compatible call. For true non-blocking, use ProcessPoolExecutor 
        with process_historical_data_task directly.
        """
        with self._filter_lock:
            high_hz = self._filters[CHANNEL_NAMES[0]].high_hz
            low_hz = self._filters[CHANNEL_NAMES[0]].low_hz
        return process_historical_data_task(start_time, end_time, low_hz, high_hz, target_display_points)
            
    def _hw_loop(self):
        """
        Strictly prioritized hardware loop for 100 SPS SPI reading and UDP sending.

        TIMING ARCHITECTURE — Software PLL via chrony-disciplined UTC clock
        -------------------------------------------------------------------
        The loop schedules each iteration against time.time() (POSIX CLOCK_REALTIME).
        On Raspberry Pi, the Linux kernel's chrony daemon continuously disciplines
        CLOCK_REALTIME to NTP via *slewing* (adjusting the clock rate by ±500 ppm),
        never by jumping.  This means time.time() IS the Software PLL output.

        By accumulating next_loop_utc on time.time(), the loop speed is automatically
        steered by chrony to match true UTC — no custom PLL code required.

        Sample timestamp:
            t = next_loop_utc   (the pre-computed UTC instant this iteration fires)
        This is the actual UTC moment the ADC conversion was commanded, with no
        per-sample syscall jitter because we use the *scheduled* time, not the
        *measured* time.

        Rate limiting:
            The spin-wait uses time.monotonic() (fast VDSO, no kernel context switch).
            We derive the equivalent monotonic target from a short-lived reference pair
            (_utc_ref, _mono_ref), refreshed every iteration to stay accurate.

        NTP step detection:
            chrony slews by default; steps only occur for large errors (e.g. at boot).
            If time.time() diverges from the expected monotonic-derived value by more
            than NTP_STEP_THRESHOLD, we treat it as an NTP step and reset the anchor.
        """
        NTP_STEP_THRESHOLD = 0.5        # seconds — anything larger is an NTP step
        target_interval    = 1.0 / 200  # 5 ms per oversampled iteration (200 Hz)

        # ── Startup: establish UTC anchor ──────────────────────────────────────
        # Take median of 5 time.time() readings to reduce OS scheduler jitter
        # on the very first sample.
        _init = sorted(time.time() for _ in range(5))
        next_loop_utc = _init[2]           # median → UTC-accurate start
        _utc_ref      = next_loop_utc
        _mono_ref     = time.monotonic()
        print(f"sensor-hw: Software PLL started. Initial UTC anchor: {next_loop_utc:.6f}", file=sys.stderr)

        udp_buffers = [[], [], []]         # m/s² per axis (corrected UDP path)
        raw_buffers  = [[], [], []]        # integer counts per axis (raw UDP path)

        total_samples = 0
        total_time    = 0
        sps_mono_ref  = time.monotonic()  # monotonic reference for SPS tracking
        sample_count  = 0

        # 2nd-Order Butterworth Low-Pass (fc=50 Hz, fs=200 Hz) — Anti-Aliasing.
        # Pure integer arithmetic; bypasses Numpy/Scipy GIL. ~1 µs per sample.
        b0, b1, b2 = 0.29289322, 0.58578644, 0.29289322
        a1, a2     = 0.0, 0.17157288

        # Per-axis IIR state
        x_hist = {'Z': [0.0, 0.0], 'X': [0.0, 0.0], 'Y': [0.0, 0.0]}
        y_hist = {'Z': [0.0, 0.0], 'X': [0.0, 0.0], 'Y': [0.0, 0.0]}

        decimate_flag = False

        while self.running:
            try:
                # Advance UTC scheduling accumulator
                next_loop_utc += target_interval

                # ── Software PLL: NTP step detection ──────────────────────────
                # Under normal chrony operation time.time() slews smoothly — no
                # jump will be detected here.  A jump > NTP_STEP_THRESHOLD means
                # a manual NTP step (e.g. chrony makestep at boot) — we reset.
                now_utc  = time.time()
                now_mono = time.monotonic()
                expected_utc = _utc_ref + (now_mono - _mono_ref)
                utc_error    = now_utc - expected_utc

                if abs(utc_error) > NTP_STEP_THRESHOLD:
                    # Large NTP step: re-anchor to current UTC
                    next_loop_utc = now_utc
                    print(
                        f"sensor-hw: NTP step detected ({utc_error:+.3f}s). "
                        f"Timing re-anchored to {now_utc:.6f}",
                        file=sys.stderr
                    )

                # Update short-lived references for spin-wait calculation
                _utc_ref  = now_utc
                _mono_ref = now_mono

                # ── Hardware Read (no timestamp — timing is handled here) ──────
                z_cnt, x_cnt, y_cnt = self.sensor.read_all_raw()

                # ── Anti-Aliasing IIR Filter (pure arithmetic, no GIL) ────────
                z_f = b0*z_cnt + b1*x_hist['Z'][0] + b2*x_hist['Z'][1] - a1*y_hist['Z'][0] - a2*y_hist['Z'][1]
                x_hist['Z'] = [z_cnt, x_hist['Z'][0]]; y_hist['Z'] = [z_f,   y_hist['Z'][0]]

                x_f = b0*x_cnt + b1*x_hist['X'][0] + b2*x_hist['X'][1] - a1*y_hist['X'][0] - a2*y_hist['X'][1]
                x_hist['X'] = [x_cnt, x_hist['X'][0]]; y_hist['X'] = [x_f,   y_hist['X'][0]]

                y_f = b0*y_cnt + b1*x_hist['Y'][0] + b2*x_hist['Y'][1] - a1*y_hist['Y'][0] - a2*y_hist['Y'][1]
                x_hist['Y'] = [y_cnt, x_hist['Y'][0]]; y_hist['Y'] = [y_f,   y_hist['Y'][0]]

                # ── Decimation: keep every 2nd → 100 SPS output ───────────────
                decimate_flag = not decimate_flag
                if not decimate_flag:

                    # ── Sample Timestamp: scheduled UTC time ─────────────────
                    # t = next_loop_utc — the NTP-disciplined UTC instant this
                    # ADC conversion was commanded.  No per-sample syscall.
                    # No synthetic counter math.  chrony provides the PLL steering.
                    t = next_loop_utc

                    # Convert filtered counts → physical units for analytics/UDP
                    z_ms2 = (z_f - RAW_COUNTS_ZERO[0]) * INSTRUMENT_SENSITIVITY_MS2_PER_COUNT
                    x_ms2 = (x_f - RAW_COUNTS_ZERO[1]) * INSTRUMENT_SENSITIVITY_MS2_PER_COUNT
                    y_ms2 = (y_f - RAW_COUNTS_ZERO[2]) * INSTRUMENT_SENSITIVITY_MS2_PER_COUNT

                    # 1. miniSEED archive (raw int32 counts — unmodified hardware data)
                    mseed_writer.enqueue(t, int(round(z_f)), int(round(x_f)), int(round(y_f)))

                    # 2. Analytics WebSocket (non-blocking)
                    record = (t, z_ms2, x_ms2, y_ms2)
                    if not self._analytics_queue.full():
                        self._analytics_queue.put_nowait(record)

                    sample_count += 1

                    # 3. UDP Buffering & Sending
                    if len(udp_buffers[0]) == 0:
                        timestamp = t        # packet start timestamp (6 decimal places)
                    udp_buffers[0].append(z_ms2)
                    udp_buffers[1].append(x_ms2)
                    udp_buffers[2].append(y_ms2)
                    raw_buffers[0].append(int(round(z_f)))
                    raw_buffers[1].append(int(round(x_f)))
                    raw_buffers[2].append(int(round(y_f)))

                    if len(udp_buffers[0]) >= SAMPLES_PER_PACKET:
                        if self._cached_targets and self._cached_data_forwarding:
                            for target in self._cached_targets:
                                fmt = target.get('format', 'corrected')
                                for i, name in enumerate(CHANNEL_NAMES):
                                    if fmt == 'raw':
                                        samples = raw_buffers[i]
                                    else:
                                        samples = [round(v, 6) for v in udp_buffers[i]]
                                    samples_str = ", ".join(str(s) for s in samples)
                                    # Raspberry Shake Datacast format (microsecond precision)
                                    packet_str = "{'" + name + "', " + f"{timestamp:.6f}" + ", " + samples_str + "}"
                                    try:
                                        self.sock.sendto(packet_str.encode('utf-8'), (target['ip'], target['port']))
                                    except OSError as e:
                                        print(f"UDP send error → {target['ip']}:{target['port']}: {e}", file=sys.stderr)
                        udp_buffers = [[], [], []]
                        raw_buffers  = [[], [], []]

                    # 4. SPS Tracking (monotonic — immune to chrony slewing)
                    if sample_count >= SAMPLES_PER_PACKET:
                        now_m   = time.monotonic()
                        elapsed = now_m - sps_mono_ref
                        sps     = SAMPLES_PER_PACKET / elapsed if elapsed > 0 else 0
                        total_samples += SAMPLES_PER_PACKET
                        total_time    += elapsed
                        self.hardware_sps = round(sps, 2)
                        self.avg_sps     = round(total_samples / total_time, 2)
                        sps_mono_ref     = now_m
                        sample_count     = 0

                # ── Rate Limiting ──────────────────────────────────────────────
                # Sleep uses time.monotonic() (fast VDSO, no syscall overhead).
                # We convert the UTC target to its equivalent monotonic time via
                # the short-lived (_utc_ref, _mono_ref) pair updated above.
                target_mono = _mono_ref + (next_loop_utc - _utc_ref)
                remaining   = target_mono - time.monotonic()
                if remaining > 0.0005:
                    time.sleep(remaining - 0.0002)
                while time.monotonic() < target_mono:
                    pass

            except Exception as e:
                print(f"HW loop error: {e}", file=sys.stderr)
                time.sleep(1)
                # Re-anchor to current UTC after any error to avoid stale timing
                _init = sorted(time.time() for _ in range(5))
                next_loop_utc = _init[2]
                _utc_ref  = next_loop_utc
                _mono_ref = time.monotonic()

        # Final flush on shutdown
        mseed_writer.flush()

    def _safe_put(self, q, msg):
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            pass

    def _analytics_loop(self):
        """Secondary loop for DB settings, batch filtering, and WebSockets."""
        from database import get_settings
        import queue
        
        settings_refresh_time = 0
        batch_records = []
        
        while self.running:
            try:
                # 1. Update DB settings every 5s
                now_mono = time.monotonic()
                if now_mono - settings_refresh_time > 5.0:
                    cached_settings = get_settings()
                    settings_refresh_time = now_mono
                    
                    targets_str = cached_settings.get('targets', '[]') if cached_settings else '[]'
                    try:
                        self._cached_targets = json.loads(targets_str)
                    except Exception:
                        self._cached_targets = []
                        
                    if cached_settings:
                        self._cached_data_forwarding = cached_settings.get('data_forwarding', 'true').lower() == 'true'

                # 2. Block until we receive data from HW thread
                try:
                    record = self._analytics_queue.get(timeout=0.2)
                    batch_records.append(record)
                except queue.Empty:
                    continue
                
                # 3. Process in batches to massively reduce GIL overhead
                if len(batch_records) >= SAMPLES_PER_PACKET:
                    timestamps = [r[0] for r in batch_records]
                    raw = {
                        'ENZ': np.array([r[1] for r in batch_records], dtype=np.float64),
                        'ENN': np.array([r[2] for r in batch_records], dtype=np.float64),
                        'ENE': np.array([r[3] for r in batch_records], dtype=np.float64)
                    }
                    
                    with self._filter_lock:
                        filtered = {}
                        for ch in CHANNEL_NAMES:
                            filtered[ch] = self._filters[ch].apply_batch_realtime(raw[ch]).tolist()
                    
                    raw_lists = {ch: raw[ch].tolist() for ch in CHANNEL_NAMES}
                    
                    batch_msg = {
                        "t_start": timestamps[0],
                        "sps": 100,
                        "samples": raw_lists
                    }
                    
                    analysis_msg = {
                        "t_start": timestamps[0],
                        "sps": 100,
                        "samples": filtered,
                        "decimation_factor": 1,
                    }
                    
                    # Log SPS safely without blocking the hardware thread
                    print(f"Per-Channel Sample Rates:")
                    for name in CHANNEL_NAMES:
                        print(f"   {name}: {self.hardware_sps:.2f} samples/sec (current), {self.avg_sps:.2f} samples/sec (avg)")
                    
                    # Thread-safe asyncio put
                    if self._loop and self._loop.is_running():
                        with self._sub_lock:
                            for q in list(self.subscribers):
                                self._loop.call_soon_threadsafe(self._safe_put, q, batch_msg)
                        
                        with self._analysis_lock:
                            for q in list(self.analysis_subscribers):
                                self._loop.call_soon_threadsafe(self._safe_put, q, analysis_msg)
                    
                    batch_records = []
                    
            except Exception as e:
                print(f"Analytics loop error: {e}")
                time.sleep(1)

# Global manager instance
sensor_manager = SensorManager(use_mock=sys.platform == 'win32')
