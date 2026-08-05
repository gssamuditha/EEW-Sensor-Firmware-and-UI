import sqlite3
import os
import subprocess
import shutil

def main():
    print("Starting Factory Reset...")
    
    # 1. Reset Database Configuration
    db_path = os.path.join(os.path.dirname(__file__), '..', 'backend', 'eew_sensor.db')
    try:
        conn = sqlite3.connect(db_path)
        
        # Drop any existing event logs
        conn.execute("DELETE FROM event_log")
        # Wipe settings (the backend will automatically re-populate defaults on next startup)
        conn.execute("DELETE FROM settings")
        conn.execute("INSERT INTO settings (key, value) VALUES ('is_configured', 'false')")
        
        conn.commit()
        conn.close()
        print("[-] Database reset complete")
    except Exception as e:
        print(f"[!] Failed to reset database: {e}")

    # 2. Clear Wi-Fi Networks (Linux Only)
    if os.name != 'nt':  # Skip if running on Windows dev machine
        try:
            print("[-] Removing saved Wi-Fi networks...")
            # Get all NetworkManager connection names
            res = subprocess.run(
                ['sudo', 'nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'],
                capture_output=True, text=True
            )
            for line in res.stdout.split('\n'):
                if '802-11-wireless' in line.lower() or ':wifi' in line.lower():
                    name = line.split(':')[0]
                    if name:
                        # Delete the connection
                        subprocess.run(['sudo', 'nmcli', 'connection', 'delete', name], capture_output=True)
            print("[-] Wi-Fi networks cleared")
        except Exception as e:
            print(f"[!] Failed to clear Wi-Fi: {e}")
    else:
        print("[-] Skipping Wi-Fi clear (running on Windows)")

    # 3. Clear Historical Waveform Data
    # (Matches the default archive root in database.py)
    archive_path = "/home/crisislab/data/archive"
    if os.path.exists(archive_path):
        print("[-] Clearing miniSEED archive...")
        for filename in os.listdir(archive_path):
            filepath = os.path.join(archive_path, filename)
            try:
                if os.path.isfile(filepath) or os.path.islink(filepath):
                    os.unlink(filepath)
                elif os.path.isdir(filepath):
                    shutil.rmtree(filepath)
            except Exception as e:
                print(f"[!] Failed to delete {filepath}: {e}")

    print("\n Factory Reset Complete! The device is ready for production imaging.")

if __name__ == "__main__":
    main()
