"""
detector.py — Real-time STA/LTA P-wave onset detector for EEW Sensor.
======================================================================

Implements the classic Allen (1978) Short-Term Average / Long-Term Average
(STA/LTA) algorithm adapted for MEMS accelerometer arrays, using an efficient
recursive IIR approximation for real-time operation on Raspberry Pi 3.

Algorithm reference
-------------------
  Allen, R. V. (1978). Automatic earthquake recognition and timing from
  single traces. BSSA, 68(5), 1521–1532.

  Baer, M. & Kradolfer, U. (1987). An automatic phase picker for local
  and teleseismic events. BSSA, 77(4), 1437–1445.

Design notes
------------
* The detector runs inside the existing `_analytics_loop` thread — no
  additional threads are created.
* Characteristic Function (CF):
    - ACC channels (ENZ, ENN, ENE):  CF = squared amplitude (x²)
    - VEL channel  (EHZ, geophone):  CF = absolute amplitude |x|
* Multi-channel fusion:
    - Phase 1 — Composite CF: vector norm² of all ACC channels (higher SNR
      at P-wave onset because P-wave energy distributes across all 3 axes).
    - Phase 2 — Per-channel confirmation: each channel runs an independent
      STA/LTA; at least N_CONFIRM channels must exceed threshold_on.
* Recursive (IIR) STA/LTA:
    STA[n] = α_s * CF[n] + (1-α_s) * STA[n-1]   (α_s = 1/n_sta)
    LTA[n] = α_l * CF[n] + (1-α_l) * LTA[n-1]   (α_l = 1/n_lta)
  This avoids O(N) circular-buffer reads, is ~3–5× faster than the boxcar
  version, and is standard in real-time EEW (e.g. Earthworm carlstatrig).
* Re-trigger lockout: after trigger_on, no new trigger_on is emitted until
  `lockout_sec` seconds have elapsed (default = lta_sec).
* LTA freeze: once triggered, the LTA update is frozen so a slowly decaying
  coda does not drag the LTA up and mask re-triggers after the lockout.
"""

import time
import threading
from typing import Optional
import numpy as np


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum LTA fill fraction before triggering is enabled.
# Prevents spurious triggers during the first `lta_sec` seconds of operation.
LTA_MIN_FILL_FRACTION = 0.90   # require 90 % of LTA window to be "seen"

# Number of ACC channels that must exceed threshold_on for confirmation vote
N_CONFIRM = 2   # at least 2-of-3 for a 3CH sensor, 2-of-3 ACC for 4CH


# ---------------------------------------------------------------------------
# STALTADetector
# ---------------------------------------------------------------------------

