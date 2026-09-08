#!/usr/bin/env python3
"""
CLI tool to reset the EEW Sensor admin password to the factory default ('cl123').
Run this script from the terminal if the web UI password is lost.
"""

import sys
import os
import bcrypt

# Ensure the backend directory is in the import path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'backend')
sys.path.insert(0, BACKEND_DIR)

try:
    # Change working directory so relative DB paths in database.py work
    os.chdir(BACKEND_DIR)
    from database import update_settings, get_settings
except ImportError as e:
    print(f"Error importing database module: {e}")
    print(f"Make sure this script is run from the correct directory.")
    sys.exit(1)

def main():
    print("=========================================")
    print("   EEW Sensor Password Reset Utility     ")
    print("=========================================")
    print("This will reset the Web UI admin password to the default: cl123")
    
    confirm = input("Are you sure you want to proceed? (y/N): ")
    if confirm.lower() != 'y':
        print("Reset cancelled.")
        sys.exit(0)
        
    print("Generating new password hash...")
    default_password = b'cl123'
    default_hash = bcrypt.hashpw(default_password, bcrypt.gensalt()).decode()
    
    try:
        update_settings({'admin_password_hash': default_hash})
        print("Success! The password has been reset.")
        print("You can now log in with the default password: cl123")
    except Exception as e:
        print(f"Failed to reset password in the database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
