"""
mseed_writer.py — SeisComP Data Structure (SDS) miniSEED Archive Writer
=========================================================================
Buffers raw signed 32-bit ADC counts at 100 SPS and flushes them every
FLUSH_INTERVAL seconds to daily miniSEED binary files on disk.

SDS Path Structure
------------------
    <archive_root>/YYYY/NET/STA/CHAN.D/NET.STA.LOC.CHAN.D.YYYY.JDAY

Example (device_id='T0021', network='CL', location='00', channel='ENZ'):
    /opt/data/archive/2026/CL/T0021/ENZ.D/CL.T0021.00.ENZ.D.2026.201

Usage
-----
    from mseed_writer import mseed_writer

    # Enqueue one decimated sample (post-IIR, post-decimation raw int32 counts)
    mseed_writer.enqueue(timestamp_float, z_cnt_int, x_cnt_int, y_cnt_int)

    # Start the background flush thread (called once at startup)
    mseed_writer.start()

    # Force-flush remaining buffer on shutdown
    mseed_writer.flush()

Data Integrity
--------------
    * Uses open(path, 'ab') for atomic appends — never truncates existing data.
    * Each flush creates a self-contained miniSEED record anchored to the exact
      first-sample timestamp of that batch.
    * SEED encoding: INT32 (Steim-1 compressed by ObsPy).
    * Record length: 512 bytes (standard for low-power embedded loggers).
"""

import os
import queue
import threading
import time
import sys
from pathlib import Path

import numpy as np

try:
    from obspy import Trace, Stream, UTCDateTime
    from obspy import read as obspy_read
    OBSPY_AVAILABLE = True
except ImportError:
    OBSPY_AVAILABLE = False
    print("WARNING: ObsPy not available — miniSEED writing disabled.", file=sys.stderr)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FLUSH_INTERVAL = 60          # seconds between SD-card writes
SAMPLING_RATE  = 100.0       # Hz
CHANNEL_NAMES  = ['ENZ', 'ENN', 'ENE']
MSEED_RECLEN   = 512         # miniSEED record length in bytes

# Default SDS archive root (overridden by DB settings at runtime)
DEFAULT_ARCHIVE_ROOT = '/home/crisislab/data/archive'
if sys.platform == 'win32':
    # Windows development mock path
    DEFAULT_ARCHIVE_ROOT = os.path.join(os.path.dirname(__file__), '..', 'data', 'archive')
    DEFAULT_ARCHIVE_ROOT = os.path.abspath(DEFAULT_ARCHIVE_ROOT)


# ---------------------------------------------------------------------------
# SDS Path Builder
# ---------------------------------------------------------------------------

def sds_filepath(archive_root: str, network: str, station: str,
                 location: str, channel: str, starttime) -> str:
    """
    Return the full SDS file path for a given channel and day.

    Format: <root>/YYYY/NET/STA/CHAN.D/NET.STA.LOC.CHAN.D.YYYY.JDAY

    Parameters
    ----------
    starttime : obspy.UTCDateTime or float epoch
    """
    if isinstance(starttime, (int, float)):
        t = UTCDateTime(starttime)
    else:
        t = starttime

    year  = t.year
    jday  = t.julday                       # day-of-year, 1-indexed
    net   = network.upper()
    sta   = station.upper()
    loc   = location
    chan  = channel.upper()

    # Directory: <root>/YYYY/NET/STA/CHAN.D/
    dirpath = os.path.join(archive_root, str(year), net, sta, f"{chan}.D")
    # Filename: NET.STA.LOC.CHAN.D.YYYY.JDAY
    filename = f"{net}.{sta}.{loc}.{chan}.D.{year}.{jday:03d}"

    return os.path.join(dirpath, filename)


# ---------------------------------------------------------------------------
# MiniSEEDWriter
# ---------------------------------------------------------------------------

