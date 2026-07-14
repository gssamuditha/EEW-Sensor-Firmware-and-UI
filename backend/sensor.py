import time
import socket
import threading
import asyncio
import random
import sys
import json

from database import insert_batch, get_data_for_range, get_data_availability
from filters import BandpassFilter, minmax_downsample, FILTER_PRESETS
import numpy as np

# === ADC Config ===
CS_PINS = [35, 33, 36]        # Acc Z, Acc X, Acc Y
DRDY_PINS = [11, 15, 13]
VREF_ADCS = [1.8, 1.8, 1.8]
FULL_SCALE = 8388607
CHANNEL_NAMES = ['ENZ', 'ENN', 'ENE']
SAMPLES_PER_PACKET = 25
SAMPLE_INTERVAL = 0.0035  # 100 sps

# === Accelerometer Settings ===
ACC_ZERO_VOLTAGES = [0.0, 0.0, 0.0]  # To be calibrated
ACC_SENSITIVITY_V_PER_G = 0.4
G_TO_MS2 = 9.80665

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
        # Generate some realistic looking sine wave + noise data
        t = time.time()
        z = 0.5 * random.random() + 0.1
        x = 0.5 * random.random() - 0.2
        y = 0.5 * random.random() + 0.05
        return (t, z, x, y)


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
            self.spi.xfer2([0x42, 0x81, 0x60, 0x40])
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
            time.sleep(0.0001)
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
        samples = [[], [], []]  # For Z, X, Y
        start_time = time.time()
        while time.time() - start_time < calibration_time_sec:
            self._start_conversion_all()
            for axis in range(3):
                voltage = self._read_adc(axis)
                samples[axis].append(voltage)
            time.sleep(SAMPLE_INTERVAL)

        for i in range(3):
            ACC_ZERO_VOLTAGES[i] = sum(samples[i]) / len(samples[i])

        print("Calibration complete. Zero-level voltages (V):")
        print(f"Z: {ACC_ZERO_VOLTAGES[0]:.6f} V, X: {ACC_ZERO_VOLTAGES[1]:.6f} V, Y: {ACC_ZERO_VOLTAGES[2]:.6f} V")

    def read_all(self):
        self._start_conversion_all()
        readings = []
        for i in range(3):
            voltage = self._read_adc(i)
            zero_voltage = ACC_ZERO_VOLTAGES[i]
            g_val = (voltage - zero_voltage) / ACC_SENSITIVITY_V_PER_G
            ms2 = g_val * G_TO_MS2
            readings.append(ms2)
        return (time.time(), readings[0], readings[1], readings[2])

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
        self._filter_lock = threading.Lock()
        
    def start(self):
        from database import get_settings
        settings = get_settings()
        cal_time = int(settings.get('calibration_time', 60))
        
        self.sensor.init_sensor()
        self.sensor.calibrate(calibration_time_sec=cal_time)
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
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

