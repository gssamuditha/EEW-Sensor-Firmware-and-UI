"""
database.py — SQLite persistence layer for EEW Sensor
======================================================

Tables
------
settings      Key-value store for all user/device configuration.

event_log     Anomaly event metadata (timestamps, max amplitude).
              Only timestamps are stored — waveform data lives in miniSEED.

Design decisions
----------------
* Waveform data is NOT stored here — that lives in the miniSEED SDS archive
  managed by mseed_writer.py and retention.py.
* SQLite is config/events only: fast reads, tiny file, no retention issues.
"""

import sqlite3
import time
from threading import Lock

DB_PATH = "eew_sensor.db"
db_lock = Lock()

# Default settings inserted on first run
_SETTINGS_DEFAULTS = {
    'targets':          '[{"name": "Crisislab Server", "ip": "10.241.144.172", "port": 2098, "format": "corrected"}]',
    'latitude':         '0.0',
    'longitude':        '0.0',
    'device_name':      'CRISIS-NODE-01',
    'device_id':        'T0021',          # 5-char SEED station code
    'network_code':     'CL',             # 2-char SEED network code
    'location_code':    '00',
    'archive_root':     '/home/crisislab/data/archive',
    'retention_days':   '7',
    'calibration_time': '60',
    'data_forwarding':  'true',
    'is_configured':    'false',
    # Hardware variant: '3CH' (ADXL only) or '4CH' (GeoPhone + ADXL)
    # Set by setup_service.sh at installation time. Can be overridden here.
    'sensor_variant':   '3CH',

    # -------------------------------------------------------------------
    # STA/LTA P-wave detection parameters
    # -------------------------------------------------------------------
    # All values are strings (SQLite key-value store) and parsed to float
    # at runtime by the detector initialisation code in sensor.py.
    'detection_enabled':  'true',
    'sta_sec':            '0.5',     # Short-term average window (seconds)
    'lta_sec':            '10.0',    # Long-term average window (seconds)
    'threshold_on':       '3.5',     # STA/LTA ratio to trigger ON
    'threshold_off':      '1.5',     # STA/LTA ratio to de-trigger (hysteresis)
    'detect_low_hz':      '2.0',     # Pre-filter lower cutoff (Hz)
    'detect_high_hz':     '15.0',    # Pre-filter upper cutoff (Hz)
}


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db():
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()

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
            # NOTE: INSERT OR IGNORE preserves any user-configured values
            # (e.g. archive_root, device_id) across service restarts and OTA updates.

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

            # Migration: drop the legacy sensor_data ring buffer table if it
            # still exists from an older deployment. All waveform data now lives
            # exclusively in the miniSEED SDS archive.
            c.execute('DROP TABLE IF EXISTS sensor_data')

            conn.commit()


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
