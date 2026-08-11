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

            # Scale to physical units using per-channel sensitivity
            ch_idx = CHANNEL_NAMES.index(ch)
            ms2 = counts * CHANNEL_CONFIGS[SENSOR_VARIANT]['sensitivity_per_count'][ch_idx]
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
        "unit": "physical",
        "window_seconds": window_seconds,
        "raw_sample_count": len(timestamps),
        "display_points": len(out_t),
    }


# ===========================================================================
# Hardware Pin Definitions (BCM numbers — same PCB for 3-CH and 4-CH)
# ===========================================================================
# The EEW sensor PCB is identical for both hardware variants.
# 4-CH sensors have a GeoPhone plugged into the EHZ ADC slot (index 0).
# 3-CH sensors leave that slot empty.
#
# All pins use BCM numbering (via lgpio) and spi.no_cs=True is required
# for both variants because CE0 (BCM 8) is used as a manual chip-select.
# /boot/firmware/config.txt must contain:
#   dtoverlay=spi0-0cs       (NOT dtparam=spi=on)
# ===========================================================================

# Full 4-channel hardware pin map (BCM)
_ALL_CS_PINS   = [8,  19, 13, 16]   # EHZ, ENZ, ENN, ENE
_ALL_DRDY_PINS = [3,  17, 22, 27]   # EHZ, ENZ, ENN, ENE
_ALL_VREF      = [3.3, 1.8, 1.8, 1.8]

# ADXL354 self-test and standby control pins (BCM) — wired to ADXL channels only
ST1  = 23
ST2  = 24
STBY = 25

FULL_SCALE   = 8388607    # 24-bit two's complement positive full-scale
SAMPLES_PER_PACKET = 25
SAMPLE_INTERVAL    = 0.0035  # target 100 SPS

# Accelerometer physical-conversion constants (ADXL354BEZ ±2g)
ACC_SENSITIVITY_V_PER_G = 0.4   # V/g  (ratiometric, ±2g range)
G_TO_MS2                = 9.80665

# ===========================================================================
# Channel Configurations — keyed by variant string '3CH' or '4CH'
# ===========================================================================
# sensitivity_per_count: physical-unit per raw ADC count (used by analytics)
#   ACC channels:  (VREF × G_TO_MS2) / (FULL_SCALE × SENSITIVITY_V_per_g) [m/s² / count]
#   EHZ channel:   instrument sensitivity is embedded in the StationXML response;
#                  for display we use a placeholder 1.0 (counts are shown as raw)

def _acc_sensitivity(vref: float) -> float:
    """Return m/s² per raw ADC count for an accelerometer channel."""
    return (vref * G_TO_MS2) / (FULL_SCALE * ACC_SENSITIVITY_V_PER_G)

CHANNEL_CONFIGS = {
    '3CH': {
        'names':                ['ENZ', 'ENN', 'ENE'],
        'cs_pins':              [19, 13, 16],
        'drdy_pins':            [17, 22, 27],
        'vref':                 [1.8, 1.8, 1.8],
        # channel unit types for UI labelling ('ACC' = m/s², 'VEL' = m/s)
        'units':                ['ACC', 'ACC', 'ACC'],
        'sensitivity_per_count': [
            _acc_sensitivity(1.8),
            _acc_sensitivity(1.8),
            _acc_sensitivity(1.8),
        ],
    },
    '4CH': {
        'names':                ['EHZ', 'ENZ', 'ENN', 'ENE'],
        'cs_pins':              [8,  19, 13, 16],
        'drdy_pins':            [3,  17, 22, 27],
        'vref':                 [3.3, 1.8, 1.8, 1.8],
        # EHZ is velocity (m/s), ADXL channels are acceleration (m/s²)
        'units':                ['VEL', 'ACC', 'ACC', 'ACC'],
        'sensitivity_per_count': [
            # EHZ: overall sensitivity 399,650,000 counts/(m/s) → 1/sensitivity m/s/count
            1.0 / 399_650_000.0,
            _acc_sensitivity(1.8),
            _acc_sensitivity(1.8),
            _acc_sensitivity(1.8),
        ],
    },
}

# ===========================================================================
# Sensor variant detection
# ===========================================================================

