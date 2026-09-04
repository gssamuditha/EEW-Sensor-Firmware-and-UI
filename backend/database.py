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
import random
import string

def _generate_device_id():
    chars = string.ascii_uppercase + string.digits
    return 'C' + ''.join(random.choice(chars) for _ in range(4))

DB_PATH = "eew_sensor.db"
db_lock = Lock()

# Default settings inserted on first run
_SETTINGS_DEFAULTS = {
    'targets':          '[{"name": "Crisislab Server", "ip": "10.241.144.172", "port": 2098, "format": "corrected"}]',
    'latitude':         '0.0',
    'longitude':        '0.0',
    'device_name':      'CRISIS-NODE-01',
    'device_id':        _generate_device_id(),  # Auto-generated unique ID on first boot
    'network_code':     'CL',             # 2-char SEED network code
    'location_code':    '00',
    'archive_root':     '/home/crisislab/data/archive',
    'retention_days':   '7',
    'calibration_time': '60',
    'data_forwarding':  'true',
    'is_configured':    'false',
    # Hardware variant: '3CH', '4CH' (GeoPhone), or '3CH_V2'
    # Set by setup_service.sh at installation time. Can be overridden here.
    'sensor_variant':   '3CH',
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

            # ------------------------------------------------------------------
            # Default admin password — set to 'cl123' on first boot only.
            # The hash is generated at runtime so it is never stored as plaintext.
            # Users should change this via the web UI Settings → Admin Password.
            # ------------------------------------------------------------------
            c.execute("SELECT value FROM settings WHERE key='admin_password_hash'")
            row = c.fetchone()
            if row is None or not row[0]:
                import bcrypt as _bcrypt_init
                _default_hash = _bcrypt_init.hashpw(b'cl123', _bcrypt_init.gensalt()).decode()
                c.execute(
                    "REPLACE INTO settings (key, value) VALUES ('admin_password_hash', ?)",
                    (_default_hash,)
                )

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