class STALTADetector:
    """
    Real-time recursive STA/LTA P-wave onset detector.

    Parameters
    ----------
    sta_sec       : float  — Short-term window duration in seconds (default 0.5)
    lta_sec       : float  — Long-term window duration in seconds (default 10.0)
    threshold_on  : float  — Trigger ON ratio threshold (default 3.5)
    threshold_off : float  — Trigger OFF (de-trigger) ratio threshold (default 1.5)
    fs            : float  — Sampling rate in Hz (default 100.0)
    channel_names : list   — List of active channel name strings
    channel_units : dict   — Map of channel_name → 'ACC' or 'VEL'
    lockout_sec   : float  — Minimum seconds between trigger_on events
                             (default = lta_sec to avoid coda re-triggers)
    """

    def __init__(
        self,
        sta_sec: float = 0.5,
        lta_sec: float = 10.0,
        threshold_on: float = 3.5,
        threshold_off: float = 1.5,
        fs: float = 100.0,
        channel_names: Optional[list] = None,
        channel_units: Optional[dict] = None,
        lockout_sec: Optional[float] = None,
    ):
        self.fs            = fs
        self.channel_names = channel_names or []
        self.channel_units = channel_units or {}

        # Configurable parameters (can be updated live via update_params)
        self._lock = threading.Lock()
        self._init_params(sta_sec, lta_sec, threshold_on, threshold_off, lockout_sec)

        # State exposed as read-only properties
        self._triggered          = False
        self._trigger_start_time = None
        self._last_trigger_time  = None   # monotonic time of last trigger_on
        self._max_amplitude      = 0.0

        # Composite + per-channel STA/LTA state
        self._sta_composite  = 0.0
        self._lta_composite  = 0.0
        self._sta_per_ch     = {ch: 0.0 for ch in self.channel_names}
        self._lta_per_ch     = {ch: 0.0 for ch in self.channel_names}

        # LTA fill tracker — counts samples seen toward a full LTA window
        self._lta_samples_seen = 0
        self._lta_full_samples = int(lta_sec * fs)

    # -----------------------------------------------------------------------
    # Public interface
    # -----------------------------------------------------------------------

    def update_params(
        self,
        sta_sec: float,
        lta_sec: float,
        threshold_on: float,
        threshold_off: float,
        lockout_sec: Optional[float] = None,
    ):
        """
        Update detector parameters (thread-safe).
        Resets all STA/LTA state to prevent stale values producing false triggers.
        """
        with self._lock:
            self._init_params(sta_sec, lta_sec, threshold_on, threshold_off, lockout_sec)
            self._reset_state()

    def update_channels(self, channel_names: list, channel_units: dict):
        """Update channel configuration and reset state (thread-safe)."""
        with self._lock:
            self.channel_names = channel_names
            self.channel_units = channel_units
            self._reset_state()

    def process_batch(
        self,
        batch: dict,        # {channel_name: np.ndarray of float64, length N}
        timestamp: float,   # UTC epoch of the first sample in the batch
    ) -> Optional[dict]:
        """
        Ingest one batch of N samples per channel and update the STA/LTA state.

        Returns a trigger event dict on state changes (trigger_on / trigger_off),
        or None if the state is unchanged.

        Parameters
        ----------
        batch     : dict mapping channel_name → 1-D numpy array of physical-unit
                    samples (m/s² for ACC, m/s for VEL), already bandpass-filtered.
        timestamp : UTC epoch (float) of the first sample in the batch.

        Returns
        -------
        dict or None
            On trigger_on:
            {
              "type":               "trigger_on",
              "timestamp":          float,     # UTC epoch of first trigger sample
              "ratio":              float,     # composite STA/LTA at trigger
              "channel_ratios":     dict,      # per-channel STA/LTA ratios
              "max_amplitude":      float,     # peak |amplitude| in this batch
              "triggered_channel":  str,       # channel with highest ratio
              "sta_sec":            float,
              "lta_sec":            float,
              "threshold_on":       float,
            }
            On trigger_off:
            {
              "type":               "trigger_off",
              "timestamp":          float,     # UTC epoch of first de-trigger sample
              "ratio":              float,
              "duration_sec":       float,     # seconds from trigger_on to trigger_off
              "max_amplitude":      float,     # peak amplitude during triggered phase
            }
        """
        with self._lock:
            return self._process_batch_locked(batch, timestamp)

    @property
    def triggered(self) -> bool:
        """True if the detector is currently in a triggered state."""
        return self._triggered

    @property
    def current_ratios(self) -> dict:
        """Latest composite and per-channel STA/LTA ratios (thread-safe snapshot)."""
        with self._lock:
            lta_c = self._lta_composite
            ratio_composite = (self._sta_composite / lta_c) if lta_c > 1e-30 else 0.0
            ratios = {}
            for ch in self.channel_names:
                lta_ch = self._lta_per_ch.get(ch, 0.0)
                sta_ch = self._sta_per_ch.get(ch, 0.0)
                ratios[ch] = (sta_ch / lta_ch) if lta_ch > 1e-30 else 0.0
            return {
                "composite": round(ratio_composite, 3),
                **{ch: round(v, 3) for ch, v in ratios.items()},
            }

    @property
    def lta_ready(self) -> bool:
        """True once the LTA window is sufficiently filled to allow triggering."""
        return self._lta_samples_seen >= int(self._lta_full_samples * LTA_MIN_FILL_FRACTION)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _init_params(self, sta_sec, lta_sec, threshold_on, threshold_off, lockout_sec):
        """Set algorithm parameters and precompute decay coefficients."""
        self.sta_sec        = float(sta_sec)
        self.lta_sec        = float(lta_sec)
        self.threshold_on   = float(threshold_on)
        self.threshold_off  = float(threshold_off)
        self.lockout_sec    = float(lockout_sec if lockout_sec is not None else lta_sec)

        n_sta = max(1, int(sta_sec * self.fs))
        n_lta = max(1, int(lta_sec * self.fs))

        # IIR decay coefficients (reciprocal of window length)
        self._alpha_sta = 1.0 / n_sta
        self._alpha_lta = 1.0 / n_lta
        self._lta_full_samples = n_lta

    def _reset_state(self):
        """Reset all recursive filter state (call under self._lock)."""
        self._triggered          = False
        self._trigger_start_time = None
        self._last_trigger_time  = None
        self._max_amplitude      = 0.0
        self._sta_composite      = 0.0
        self._lta_composite      = 0.0
        self._sta_per_ch         = {ch: 0.0 for ch in self.channel_names}
        self._lta_per_ch         = {ch: 0.0 for ch in self.channel_names}
        self._lta_samples_seen   = 0

    def _cf_for_channel(self, data: np.ndarray, unit: str) -> np.ndarray:
        """Compute Characteristic Function for one channel."""
        if unit == 'VEL':
            return np.abs(data)            # |x| — standard for velocity geophones
        else:
            return data ** 2              # x² — standard for acceleration

    def _process_batch_locked(self, batch: dict, timestamp: float) -> Optional[dict]:
        """Main processing — called with self._lock held."""
        alpha_s = self._alpha_sta
        alpha_l = self._alpha_lta

        acc_channels = [ch for ch in self.channel_names
                        if self.channel_units.get(ch, 'ACC') == 'ACC']
        vel_channels = [ch for ch in self.channel_names
                        if self.channel_units.get(ch, 'ACC') == 'VEL']

        # ── Build CFs ─────────────────────────────────────────────────────
        cf_arrays = {}
        for ch in self.channel_names:
            data = batch.get(ch)
            if data is None or len(data) == 0:
                continue
            unit = self.channel_units.get(ch, 'ACC')
            cf_arrays[ch] = self._cf_for_channel(np.asarray(data, dtype=np.float64), unit)

        if not cf_arrays:
            return None

        n_samples = max(len(v) for v in cf_arrays.values())
        if n_samples == 0:
            return None

        # Composite CF: sum of ACC channel CFs (vector norm²)
        # If no ACC channels present, fall back to first available CF
        if acc_channels:
            cf_composite = np.zeros(n_samples, dtype=np.float64)
            for ch in acc_channels:
                if ch in cf_arrays:
                    cf_len = min(len(cf_arrays[ch]), n_samples)
                    cf_composite[:cf_len] += cf_arrays[ch][:cf_len]
        else:
            first_ch = next(iter(cf_arrays))
            cf_composite = cf_arrays[first_ch]

        # ── Peak amplitude for this batch (physical units, all channels) ──
        peak_amp = 0.0
        for ch, data_arr in batch.items():
            if data_arr is not None and len(data_arr) > 0:
                peak_amp = max(peak_amp, float(np.max(np.abs(data_arr))))

        # ── Recursive STA/LTA update ───────────────────────────────────────
        # We process sample-by-sample to allow intra-batch trigger detection.
        # (Batch size is typically 25 samples at 100 SPS → one trigger every
        # 0.25 s resolution maximum, which is acceptable for EEW purposes.)

        trigger_event = None
        now_mono = time.monotonic()

        for i in range(n_samples):
            # Composite STA/LTA
            cf_val = float(cf_composite[i]) if i < len(cf_composite) else 0.0

            self._sta_composite = alpha_s * cf_val + (1.0 - alpha_s) * self._sta_composite

            # Freeze LTA while triggered to preserve the pre-event noise floor
            if not self._triggered:
                self._lta_composite = alpha_l * cf_val + (1.0 - alpha_l) * self._lta_composite

            # Per-channel STA/LTA
            for ch in self.channel_names:
                ch_cf_arr = cf_arrays.get(ch)
                ch_val = float(ch_cf_arr[i]) if (ch_cf_arr is not None and i < len(ch_cf_arr)) else 0.0
                self._sta_per_ch[ch] = alpha_s * ch_val + (1.0 - alpha_s) * self._sta_per_ch[ch]
                if not self._triggered:
                    self._lta_per_ch[ch] = alpha_l * ch_val + (1.0 - alpha_l) * self._lta_per_ch[ch]

            # Count samples toward LTA fill
            if self._lta_samples_seen < self._lta_full_samples:
                self._lta_samples_seen += 1

        # ── Ratio computation (end-of-batch snapshot) ─────────────────────
        lta_c = self._lta_composite
        ratio_composite = (self._sta_composite / lta_c) if lta_c > 1e-30 else 0.0

        ch_ratios = {}
        for ch in self.channel_names:
            lta_ch = self._lta_per_ch.get(ch, 0.0)
            sta_ch = self._sta_per_ch.get(ch, 0.0)
            ch_ratios[ch] = (sta_ch / lta_ch) if lta_ch > 1e-30 else 0.0

        # ── State machine ─────────────────────────────────────────────────
        if not self.lta_ready:
            # LTA window not yet filled — no triggering allowed
            return None

        if not self._triggered:
            # --- Check for trigger ON ---
            in_lockout = (
                self._last_trigger_time is not None
                and (now_mono - self._last_trigger_time) < self.lockout_sec
            )
            if not in_lockout and ratio_composite >= self.threshold_on:
                # Confirmation vote: count ACC channels above threshold_on
                n_above = sum(
                    1 for ch in acc_channels
                    if ch_ratios.get(ch, 0.0) >= self.threshold_on
                )
                confirm_needed = min(N_CONFIRM, max(1, len(acc_channels)))
                if len(acc_channels) == 0 or n_above >= confirm_needed:
                    self._triggered = True
                    self._trigger_start_time = timestamp
                    self._last_trigger_time  = now_mono
                    self._max_amplitude      = peak_amp

                    best_ch = max(ch_ratios, key=ch_ratios.get, default='')
                    trigger_event = {
                        "type":              "trigger_on",
                        "timestamp":         timestamp,
                        "ratio":             round(ratio_composite, 3),
                        "channel_ratios":    {ch: round(v, 3) for ch, v in ch_ratios.items()},
                        "max_amplitude":     round(peak_amp, 8),
                        "triggered_channel": best_ch,
                        "sta_sec":           self.sta_sec,
                        "lta_sec":           self.lta_sec,
                        "threshold_on":      self.threshold_on,
                    }
        else:
            # --- Triggered state ---
            # Track maximum amplitude during triggered phase
            self._max_amplitude = max(self._max_amplitude, peak_amp)

            # Check for trigger OFF (de-trigger)
            if ratio_composite < self.threshold_off:
                duration = timestamp - self._trigger_start_time
                trigger_event = {
                    "type":         "trigger_off",
                    "timestamp":    timestamp,
                    "ratio":        round(ratio_composite, 3),
                    "duration_sec": round(duration, 3),
                    "max_amplitude": round(self._max_amplitude, 8),
                }
                self._triggered          = False
                self._trigger_start_time = None
                self._max_amplitude      = 0.0

        return trigger_event