def _detect_sensor_variant() -> str:
    """
    Determine whether this unit has a GeoPhone (4-CH) or not (3-CH).

    Priority:
    1. DB setting 'sensor_variant' ('3CH' or '4CH') — allows manual override.
    2. Auto-detection via lgpio: probe DRDY pin BCM 3 (EHZ slot).
       Because the PCB is identical for both variants the ADC is always
       physically present, so a simple pin-claim succeeds on both.
       Therefore we fall back to DB if no explicit override is set.
       On Windows / mock environments, always returns '3CH'.
    """
    if sys.platform == 'win32':
        return '3CH'

    # Check DB override first
    try:
        from database import get_settings
        s = get_settings()
        forced = s.get('sensor_variant', '').strip().upper()
        if forced in ('3CH', '4CH'):
            print(f"sensor: variant forced by DB setting → {forced}", file=sys.stderr)
            return forced
    except Exception:
        pass

    # No DB setting — default to 3CH (safe fallback)
    # The user can set sensor_variant='4CH' in the DB via setup_service.sh
    print("sensor: sensor_variant not set in DB, defaulting to 3CH. "
          "Run setup_service.sh or set sensor_variant=4CH in settings to enable GeoPhone.",
          file=sys.stderr)
    return '3CH'


# Resolve variant once at module import (before any class is instantiated)
SENSOR_VARIANT: str = _detect_sensor_variant()

# Active channel configuration
_cfg = CHANNEL_CONFIGS[SENSOR_VARIANT]
CHANNEL_NAMES:  list = _cfg['names']
CS_PINS:        list = _cfg['cs_pins']
DRDY_PINS:      list = _cfg['drdy_pins']
VREF_ADCS:      list = _cfg['vref']
CHANNEL_UNITS:  list = _cfg['units']   # 'ACC' or 'VEL' per channel
N_CHANNELS:     int  = len(CHANNEL_NAMES)

# Instrument sensitivity (m/s² or m/s per count) — used for analytics/UDP
INSTRUMENT_SENSITIVITY_PER_COUNT: list = _cfg['sensitivity_per_count']

# Legacy alias kept for metadata.py compatibility
INSTRUMENT_SENSITIVITY_MS2_PER_COUNT: float = _acc_sensitivity(VREF_ADCS[0] if SENSOR_VARIANT == '3CH' else 1.8)

# Zero-level calibration per channel (filled by RealSensor.calibrate)
RAW_COUNTS_ZERO: list = [0] * N_CHANNELS

print(f"sensor: active variant={SENSOR_VARIANT}, channels={CHANNEL_NAMES}", file=sys.stderr)


# ===========================================================================
# Mock Sensor
# ===========================================================================

class MockSensor:
    def __init__(self):
        self.sample_interval = 0.01  # 100 sps
        self.channels = CHANNEL_NAMES

    def init_sensor(self):
        print("Mock sensor initialized")

    def calibrate(self, calibration_time_sec=1):
        print("Mock sensor calibrated")
        time.sleep(1)

    def read_all_raw(self):
        """Return mock signed 24-bit ADC counts (one per channel)."""
        results = []
        for i, unit in enumerate(CHANNEL_UNITS):
            vref = VREF_ADCS[i]
            if unit == 'VEL':
                # GeoPhone: simulate small velocity noise
                cnt = int((random.gauss(0, 0.00001) / (1.0 / 399_650_000.0)))
                cnt = max(-FULL_SCALE, min(FULL_SCALE, cnt))
            else:
                # Accelerometer: simulate ~0.1 m/s² noise
                ms2 = random.gauss(0.0, 0.1)
                cnt = int(ms2 / _acc_sensitivity(vref))
                cnt = max(-FULL_SCALE, min(FULL_SCALE, cnt))
            results.append(cnt)
        return tuple(results)


# ===========================================================================
# Real Sensor — unified lgpio implementation for 3-CH and 4-CH
# ===========================================================================

