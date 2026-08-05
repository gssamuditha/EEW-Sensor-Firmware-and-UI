import sqlite3
import os
db_path = os.path.join(os.path.dirname(__file__), '..', 'backend', 'eew_sensor.db')
conn = sqlite3.connect(db_path)
conn.execute("REPLACE INTO settings (key, value) VALUES ('is_configured', 'false')")
conn.commit()
conn.close()
print("Reset complete!")
