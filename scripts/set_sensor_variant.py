import sqlite3
import os
import sys

def main():
    print("EEW Sensor — Development Variant Switcher")
    
    # Handle command-line arguments if provided
    if len(sys.argv) == 2:
        choice = sys.argv[1].strip().upper()
        if choice not in ('3CH', '4CH', '3CH_V2'):
            print(f"[!] Invalid variant '{choice}'. Must be 3CH, 4CH, or 3CH_V2.")
            sys.exit(1)
    else:
        # Interactive prompt
        print("\nSelect the sensor hardware variant for this development machine:")
        print("  [1] 3-CH     (3× ADXL354 accelerometers only)")
        print("  [2] 4-CH     (GeoPhone + 3× ADXL354 accelerometers)")
        print("  [3] 3-CH V2  (3× ADXL354 with new pin mapping)")
        print("")
        ans = input("Enter choice [1/2/3, default=1]: ").strip()
        
        if ans == '3':
            choice = '3CH_V2'
        elif ans == '2':
            choice = '4CH'
        else:
            choice = '3CH'

    # The database is located in the backend folder when running from source
    db_path = os.path.join(os.path.dirname(__file__), '..', 'backend', 'eew_sensor.db')
    
    print(f"\n[-] Setting sensor variant to: {choice}")
    
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('sensor_variant', ?)",
            (choice,)
        )
        conn.commit()
        conn.close()
        
        print("[-] Database updated successfully.")
        print("\nRestart the development server for changes to take effect:")
        print("  sudo systemctl restart eew-sensor-dev")
        print("  (or restart uvicorn if running manually)")
    except Exception as e:
        print(f"[!] Failed to update database: {e}")

if __name__ == "__main__":
    main()