class RealSensor:
    """
    Hardware SPI sensor reader using lgpio (BCM pin numbering).

    Works for both 3-CH (ADXL only) and 4-CH (GeoPhone + ADXL) variants
    because the PCB is identical. The active channel count is determined by
    SENSOR_VARIANT / CHANNEL_CONFIGS at module load time.

    SPI setup:
      - spi.no_cs = True  (CE0 / BCM8 is used as manual chip-select)
      - Requires dtoverlay=spi0-0cs in /boot/firmware/config.txt
    """

    def __init__(self):
        import spidev
        self.spidev = spidev
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 4000000
        self.spi.mode = 0b01
        self.spi.no_cs = True   # CRITICAL: CE0 is a manual CS, not hardware CE

        self._h = None           # lgpio handle

    def _open_gpio(self):
        """Open the lgpio chip handle, trying gpiochip0 then gpiochip4."""
        import lgpio
        self._lgpio = lgpio
        try:
            self._h = lgpio.gpiochip_open(0)
        except Exception:
            self._h = lgpio.gpiochip_open(4)

    def _claim_pin_out(self, pin: int, initial: int):
        lgpio = self._lgpio
        try:
            lgpio.gpio_claim_output(self._h, pin, initial)
        except lgpio.error:
            lgpio.gpio_free(self._h, pin)
            lgpio.gpio_claim_output(self._h, pin, initial)

    def _claim_pin_in(self, pin: int):
        lgpio = self._lgpio
        try:
            lgpio.gpio_claim_input(self._h, pin, lgpio.SET_PULL_UP)
        except lgpio.error:
            lgpio.gpio_free(self._h, pin)
            lgpio.gpio_claim_input(self._h, pin, lgpio.SET_PULL_UP)

    def _gpio_out(self, pin: int, val: bool):
        self._lgpio.gpio_write(self._h, pin, 1 if val else 0)

    def init_sensor(self):
        """Claim all GPIO pins, power up, and run initial ADC flush cycles."""
        self._open_gpio()

        # CS pins start HIGH (deselected), control pins start LOW
        for pin in CS_PINS:
            self._claim_pin_out(pin, 1)   # CS high = deselected
        for pin in [ST1, ST2]:
            self._claim_pin_out(pin, 0)   # self-test off
        self._claim_pin_out(STBY, 1)      # standby high = active

        # DRDY pins are inputs with pull-up
        for pin in DRDY_PINS:
            self._claim_pin_in(pin)

        time.sleep(0.5)   # allow power rails to stabilise

        self._adc_init_all()

        # Flush 5 warm-up conversions to stabilise ADC references
        for _ in range(5):
            self._start_conversion_all()
            try:
                self._wait_all_drdy(timeout=2)
                for i in range(N_CHANNELS):
                    self._read_adc_raw(i)
            except Exception:
                pass
            time.sleep(0.01)

    def _adc_init_all(self):
        """Send RESET + config registers to each ADC."""
        for i in range(N_CHANNELS):
            self._gpio_out(CS_PINS[i], False)
            time.sleep(0.0001)
            self.spi.xfer2([0x06])          # RESET command
            time.sleep(0.1)
            # Reg 0 = 0x81 : AIN0/AIN1, PGA disabled (Gain=1)
            # Reg 1 = 0x80 : 330 SPS, Normal mode, Single-shot
            # Reg 2 = 0x40 : External Vref
            self.spi.xfer2([0x42, 0x81, 0x80, 0x40])
            self.spi.xfer2([0x08])          # START command
            self._gpio_out(CS_PINS[i], True)
            time.sleep(0.1)

    def _start_conversion_all(self):
        """Assert START command simultaneously to all ADCs."""
        for pin in CS_PINS:
            self._gpio_out(pin, False)
        self.spi.xfer2([0x08])             # START/SYNC
        for pin in CS_PINS:
            self._gpio_out(pin, True)

    def _wait_all_drdy(self, timeout: float = 10.0):
        """Block until all DRDY pins go LOW (conversion complete)."""
        lgpio = self._lgpio
        h = self._h
        start = time.time()
        while True:
            all_ready = all(lgpio.gpio_read(h, pin) == 0 for pin in DRDY_PINS)
            if all_ready:
                return
            if time.time() - start > timeout:
                raise TimeoutError(f"Timeout waiting for DRDY on {DRDY_PINS}")

    def _read_adc_raw(self, i: int, return_raw: bool = True) -> int:
        """Read 24-bit signed ADC count from channel index i (DRDY must be low)."""
        self._gpio_out(CS_PINS[i], False)
        data = self.spi.xfer2([0x00, 0x00, 0x00])
        self._gpio_out(CS_PINS[i], True)

        raw = (data[0] << 16) | (data[1] << 8) | data[2]
        if raw & (1 << 23):
            raw -= (1 << 24)   # two's complement sign extension
        return raw

    def calibrate(self, calibration_time_sec: int = 60):
        """
        Compute zero-level raw count offsets for each channel.
        Stores results in the module-level RAW_COUNTS_ZERO list.
        EHZ (velocity) channel is included but its zero may fluctuate.
        """
        print(f"Starting zero-level calibration for {calibration_time_sec} seconds…", file=sys.stderr)
        samples = [[] for _ in range(N_CHANNELS)]
        start_time = time.time()

        while time.time() - start_time < calibration_time_sec:
            self._start_conversion_all()
            self._wait_all_drdy(timeout=2)
            for i in range(N_CHANNELS):
                raw = self._read_adc_raw(i)
                samples[i].append(raw)
            time.sleep(SAMPLE_INTERVAL)

        for i in range(N_CHANNELS):
            RAW_COUNTS_ZERO[i] = int(round(sum(samples[i]) / len(samples[i])))

        print("Calibration complete.", file=sys.stderr)
        for i, ch in enumerate(CHANNEL_NAMES):
            print(f"  {ch}: zero={RAW_COUNTS_ZERO[i]}", file=sys.stderr)

    def read_all_raw(self) -> tuple:
        """
        Trigger simultaneous conversion on all channels, wait for DRDY,
        then read 24-bit signed counts.  Returns a tuple of N integer counts
        (one per channel, in CHANNEL_NAMES order).
        """
        self._start_conversion_all()
        self._wait_all_drdy(timeout=10)
        return tuple(self._read_adc_raw(i) for i in range(N_CHANNELS))

    def cleanup(self):
        """Release GPIO and SPI resources."""
        try:
            if self._h is not None:
                self._lgpio.gpiochip_close(self._h)
        except Exception:
            pass
        try:
            self.spi.close()
        except Exception:
            pass