class MiniSEEDWriter:
    """
    Thread-safe writer that buffers raw int32 ADC counts and flushes them
    to SDS miniSEED files every FLUSH_INTERVAL seconds.

    The main hardware loop calls enqueue() — a non-blocking, lock-free
    operation using a bounded Queue. The flush happens in a dedicated
    daemon thread so disk I/O never touches the sensor read loop.
    """

    def __init__(self):
        self._queue   = queue.Queue(maxsize=12000)   # ~2 min of samples at 100 SPS
        self._thread  = None
        self._running = False

        # Settings refreshed every 60 s from DB
        self._archive_root   = DEFAULT_ARCHIVE_ROOT
        self._network_code   = 'CL'
        self._device_id      = 'T0021'   # 5-char SEED station code
        self._location_code  = '00'
        self._settings_lock  = threading.Lock()
        self._write_lock     = threading.Lock()
        self._last_settings_refresh = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Start the background flush thread. Call once at application startup."""
        if self._running:
            return
        self._refresh_settings()
        self._running = True
        self._thread  = threading.Thread(
            target=self._flush_loop, daemon=True, name="mseed-writer"
        )
        self._thread.start()

    def stop(self):
        """Signal the flush thread to stop after one final flush."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)

    def enqueue(self, timestamp: float, z_cnt: int, x_cnt: int, y_cnt: int):
        """
        Queue one decimated sample (non-blocking).

        Parameters
        ----------
        timestamp : Unix epoch float (time of first sample in any batch)
        z_cnt     : signed int32 ADC count, Z-axis (post-IIR, post-decimation)
        x_cnt     : signed int32 ADC count, N-axis
        y_cnt     : signed int32 ADC count, E-axis
        """
        try:
            self._queue.put_nowait((timestamp, z_cnt, x_cnt, y_cnt))
        except queue.Full:
            pass   # Drop rather than block the hardware thread

    def flush(self):
        """Force-flush whatever is buffered. Call on shutdown."""
        self._drain_and_write()

    # ------------------------------------------------------------------
    # Settings refresh
    # ------------------------------------------------------------------

    def _refresh_settings(self):
        """Pull network/station codes and archive root from the DB settings table."""
        try:
            from database import get_settings
            s = get_settings()
            with self._settings_lock:
                self._archive_root  = s.get('archive_root',  DEFAULT_ARCHIVE_ROOT)
                self._network_code  = s.get('network_code',  'CL').upper()
                self._device_id     = s.get('device_id',     'T0021').upper()
                self._location_code = s.get('location_code', '00')
        except Exception as e:
            print(f"mseed_writer: settings refresh error: {e}", file=sys.stderr)
        self._last_settings_refresh = time.monotonic()

    # ------------------------------------------------------------------
    # Flush loop
    # ------------------------------------------------------------------

    def _flush_loop(self):
        """Run in daemon thread. Flushes buffer every FLUSH_INTERVAL seconds."""
        next_flush = time.monotonic() + FLUSH_INTERVAL
        while self._running:
            now = time.monotonic()

            # Refresh settings every 60 s
            if now - self._last_settings_refresh > 60.0:
                self._refresh_settings()

            if now >= next_flush:
                self._drain_and_write()
                next_flush = time.monotonic() + FLUSH_INTERVAL

            time.sleep(1.0)   # 1-second polling — SD writes happen at flush time

        # Final flush on stop
        self._drain_and_write()

    # ------------------------------------------------------------------
    # Core drain + write
    # ------------------------------------------------------------------

    def _drain_and_write(self):
        """
        Drain the queue into per-channel NumPy arrays, then write miniSEED.
        Handles day-boundary splits automatically — if the buffer spans
        midnight (UTC), it writes two separate records to the correct daily files.
        """
        with self._write_lock:
            if not OBSPY_AVAILABLE:
                # Discard without error — running in a no-ObsPy environment
                while not self._queue.empty():
                    try:
                        self._queue.get_nowait()
                    except queue.Empty:
                        break
                return

        # Collect all queued samples
        samples = []
        while True:
            try:
                samples.append(self._queue.get_nowait())
            except queue.Empty:
                break

        if not samples:
            return

        # Convert efficiently using list comprehensions to avoid object boxing
        timestamps = np.array([s[0] for s in samples], dtype=np.float64)
        z_counts   = np.array([s[1] for s in samples], dtype=np.int32)
        x_counts   = np.array([s[2] for s in samples], dtype=np.int32)
        y_counts   = np.array([s[3] for s in samples], dtype=np.int32)

        # Split at UTC midnight boundaries so each chunk maps to one daily file
        segments = self._split_at_day_boundaries(timestamps, z_counts, x_counts, y_counts)

        with self._settings_lock:
            net = self._network_code
            sta = self._device_id
            loc = self._location_code
            root = self._archive_root

        for seg_timestamps, seg_z, seg_x, seg_y, seg_starttime in segments:
            for ch, data in zip(CHANNEL_NAMES, [seg_z, seg_x, seg_y]):
                self._write_segment(root, net, sta, loc, ch, seg_starttime, data)

    def _split_at_day_boundaries(self, timestamps, z, x, y):
        """
        Split arrays at UTC midnight boundaries.
        Returns a list of (timestamps, z, x, y, UTCDateTime_starttime) tuples.
        """
        if len(timestamps) == 0:
            return []

        segments = []
        seg_start_idx = 0
        start_day = UTCDateTime(timestamps[0]).julday
        start_year = UTCDateTime(timestamps[0]).year

        for i in range(1, len(timestamps)):
            t = UTCDateTime(timestamps[i])
            if t.julday != start_day or t.year != start_year:
                # Day boundary — emit current segment
                seg_start = UTCDateTime(timestamps[seg_start_idx])
                segments.append((
                    timestamps[seg_start_idx:i],
                    z[seg_start_idx:i],
                    x[seg_start_idx:i],
                    y[seg_start_idx:i],
                    seg_start,
                ))
                seg_start_idx = i
                start_day  = t.julday
                start_year = t.year

        # Final segment
        seg_start = UTCDateTime(timestamps[seg_start_idx])
        segments.append((
            timestamps[seg_start_idx:],
            z[seg_start_idx:],
            x[seg_start_idx:],
            y[seg_start_idx:],
            seg_start,
        ))
        return segments

    def _write_segment(self, root, net, sta, loc, channel, starttime, data: np.ndarray):
        """Write a single channel segment as miniSEED, appending to the daily file."""
        if len(data) == 0:
            return

        filepath = sds_filepath(root, net, sta, loc, channel, starttime)

        # Ensure directory exists
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
        except OSError as e:
            print(f"mseed_writer: cannot create directory for {filepath}: {e}", file=sys.stderr)
            return

        # Build ObsPy Trace
        tr = Trace(data=data.astype(np.int32))
        tr.stats.network       = net
        tr.stats.station       = sta
        tr.stats.location      = loc
        tr.stats.channel       = channel
        tr.stats.sampling_rate = SAMPLING_RATE
        tr.stats.starttime     = starttime

        # Serialize to in-memory miniSEED bytes
        import io
        buf = io.BytesIO()
        try:
            tr.write(buf, format='MSEED', encoding='INT32', reclen=MSEED_RECLEN)
        except Exception as e:
            # Catch backwards time jumps from NTP clock corrections
            print(f"mseed_writer: ObsPy write error (dropped chunk) for {filepath}: {e}", file=sys.stderr)
            return
        
        mseed_bytes = buf.getvalue()

        # Atomic append to daily file
        try:
            with open(filepath, 'ab') as f:
                f.write(mseed_bytes)
        except OSError as e:
            print(f"mseed_writer: write error for {filepath}: {e}", file=sys.stderr)

    # ------------------------------------------------------------------
    # Query helpers (called from API endpoints)
    # ------------------------------------------------------------------

    def get_settings_snapshot(self):
        """Return current network/station settings as a dict."""
        with self._settings_lock:
            return {
                'archive_root':  self._archive_root,
                'network_code':  self._network_code,
                'device_id':     self._device_id,
                'location_code': self._location_code,
            }

    def get_archive_availability(self) -> dict:
        """
        Scan the SDS archive and return the earliest and latest timestamps.
        Reads file names only — no file I/O into miniSEED content.
        Returns dict: {earliest: float|None, latest: float|None}
        """
        with self._settings_lock:
            root = self._archive_root

        earliest_epoch = None
        latest_epoch   = None

        if not os.path.isdir(root):
            return {'earliest': None, 'latest': None}

        for dirpath, _dirs, filenames in os.walk(root):
            for fname in filenames:
                # Filename format: NET.STA.LOC.CHAN.D.YYYY.JDAY
                parts = fname.split('.')
                if len(parts) < 7:
                    continue
                try:
                    year = int(parts[5])
                    jday = int(parts[6])
                    t = UTCDateTime(year=year, julday=jday)
                    epoch = float(t)
                    if earliest_epoch is None or epoch < earliest_epoch:
                        earliest_epoch = epoch
                    # End of that day
                    end_epoch = float(UTCDateTime(year=year, julday=jday) + 86400)
                    if latest_epoch is None or end_epoch > latest_epoch:
                        latest_epoch = end_epoch
                except (ValueError, IndexError):
                    continue

        return {'earliest': earliest_epoch, 'latest': latest_epoch}

    def get_archive_size_bytes(self) -> int:
        """Return total size of all miniSEED files in the archive in bytes."""
        with self._settings_lock:
            root = self._archive_root

        total = 0
        if not os.path.isdir(root):
            return 0

        for dirpath, _dirs, filenames in os.walk(root):
            for fname in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, fname))
                except OSError:
                    pass
        return total


