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
    del arr
    
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
        self.avg_sps = 0.0
        
        self._loop = None
        self._hw_thread = None
        self._analytics_thread = None
        
        import queue
        self._analytics_queue = queue.Queue(maxsize=1000)
        self._cached_targets = []
        self._cached_data_forwarding = True
        self._filter_lock = threading.Lock()
        
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
        """Strictly prioritized hardware loop for 100 SPS SPI reading, DB queueing, and UDP sending."""
        buffer = []
        udp_buffers = [[], [], []]
        
        total_samples = 0
        total_time = 0
        packet_start_time = time.time()
        sample_count = 0
        target_interval = 1.0 / 200  # 5 ms per sample (200 Hz Oversampling)
        next_loop_time = time.monotonic()
        
        # 2nd-Order Butterworth Low-Pass (fc=50Hz, fs=200Hz) for Anti-Aliasing
        # b0, b1, b2, a1, a2
        b0, b1, b2 = 0.29289322, 0.58578644, 0.29289322
        a1, a2 = 0.0, 0.17157288
        
        x_hist = {'Z': [0.0, 0.0], 'X': [0.0, 0.0], 'Y': [0.0, 0.0]}
        y_hist = {'Z': [0.0, 0.0], 'X': [0.0, 0.0], 'Y': [0.0, 0.0]}
        
        decimate_flag = False

        while self.running:
            try:
                next_loop_time += target_interval

                t, z, x, y = self.sensor.read_all()
                
                # --- Pure Arithmetic Anti-Aliasing Filter ---
                # Completely bypasses Numpy/Scipy GIL overhead. Takes ~1 microsecond.
                z_f = b0*z + b1*x_hist['Z'][0] + b2*x_hist['Z'][1] - a1*y_hist['Z'][0] - a2*y_hist['Z'][1]
                x_hist['Z'] = [z, x_hist['Z'][0]]
                y_hist['Z'] = [z_f, y_hist['Z'][0]]
                
                x_f = b0*x + b1*x_hist['X'][0] + b2*x_hist['X'][1] - a1*y_hist['X'][0] - a2*y_hist['X'][1]
                x_hist['X'] = [x, x_hist['X'][0]]
                y_hist['X'] = [x_f, y_hist['X'][0]]
                
                y_f = b0*y + b1*x_hist['Y'][0] + b2*x_hist['Y'][1] - a1*y_hist['Y'][0] - a2*y_hist['Y'][1]
                x_hist['Y'] = [y, x_hist['Y'][0]]
                y_hist['Y'] = [y_f, y_hist['Y'][0]]
                
                decimate_flag = not decimate_flag
                
                # Only process every 2nd sample for Real-Time (yielding exactly 100 Hz)
                if not decimate_flag:
                    record = (t, z_f, x_f, y_f)
                    
                    # 1. Background DB writer queueing (non-blocking, exactly 100 SPS)
                    buffer.append(record)
                    if len(buffer) >= 50:
                        insert_batch(buffer)
                        buffer = []
                    
                    # 2. Push to analytics thread (non-blocking)
                    if not self._analytics_queue.full():
                        self._analytics_queue.put_nowait(record)
                    
                    sample_count += 1
                    
                    # 3. UDP Sending (using cached targets from analytics thread)
                    if self._cached_targets:
                        if len(udp_buffers[0]) == 0:
                            timestamp = t
                        udp_buffers[0].append(z_f)
                        udp_buffers[1].append(x_f)
                        udp_buffers[2].append(y_f)

                        if len(udp_buffers[0]) >= SAMPLES_PER_PACKET:
                            for i, name in enumerate(CHANNEL_NAMES):
                                packet = [name, timestamp] + udp_buffers[i]
                                data = str(packet).encode()
                                if self._cached_data_forwarding:
                                    for target in self._cached_targets:
                                        try:
                                            self.sock.sendto(data, (target['ip'], target['port']))
                                        except BlockingIOError:
                                            pass
                            udp_buffers = [[], [], []]
                    
                    # 4. SPS Tracking
                    if sample_count >= SAMPLES_PER_PACKET:
                        end_time = time.time()
                        elapsed = end_time - packet_start_time
                        sps = SAMPLES_PER_PACKET / elapsed if elapsed > 0 else 0

                        total_samples += SAMPLES_PER_PACKET
                        total_time += elapsed
                        overall_sps = total_samples / total_time if total_time > 0 else 0

                        self.hardware_sps = round(sps, 2)
                        self.avg_sps = round(overall_sps, 2)
                        
                        packet_start_time = end_time
                        sample_count = 0

                # Precise, drift-free rate limiting using absolute time
                now = time.monotonic()
                remaining = next_loop_time - now
                if remaining > 0.003:
                    time.sleep(remaining - 0.002)
                while time.monotonic() < next_loop_time:
                    pass

            except Exception as e:
                print(f"HW loop error: {e}")
                time.sleep(1)
                next_loop_time = time.monotonic() # Reset absolute timer after an error
        
        # Flush on shutdown
        if len(buffer) > 0:
            insert_batch(buffer)
            buffer = []

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
