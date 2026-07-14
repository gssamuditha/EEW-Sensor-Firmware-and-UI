"""
filters.py — Digital Signal Processing module for EEW Sensor Analysis.

Provides a real-time IIR Butterworth bandpass filter suitable for seismic
signal analysis.  Designed to run on Raspberry Pi 3 with minimal CPU overhead.

Typical earthquake frequency band: 0.1 Hz – 20 Hz.
"""

import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi, sosfiltfilt

try:
    from obspy import Trace
    OBSPY_AVAILABLE = True
except ImportError:
    OBSPY_AVAILABLE = False


# ---------------------------------------------------------------------------
# Filter presets — standard seismological frequency bands
# ---------------------------------------------------------------------------
FILTER_PRESETS = {
    "global":      {"label": "Global (Teleseismic)",  "low_hz": 0.1,  "high_hz": 0.8},
    "regional":    {"label": "Regional",              "low_hz": 0.7,  "high_hz": 2.0},
    "local":       {"label": "Local",                 "low_hz": 3.0,  "high_hz": 8.0},
    "hyper_local": {"label": "Hyper-Local",           "low_hz": 3.0,  "high_hz": 20.0},
    "default":     {"label": "Full Earthquake Band",  "low_hz": 0.1,  "high_hz": 20.0},
}


class BandpassFilter:
    """
    Real-time IIR Butterworth bandpass filter using second-order sections
    (SOS) for numerical stability.

    Supports three modes:
      1. apply(data)              stateless causal batch filtering
      2. apply_zerophase(data)    zero-phase batch filtering (for historical data)
      3. apply_realtime(sample)   stateful sample-by-sample filtering (for live stream)
    """

    def __init__(self, low_hz: float, high_hz: float, fs: float = 100.0, order: int = 4):
        """
        Parameters
        ----------
        low_hz  : Lower cutoff frequency in Hz (e.g. 0.1)
        high_hz : Upper cutoff frequency in Hz (e.g. 20.0)
        fs      : Sampling rate in Hz (default 100)
        order   : Filter order (default 4 — standard for seismic analysis)
        """
        self.fs = fs
        self.order = order
        self.low_hz = low_hz
        self.high_hz = high_hz
        self._sos = None
        self._zi = None  # Filter state for real-time mode
        self._design_filter()

    def _design_filter(self):
        """Compute SOS coefficients and initialise the filter state."""
        nyquist = self.fs / 2.0
        low = self.low_hz / nyquist
        high = self.high_hz / nyquist

        # Clamp to valid Nyquist-normalised range (0, 1)
        low = max(low, 1e-6)
        high = min(high, 1.0 - 1e-6)

        if low >= high:
            raise ValueError(
                f"Low cutoff ({self.low_hz} Hz) must be less than "
                f"high cutoff ({self.high_hz} Hz)"
            )

        self._sos = butter(self.order, [low, high], btype='band', output='sos')
        # Initial conditions for step response — gives a smooth filter startup
        self._zi = sosfilt_zi(self._sos) * 0.0  # start from zero

    def update_params(self, low_hz: float, high_hz: float):
        """
        Update cutoff frequencies and recompute filter coefficients.
        Resets the internal filter state.
        """
        self.low_hz = low_hz
        self.high_hz = high_hz
        self._design_filter()

    def apply(self, data: np.ndarray) -> np.ndarray:
        """
        Stateless causal batch filter — apply bandpass to an entire array.
        Does NOT affect the real-time filter state.

        Parameters
        ----------
        data : 1-D numpy array of samples

        Returns
        -------
        Filtered 1-D numpy array (same length)
        """
        if len(data) == 0:
            return data
        return sosfilt(self._sos, data)

    def apply_zerophase(self, data: np.ndarray) -> np.ndarray:
        """
        Zero-phase (forward-backward) batch filter for historical data.

        Uses sosfiltfilt which applies the filter forward and backward,
        resulting in zero phase distortion.  This preserves exact P/S wave
        arrival timing and is the gold standard for offline seismic analysis.

        The effective filter order is doubled (4th order → equivalent to 8th).

        Parameters
        ----------
        data : 1-D numpy array of samples (minimum 13 samples required)

        Returns
        -------
        Filtered 1-D numpy array (same length)
        """
        if len(data) < 13:
            # sosfiltfilt needs enough samples for the padlen
            return data
        return sosfiltfilt(self._sos, data)

    def apply_realtime(self, sample: float) -> float:
        """
        Stateful sample-by-sample IIR filter.

        Call this once per new sample in the sensor loop.  The internal
        filter state (self._zi) carries over between calls, providing
        correct IIR behaviour across batches.

        Parameters
        ----------
        sample : Single float sample value

        Returns
        -------
        Filtered float value
        """
        # sosfilt expects an array; wrap the single sample
        filtered, self._zi = sosfilt(self._sos, np.array([sample]), zi=self._zi)
        return float(filtered[0])

    def apply_batch_realtime(self, samples: np.ndarray) -> np.ndarray:
        """
        Stateful array-based IIR filter for batches.
        Dramatically faster than sample-by-sample for real-time streams.
        """
        filtered, self._zi = sosfilt(self._sos, samples, zi=self._zi)
        return filtered

    @property
    def params(self) -> dict:
        """Return current filter parameters as a serialisable dict."""
        return {
            "low_hz": self.low_hz,
            "high_hz": self.high_hz,
            "fs": self.fs,
            "order": self.order,
        }


