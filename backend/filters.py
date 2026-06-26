"""
filters.py — Digital Signal Processing module for EEW Sensor Analysis.

Provides a real-time IIR Butterworth bandpass filter suitable for seismic
signal analysis.  Designed to run on Raspberry Pi 3 with minimal CPU overhead.

Typical earthquake frequency band: 0.1 Hz – 20 Hz.
"""

import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi


class BandpassFilter:
    """
    Real-time IIR Butterworth bandpass filter using second-order sections
    (SOS) for numerical stability.

    Supports two modes:
      1. apply(data)           stateless batch filtering (for historical data)
      2. apply_realtime(sample) stateful sample-by-sample filtering (for live stream)
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
        Stateless batch filter — apply bandpass to an entire array.
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

    @property
    def params(self) -> dict:
        """Return current filter parameters as a serialisable dict."""
        return {
            "low_hz": self.low_hz,
            "high_hz": self.high_hz,
            "fs": self.fs,
            "order": self.order,
        }


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