# ===========================================================================
# SensorManager
# ===========================================================================

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
        # Per-channel bandpass filters (default: earthquake band 0.1–20 Hz)
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
        if hasattr(self.sensor, 'cleanup'):
            self.sensor.cleanup()

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
        _init = sorted(time.time() for _ in range(5))
        next_loop_utc = _init[2]           # median → UTC-accurate start
        _utc_ref      = next_loop_utc
        _mono_ref     = time.monotonic()
        print(f"sensor-hw: Software PLL started. Initial UTC anchor: {next_loop_utc:.6f}",
              file=sys.stderr)

        # N-channel buffers
        udp_buffers = [[] for _ in range(N_CHANNELS)]  # physical units (corrected UDP)
        raw_buffers = [[] for _ in range(N_CHANNELS)]   # integer counts (raw UDP)

        total_samples = 0
        total_time    = 0
        sps_mono_ref  = time.monotonic()
        sample_count  = 0

        # 2nd-Order Butterworth Low-Pass (fc=50 Hz, fs=200 Hz) — Anti-Aliasing.
        b0, b1, b2 = 0.29289322, 0.58578644, 0.29289322
        a1, a2     = 0.0, 0.17157288

        # Per-channel IIR filter state: dict keyed by channel name
        x_hist = {ch: [0.0, 0.0] for ch in CHANNEL_NAMES}
        y_hist = {ch: [0.0, 0.0] for ch in CHANNEL_NAMES}

        decimate_flag = False

        while self.running:
            try:
                # Advance UTC scheduling accumulator
                next_loop_utc += target_interval

                # ── Software PLL: NTP step detection ──────────────────────────
                now_utc  = time.time()
                now_mono = time.monotonic()
                expected_utc = _utc_ref + (now_mono - _mono_ref)
                utc_error    = now_utc - expected_utc

                if abs(utc_error) > NTP_STEP_THRESHOLD:
                    next_loop_utc = now_utc
                    print(
                        f"sensor-hw: NTP step detected ({utc_error:+.3f}s). "
                        f"Timing re-anchored to {now_utc:.6f}",
                        file=sys.stderr
                    )

                _utc_ref  = now_utc
                _mono_ref = now_mono

                # ── Hardware Read ──────────────────────────────────────────────
                raw_counts = self.sensor.read_all_raw()   # tuple of N int counts

                # ── Anti-Aliasing IIR Filter (per channel) ────────────────────
                filtered_counts = []
                for i, ch in enumerate(CHANNEL_NAMES):
                    cnt = raw_counts[i]
                    f = (b0*cnt
                         + b1*x_hist[ch][0] + b2*x_hist[ch][1]
                         - a1*y_hist[ch][0] - a2*y_hist[ch][1])
                    x_hist[ch] = [cnt, x_hist[ch][0]]
                    y_hist[ch] = [f,   y_hist[ch][0]]
                    filtered_counts.append(f)

                # ── Decimation: keep every 2nd → 100 SPS output ───────────────
                decimate_flag = not decimate_flag
                if not decimate_flag:
                    t = next_loop_utc

                    # Convert filtered counts → physical units
                    phys_values = [
                        (filtered_counts[i] - RAW_COUNTS_ZERO[i])
                        * INSTRUMENT_SENSITIVITY_PER_COUNT[i]
                        for i in range(N_CHANNELS)
                    ]

                    # 1. miniSEED archive (raw int32 counts)
                    mseed_writer.enqueue(t, [int(round(f)) for f in filtered_counts])

                    # 2. Analytics WebSocket (non-blocking)
                    record = (t,) + tuple(phys_values)
                    if not self._analytics_queue.full():
                        self._analytics_queue.put_nowait(record)

                    sample_count += 1

                    # 3. UDP Buffering & Sending
                    if len(udp_buffers[0]) == 0:
                        timestamp = t
                    for i in range(N_CHANNELS):
                        udp_buffers[i].append(phys_values[i])
                        raw_buffers[i].append(int(round(filtered_counts[i])))

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
                                    # Raspberry Shake Datacast format
                                    packet_str = ("{'%s', %.6f, %s}" % (name, timestamp, samples_str))
                                    try:
                                        self.sock.sendto(
                                            packet_str.encode('utf-8'),
                                            (target['ip'], target['port'])
                                        )
                                    except OSError as e:
                                        print(f"UDP send error → {target['ip']}:{target['port']}: {e}",
                                              file=sys.stderr)
                        udp_buffers = [[] for _ in range(N_CHANNELS)]
                        raw_buffers = [[] for _ in range(N_CHANNELS)]

                    # 4. SPS Tracking
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
                target_mono = _mono_ref + (next_loop_utc - _utc_ref)
                remaining   = target_mono - time.monotonic()
                if remaining > 0.0005:
                    time.sleep(remaining - 0.0002)
                while time.monotonic() < target_mono:
                    pass

            except Exception as e:
                print(f"HW loop error: {e}", file=sys.stderr)
                time.sleep(1)
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

                # 3. Process in batches to reduce GIL overhead
                if len(batch_records) >= SAMPLES_PER_PACKET:
                    timestamps = [r[0] for r in batch_records]

                    # Build per-channel numpy arrays from the record tuples
                    # record = (t, ch0_val, ch1_val, ..., chN-1_val)
                    raw = {
                        ch: np.array([r[i + 1] for r in batch_records], dtype=np.float64)
                        for i, ch in enumerate(CHANNEL_NAMES)
                    }

                    with self._filter_lock:
                        filtered = {}
                        for ch in CHANNEL_NAMES:
                            filtered[ch] = self._filters[ch].apply_batch_realtime(raw[ch]).tolist()

                    raw_lists = {ch: raw[ch].tolist() for ch in CHANNEL_NAMES}

                    batch_msg = {
                        "t_start": timestamps[0],
                        "sps": 100,
                        "samples": raw_lists,
                        # Expose channel metadata so the frontend can label units
                        "channel_units": {ch: CHANNEL_UNITS[i] for i, ch in enumerate(CHANNEL_NAMES)},
                    }

                    analysis_msg = {
                        "t_start": timestamps[0],
                        "sps": 100,
                        "samples": filtered,
                        "decimation_factor": 1,
                        "channel_units": {ch: CHANNEL_UNITS[i] for i, ch in enumerate(CHANNEL_NAMES)},
                    }

                    print(f"Per-Channel Sample Rates:")
                    for name in CHANNEL_NAMES:
                        print(f"   {name}: {self.hardware_sps:.2f} sps (current), {self.avg_sps:.2f} sps (avg)")

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


# ── Hardware detection ─────────────────────────────────────────────────────
# Use the mock sensor if:
#   a) Running on Windows (development)
#   b) EEW_MOCK=1 environment variable is set (CI / build environment)
#   c) /proc/device-tree/model does not exist or does not contain 'Raspberry Pi'
import os as _os

def _is_raspberry_pi() -> bool:
    """Return True only when running on actual Raspberry Pi hardware."""
    if sys.platform == 'win32':
        return False
    if _os.environ.get('EEW_MOCK', '').strip() == '1':
        return False
    try:
        with open('/proc/device-tree/model', 'r') as _f:
            return 'Raspberry Pi' in _f.read()
    except (FileNotFoundError, PermissionError, OSError):
        return False

# Global manager instance
sensor_manager = SensorManager(use_mock=not _is_raspberry_pi())