def minmax_downsample(timestamps: np.ndarray, data: np.ndarray,
                      target_points: int = 4000) -> tuple:
    """
    Min-max envelope downsampling for seismic waveform visualisation.

    For each pixel-width bucket, keeps both the minimum and maximum value.
    This guarantees that no peak or trough (e.g. P-wave first arrival,
    maximum ground acceleration) is hidden by the downsampling — unlike
    simple stride decimation which can miss peaks between strides.

    Parameters
    ----------
    timestamps   : 1-D numpy array of epoch timestamps
    data         : 1-D numpy array of amplitude values (same length)
    target_points: Approximate number of output points (default 4000)

    Returns
    -------
    (out_timestamps, out_data) — both 1-D numpy arrays, length ≤ target_points
    """
    n = len(data)
    if n <= target_points:
        return timestamps, data

    # Each bucket produces 2 points (min + max), so we need target/2 buckets
    n_buckets = max(1, target_points // 2)
    bucket_size = n / n_buckets

    out_t = np.empty(n_buckets * 2, dtype=np.float64)
    out_v = np.empty(n_buckets * 2, dtype=np.float64)
    idx = 0

    for i in range(n_buckets):
        start = int(i * bucket_size)
        end = min(int((i + 1) * bucket_size), n)
        if start >= end:
            continue

        chunk_data = data[start:end]
        chunk_time = timestamps[start:end]

        min_idx = np.argmin(chunk_data)
        max_idx = np.argmax(chunk_data)

        # Emit in chronological order to preserve waveform shape
        if min_idx <= max_idx:
            out_t[idx] = chunk_time[min_idx]
            out_v[idx] = chunk_data[min_idx]
            out_t[idx + 1] = chunk_time[max_idx]
            out_v[idx + 1] = chunk_data[max_idx]
        else:
            out_t[idx] = chunk_time[max_idx]
            out_v[idx] = chunk_data[max_idx]
            out_t[idx + 1] = chunk_time[min_idx]
            out_v[idx + 1] = chunk_data[min_idx]
        idx += 2

    return out_t[:idx], out_v[:idx]


def downsample(data: np.ndarray, factor: int) -> np.ndarray:
    """
    Simple decimation by integer factor (every Nth sample).

    For display purposes only — the bandpass filter already acts as the
    anti-alias filter, so a simple stride is sufficient.

    Parameters
    ----------
    data   : 1-D numpy array
    factor : Decimation factor (e.g. 10 means keep every 10th sample)

    Returns
    -------
    Decimated 1-D numpy array
    """
    if factor <= 1:
        return data
    return data[::factor]

def obspy_resample_trace(timestamps, data, input_sps=200.0, target_sps=100.0, filter_freq=45.0):
    """
    Professionally resample a trace with fluctuating timestamps to a strict SPS.
    Uses ObsPy to apply a zero-phase anti-aliasing filter and Lanczos interpolation.
    """
    if len(timestamps) < 20:
        return np.array(timestamps), np.array(data)
        
    t0 = timestamps[0]
    tN = timestamps[-1]
    
    # 1. Grid interpolation (Jitter Removal)
    # Map the fluctuating DB timestamps to a mathematically perfect input grid
    duration = tN - t0
    num_samples = int(duration * input_sps) + 1
    strict_t = t0 + np.arange(num_samples) / input_sps
    
    strict_data = np.interp(strict_t, timestamps, data)
    
    if not OBSPY_AVAILABLE:
        # Fallback if ObsPy isn't installed (just returns the strict grid decimated)
        # Using simple linear downsampling as a fallback
        out_samples = int(duration * target_sps) + 1
        out_t = t0 + np.arange(out_samples) / target_sps
        out_data = np.interp(out_t, strict_t, strict_data)
        return out_t, out_data
        
    # 2. Create ObsPy Trace
    tr = Trace(data=strict_data)
    tr.stats.sampling_rate = input_sps
    
    # 3. Zero-phase Anti-Aliasing (Low-pass)
    # Filter just below Nyquist of target SPS to prevent all aliasing
    tr.filter('lowpass', freq=filter_freq, corners=4, zerophase=True)
    
    # 4. Lanczos Resampling
    # Sinc-based mathematically perfect decimation
    try:
        tr.interpolate(sampling_rate=target_sps, method='lanczos', a=10)
    except Exception as e:
        print(f"Lanczos interpolation failed: {e}")
        tr.resample(target_sps) # Fallback to frequency-domain resampling
    
    # Reconstruct timestamps for the output
    out_samples = len(tr.data)
    out_t = t0 + np.arange(out_samples) / target_sps
    
    return out_t, tr.data