def process_historical_data_task(start_time: float, end_time: float, low_hz: float, high_hz: float, target_display_points: int = 4000) -> dict:
    """
    Top-level standalone function to query DB and apply DSP.
    Designed to run in a separate ProcessPoolExecutor to avoid blocking the GIL.
    """
    window_seconds = end_time - start_time
    rows = get_data_for_range(start_time, end_time)

    if not rows:
        return {
            "timestamps": [],
            "samples": {ch: [] for ch in CHANNEL_NAMES},
            "sps": 100,
            "window_seconds": window_seconds,
        }

    arr = np.array(rows, dtype=np.float64)
    timestamps = arr[:, 0]
    raw = {'ENZ': arr[:, 1], 'ENN': arr[:, 2], 'ENE': arr[:, 3]}
    del rows

    filtered = {}
    for ch in CHANNEL_NAMES:
        if len(raw[ch]) < 13:
            filtered[ch] = raw[ch]
        else:
            filt = BandpassFilter(low_hz=low_hz, high_hz=high_hz, fs=100.0, order=4)
            filtered[ch] = filt.apply_zerophase(raw[ch])

    result_samples = {}
    for ch in CHANNEL_NAMES:
        ds_t, ds_v = minmax_downsample(timestamps, filtered[ch], target_display_points)
        result_samples[ch] = ds_v.tolist()

    return {
        "timestamps": ds_t.tolist(),
        "samples": result_samples,
        "sps": 100,
        "window_seconds": window_seconds,
        "raw_sample_count": len(timestamps),
        "display_points": len(ds_t.tolist()),
    }

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
            
    def _run_loop(self):
        from database import get_settings
        buffer = []              # DB write buffer
        udp_buffers = [[], [], []]  # UDP forwarding buffers (one per channel)
        ws_buffers = {ch: [] for ch in CHANNEL_NAMES}  # WS batch buffers
        ws_batch_start_time = None  # timestamp of first sample in current WS batch

        # Analysis filtered batch buffers
        analysis_buffers = {ch: [] for ch in CHANNEL_NAMES}
        analysis_batch_start_time = None

        # SPS tracking — mirrors ADXL354.py stream_udp()
        total_samples = 0
        total_time = 0
        packet_start_time = None
        sample_count = 0

        # Precise 100 SPS timing
        target_interval = 1.0 / 100  # 10 ms per sample

        # Cache settings to avoid DB hit every sample
        cached_settings = None
        settings_refresh_time = 0
        cached_targets = []
        cached_data_forwarding = True

        while self.running:
            try:
                loop_start = time.monotonic()

                # --- First sample of a new batch: capture start time ---
                if sample_count == 0:
                    packet_start_time = time.time()
                    ws_batch_start_time = None  # set on actual first read below

                t, z, x, y = self.sensor.read_all()
                record = (t, z, x, y)
                buffer.append(record)
                sample_count += 1

                # Record the wall-clock time of the very first sample in this WS batch
                if ws_batch_start_time is None:
                    ws_batch_start_time = t

                # Accumulate into per-channel WS buffers
                ws_vals = {'ENZ': z, 'ENN': x, 'ENE': y}
                for ch in CHANNEL_NAMES:
                    ws_buffers[ch].append(ws_vals[ch])

                # --- Apply bandpass filter per-axis for live stream ---
                with self._filter_lock:
                    filtered_vals = {}
                    for ch in CHANNEL_NAMES:
                        filtered_vals[ch] = self._filters[ch].apply_realtime(ws_vals[ch])
                for ch in CHANNEL_NAMES:
                    analysis_buffers[ch].append(filtered_vals[ch])
                if analysis_batch_start_time is None:
                    analysis_batch_start_time = t

                # --- When a full batch of SAMPLES_PER_PACKET is ready ---
                if sample_count >= SAMPLES_PER_PACKET:
                    end_time = time.time()
                    elapsed = end_time - packet_start_time
                    sps = SAMPLES_PER_PACKET / elapsed if elapsed > 0 else 0

                    total_samples += SAMPLES_PER_PACKET
                    total_time += elapsed
                    overall_sps = total_samples / total_time if total_time > 0 else 0

                    self.hardware_sps = round(sps, 2)
                    self.avg_sps = round(overall_sps, 2)

                    print(f"Per-Channel Sample Rates:")
                    for name in CHANNEL_NAMES:
                        print(f"   {name}: {sps:.2f} samples/sec (current), {overall_sps:.2f} samples/sec (avg)")

                    # Build batch WebSocket message (same structure as ADXL354.py UDP packet:
                    #   channel_name, start_timestamp, [samples...]  — but for all channels at once)
                    batch_msg = {
                        "t_start": ws_batch_start_time,
                        "sps": 100,
                        "samples": {ch: list(ws_buffers[ch]) for ch in CHANNEL_NAMES}
                    }

                    # Push to all WebSocket subscribers — skip silently if a client is congested
                    with self._sub_lock:
                        subs = list(self.subscribers)
                    for q in subs:
                        try:
                            q.put_nowait(batch_msg)
                            self._ws_batches_sent += 1
                        except asyncio.QueueFull:
                            self._ws_batches_dropped += 1
                            print(f"WS queue full — batch dropped (total dropped: {self._ws_batches_dropped})")

                    # Clear WS buffers for next batch
                    for ch in CHANNEL_NAMES:
                        ws_buffers[ch] = []
                    ws_batch_start_time = None
                    sample_count = 0

                    # --- Push filtered batch to analysis subscribers ---
                    analysis_msg = {
                        "t_start": analysis_batch_start_time,
                        "sps": 100,
                        "samples": {ch: list(analysis_buffers[ch]) for ch in CHANNEL_NAMES},
                        "decimation_factor": 1,
                    }
                    with self._analysis_lock:
                        a_subs = list(self.analysis_subscribers)
                    for q in a_subs:
                        try:
                            q.put_nowait(analysis_msg)
                        except asyncio.QueueFull:
                            pass  # drop silently for slow analysis clients
                    # Clear analysis buffers
                    for ch in CHANNEL_NAMES:
                        analysis_buffers[ch] = []
                    analysis_batch_start_time = None

                # Refresh settings cache every 5 seconds
                now_mono = time.monotonic()
                if now_mono - settings_refresh_time > 5.0:
                    cached_settings = get_settings()
                    settings_refresh_time = now_mono
                    
                    targets_str = cached_settings.get('targets', '[]') if cached_settings else '[]'
                    try:
                        cached_targets = json.loads(targets_str)
                    except Exception:
                        cached_targets = []
                        
                    if cached_settings:
                        cached_data_forwarding = cached_settings.get('data_forwarding', 'true').lower() == 'true'

                # --- UDP forwarding (unchanged from ADXL354.py pattern) ---
                if cached_targets:
                    if len(udp_buffers[0]) == 0:
                        timestamp = t
                    udp_buffers[0].append(z)
                    udp_buffers[1].append(x)
                    udp_buffers[2].append(y)

                    if len(udp_buffers[0]) >= SAMPLES_PER_PACKET:
                        for i, name in enumerate(CHANNEL_NAMES):
                            packet = [name, timestamp] + udp_buffers[i]
                            data = str(packet).encode()
                            if cached_data_forwarding:
                                for target in cached_targets:
                                    self.sock.sendto(data, (target['ip'], target['port']))
                        udp_buffers = [[], [], []]

                # Batch save to DB every 50 samples
                if len(buffer) >= 50:
                    insert_batch(buffer)
                    buffer = []

                # Precise rate limiting: hybrid sleep + busy-wait for exact 100 SPS
                remaining = target_interval - (time.monotonic() - loop_start)
                if remaining > 0.002:
                    time.sleep(remaining - 0.001)
                while (time.monotonic() - loop_start) < target_interval:
                    pass

            except Exception as e:
                print(f"Sensor read error: {e}")
                time.sleep(1)

        # Flush any remaining buffer on shutdown
        if len(buffer) > 0:
            insert_batch(buffer)
            buffer = []

# Global manager instance
sensor_manager = SensorManager(use_mock=sys.platform == 'win32')
