import sqlite3
import time
import queue
import threading
from threading import Lock

DB_PATH = "eew_sensor.db"
db_lock = Lock()

# --- Background DB writer ---------------------------------------------------
# The sensor loop must never block on disk I/O.  All writes go through a
# thread-safe queue and are flushed by a dedicated writer thread.
_db_write_queue = queue.Queue()
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
                    cursor = conn.cursor()
                    cursor.executemany('''
                        INSERT INTO sensor_data (timestamp, z, x, y)
                        VALUES (?, ?, ?, ?)
                    ''', batch)
                    conn.commit()
        except Exception as e:
            print(f"DB write error: {e}")

def start_db_writer():
    """Start the background DB writer thread.  Called once at startup."""
    global _writer_running
    _writer_running = True
    t = threading.Thread(target=_db_writer_loop, daemon=True, name="db-writer")
    t.start()

def stop_db_writer():
    global _writer_running
    _writer_running = False

# -----------------------------------------------------------------------------

def init_db():
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sensor_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    z REAL,
                    x REAL,
                    y REAL
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            # Insert defaults if not exist
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('targets', '[{\"name\": \"Main Server\", \"ip\": \"127.0.0.1\", \"port\": 2098, \"format\": \"corrected\"}]')")
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('latitude', '0.0')")
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('longitude', '0.0')")
            
            # Index on timestamp for faster queries
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON sensor_data(timestamp)')
            conn.commit()

    # Start the background writer after schema is ready
    start_db_writer()

def insert_batch(records):
    """Queue a batch for async DB write.  Never blocks the caller."""
    # Ensure timestamps are float (guards against any int truncation)
    safe_records = [(float(t), z, x, y) for t, z, x, y in records]
    _db_write_queue.put(safe_records)

def cleanup_old_data():
    # 24 hours = 86400 seconds
    cutoff = time.time() - 86400
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM sensor_data WHERE timestamp < ?', (cutoff,))
            deleted = cursor.rowcount
            conn.commit()
            return deleted

def get_data_for_export(start_time, end_time):
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT timestamp, z, x, y FROM sensor_data
                WHERE timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
            ''', (start_time, end_time))
            rows = cursor.fetchall()
            return rows

def get_data_for_analysis(window_seconds, decimation_factor=1):
    """
    Query the last N seconds of raw sensor data with optional decimation.
    
    For large windows (e.g. 24h = 8.6M rows at 100 SPS), decimation_factor
    controls how many rows to skip.  Uses SQL to return only every Nth row,
    keeping memory usage bounded on the RPi 3.
    
    Returns list of tuples: [(timestamp, z, x, y), ...]
    """
    cutoff = time.time() - window_seconds
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            if decimation_factor <= 1:
                cursor.execute('''
                    SELECT timestamp, z, x, y FROM sensor_data
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                ''', (cutoff,))
            else:
                # Use ROW_NUMBER to pick every Nth row server-side
                cursor.execute('''
                    SELECT timestamp, z, x, y FROM (
                        SELECT timestamp, z, x, y,
                               ROW_NUMBER() OVER (ORDER BY timestamp ASC) AS rn
                        FROM sensor_data
                        WHERE timestamp >= ?
                    ) WHERE rn % ? = 1
                    ORDER BY timestamp ASC
                ''', (cutoff, decimation_factor))
            return cursor.fetchall()


def get_data_for_range(start_time, end_time):
    """
    Query raw sensor data between two absolute timestamps at full 100 SPS.
    
    No decimation — returns ALL samples so the bandpass filter can operate
    at the original sample rate (Nyquist = 50 Hz).
    
    Max window should be capped by the caller (≤ 3600s = 360k samples).
    
    Returns list of tuples: [(timestamp, z, x, y), ...]
    """
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT timestamp, z, x, y FROM sensor_data
                WHERE timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
            ''', (start_time, end_time))
            return cursor.fetchall()


def get_data_availability():
    """
    Return the earliest and latest timestamps in the sensor_data table.
    
    Used by the frontend time-range picker to show what data is available.
    Returns dict: {"earliest": float|None, "latest": float|None, "count": int}
    """
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM sensor_data
            ''')
            row = cursor.fetchone()
            return {
                "earliest": row[0],
                "latest": row[1],
                "count": row[2] or 0,
            }


def get_settings():
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT key, value FROM settings')
            rows = cursor.fetchall()
            return {k: v for k, v in rows}

def update_settings(settings_dict):
    with db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            for key, value in settings_dict.items():
                cursor.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
            conn.commit()
