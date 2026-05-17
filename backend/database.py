import sqlite3
import time
from threading import Lock

DB_PATH = "eew_sensor.db"
db_lock = Lock()

def init_db():
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
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
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('targets', '[{\"ip\": \"127.0.0.1\", \"port\": 2098}]')")
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('latitude', '0.0')")
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('longitude', '0.0')")
        
        # Index on timestamp for faster queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON sensor_data(timestamp)')
        conn.commit()
        conn.close()

def insert_batch(records):
    # records is list of (timestamp, z, x, y)
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.executemany('''
            INSERT INTO sensor_data (timestamp, z, x, y)
            VALUES (?, ?, ?, ?)
        ''', records)
        conn.commit()
        conn.close()

def cleanup_old_data():
    # 24 hours = 86400 seconds
    cutoff = time.time() - 86400
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sensor_data WHERE timestamp < ?', (cutoff,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted

def get_data_for_export(start_time, end_time):
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT timestamp, z, x, y FROM sensor_data
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        ''', (start_time, end_time))
        rows = cursor.fetchall()
        conn.close()
        return rows

def get_settings():
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT key, value FROM settings')
        rows = cursor.fetchall()
        conn.close()
        return {k: v for k, v in rows}

def update_settings(targets_json, lat, lon):
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', ('targets', targets_json))
        cursor.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', ('latitude', str(lat)))
        cursor.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', ('longitude', str(lon)))
        conn.commit()
        conn.close()