# ---------------------------------------------------------------------------
# Module-level read helper (called from ProcessPoolExecutor subprocesses)
# ---------------------------------------------------------------------------

def read_waveform_range(t_start, t_end, settings: dict = None) -> object:
    """
    Read a time-windowed waveform slice from the SDS archive using ObsPy.

    This function is designed to be called from a ProcessPoolExecutor
    subprocess — it must be importable as a top-level function.

    Parameters
    ----------
    t_start  : obspy.UTCDateTime or float epoch
    t_end    : obspy.UTCDateTime or float epoch
    settings : dict from get_settings_snapshot() — avoids DB call in subprocess

    Returns
    -------
    obspy.Stream or None on error
    """
    if not OBSPY_AVAILABLE:
        return None

    if isinstance(t_start, (int, float)):
        t_start = UTCDateTime(t_start)
    if isinstance(t_end, (int, float)):
        t_end = UTCDateTime(t_end)

    # Resolve settings
    if settings is None:
        try:
            from database import get_settings
            s = get_settings()
            root = s.get('archive_root', DEFAULT_ARCHIVE_ROOT)
            net  = s.get('network_code',  'CL').upper()
            sta  = s.get('device_id',     'T0021').upper()
            loc  = s.get('location_code', '00')
        except Exception:
            root = DEFAULT_ARCHIVE_ROOT
            net, sta, loc = 'CL', 'T0021', '00'
    else:
        root = settings.get('archive_root', DEFAULT_ARCHIVE_ROOT)
        net  = settings.get('network_code', 'CL').upper()
        sta  = settings.get('device_id',    'T0021').upper()
        loc  = settings.get('location_code','00')

    # Collect daily files that overlap the requested window
    streams = Stream()
    current = UTCDateTime(year=t_start.year, julday=t_start.julday)
    end_day  = UTCDateTime(year=t_end.year,   julday=t_end.julday)

    while current <= end_day:
        for ch in CHANNEL_NAMES:
            fpath = sds_filepath(root, net, sta, loc, ch, current)
            if os.path.isfile(fpath):
                try:
                    st = obspy_read(fpath, starttime=t_start, endtime=t_end)
                    streams += st
                except Exception as e:
                    print(f"mseed_writer: read error {fpath}: {e}", file=sys.stderr)
        current += 86400   # advance one day

    return streams if len(streams) > 0 else None


# ---------------------------------------------------------------------------
# Singleton instance
# ---------------------------------------------------------------------------

mseed_writer = MiniSEEDWriter()
