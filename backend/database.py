"""
database.py — SQLite persistence layer for EEW Sensor
======================================================

Tables
------
sensor_data   Rolling 2-hour ring buffer of m/s² samples.
              Used exclusively by /api/analysis/window for fast DSP queries.
              NOT the permanent archive — that lives in miniSEED files.

settings      Key-value store for all user/device configuration.

event_log     Anomaly event metadata (timestamps, max amplitude).
              Only timestamps are stored — waveform data lives in miniSEED.

Design decisions
----------------
* All disk writes are non-blocking: the hardware thread enqueues to
  _db_write_queue; a dedicated writer thread drains it.
* sensor_data retention is enforced every hour (2-hour cutoff).
* The permanent miniSEED archive is managed by mseed_writer.py and retention.py.
"""

import sqlite3
import time
import queue
import threading
import sys
from threading import Lock

DB_PATH  = "eew_sensor.db"
db_lock  = Lock()

# Default settings inserted on first run
_SETTINGS_DEFAULTS = {
    'targets':        '[{"name": "Main Server", "ip": "127.0.0.1", "port": 2098, "format": "corrected"}]',
    'latitude':       '0.0',
    'longitude':      '0.0',
    'device_name':    'CRISIS-NODE-01',
    'device_id':      'T0021',          # 5-char SEED station code
    'network_code':   'CL',             # 2-char SEED network code
    'location_code':  '00',
    'archive_root':   '/home/crisislab/data/archive',
    'retention_days': '7',
    'calibration_time': '60',
    'data_forwarding': 'true',
}

# ---------------------------------------------------------------------------
# Background DB writer
# ---------------------------------------------------------------------------

_db_write_queue: queue.Queue = queue.Queue()
_writer_running = False


def _db_writer_loop():
    """Drain _db_write_queue and write batches to SQLite in the background."""
    while _writer_running:
        try:
            batch = _db_write_queue.get(timeout=1.0)
        except queue.Empty:
            continue
        try:
            with db_lock:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.cursor().executemany(
                        'INSERT INTO sensor_data (timestamp, z, x, y) VALUES (?, ?, ?, ?)',
                        batch
                    )
                    conn.commit()
        except Exception as e:
            print(f"DB write error: {e}", file=sys.stderr)


def start_db_writer():
    global _writer_running
    _writer_running = True
    t = threading.Thread(target=_db_writer_loop, daemon=True, name="db-writer")
    t.start()


def stop_db_writer():
    global _writer_running
    _writer_running = False


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db():
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()

            # ----------------------------------------------------------------
            # sensor_data — 2-hour rolling ring buffer (m/s²)
            # Used by the Analysis dashboard for fast bandpass queries.
            # NOT the permanent archive.
            # ----------------------------------------------------------------
            c.execute('''
                CREATE TABLE IF NOT EXISTS sensor_data (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    z         REAL NOT NULL,
                    x         REAL NOT NULL,
                    y         REAL NOT NULL
                )
            ''')
            c.execute(
                'CREATE INDEX IF NOT EXISTS idx_sd_timestamp ON sensor_data(timestamp)'
            )

            # ----------------------------------------------------------------
            # settings — key/value configuration store
            # ----------------------------------------------------------------
            c.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            ''')
            for key, value in _SETTINGS_DEFAULTS.items():
                c.execute(
                    'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                    (key, value)
                )
            # NOTE: All settings use INSERT OR IGNORE so that user-configured values
            # (e.g. archive_root, device_id) are never overwritten by code defaults
            # on service restart or after an OTA update.

            # ----------------------------------------------------------------
            # event_log — anomaly event metadata
            # Stores timestamps only — waveforms are in miniSEED files.
            # ----------------------------------------------------------------
            c.execute('''
                CREATE TABLE IF NOT EXISTS event_log (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    detected_at   REAL NOT NULL,
                    start_time    REAL NOT NULL,
                    end_time      REAL,
                    max_amplitude REAL,
                    channel       TEXT,
                    notes         TEXT
                )
            ''')
            c.execute(
                'CREATE INDEX IF NOT EXISTS idx_el_detected ON event_log(detected_at)'
            )

            conn.commit()

    start_db_writer()


# ---------------------------------------------------------------------------
# 2-hour ring buffer writes
# ---------------------------------------------------------------------------

def insert_batch(records):
    """
    Queue a batch of m/s² samples for async DB write. Non-blocking.

    Parameters
    ----------
    records : list of (timestamp_float, z_ms2, x_ms2, y_ms2)
    """
    safe = [(float(t), z, x, y) for t, z, x, y in records]
    _db_write_queue.put(safe)


def cleanup_old_data():
    """
    Prune the sensor_data ring buffer to the last 2 hours.
    Called by the FastAPI lifespan background task every hour.
    """
    cutoff = time.time() - 7200   # 2 hours
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute('DELETE FROM sensor_data WHERE timestamp < ?', (cutoff,))
            deleted = c.rowcount
            conn.commit()
    return deleted


# ---------------------------------------------------------------------------
# Analysis dashboard read (fast, from ring buffer)
# ---------------------------------------------------------------------------

def get_data_for_range(start_time: float, end_time: float):
    """
    Return all 100-SPS m/s² samples between start_time and end_time from the
    2-hour ring buffer.

    Max window: 2 hours = 720,000 rows.
    Caller must cap the window before calling.

    Returns list of (timestamp, z, x, y) tuples.
    """
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute(
                'SELECT timestamp, z, x, y FROM sensor_data '
                'WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp ASC',
                (start_time, end_time)
            )
            return c.fetchall()


def get_data_availability():
    """
    Return earliest/latest timestamps in the 2-hour ring buffer.
    Used by the analysis dashboard time-range indicator.
    """
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute('SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM sensor_data')
            row = c.fetchone()
            return {
                'earliest': row[0],
                'latest':   row[1],
                'count':    row[2] or 0,
                'source':   'ring_buffer_2h',
            }


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------

def log_event(start_time: float, end_time: float = None,
              max_amplitude: float = None, channel: str = None, notes: str = None):
    """
    Record an anomaly event in the event_log table.
    Only stores metadata — waveform data is in the miniSEED archive.
    """
    now = time.time()
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            conn.cursor().execute(
                'INSERT INTO event_log '
                '(detected_at, start_time, end_time, max_amplitude, channel, notes) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (now, start_time, end_time, max_amplitude, channel, notes)
            )
            conn.commit()


def get_events(start_time: float = None, end_time: float = None, limit: int = 100):
    """Return event_log rows between optional start/end timestamps."""
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            if start_time and end_time:
                c.execute(
                    'SELECT * FROM event_log WHERE start_time >= ? AND start_time <= ? '
                    'ORDER BY detected_at DESC LIMIT ?',
                    (start_time, end_time, limit)
                )
            else:
                c.execute(
                    'SELECT * FROM event_log ORDER BY detected_at DESC LIMIT ?',
                    (limit,)
                )
            cols = [d[0] for d in c.description]
            return [dict(zip(cols, row)) for row in c.fetchall()]


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_settings() -> dict:
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute('SELECT key, value FROM settings')
            return {k: v for k, v in c.fetchall()}


def update_settings(settings_dict: dict):
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            for key, value in settings_dict.items():
                c.execute(
                    'REPLACE INTO settings (key, value) VALUES (?, ?)',
                    (key, str(value))
                )
            conn.commit()
