#!/usr/bin/env python3
"""
EEW Sensor — Production Entry Point
====================================
This file is compiled by Nuitka into a standalone ARM64 binary:

    python -m nuitka --standalone --follow-imports run_server.py

The resulting binary (run_server) is placed in /opt/eew-sensor/backend/
and launched by the eew-sensor systemd service.

Do NOT import uvicorn here with a string target ("main:app").
Nuitka's static analyser must be able to follow all imports; importing
`app` as a real object satisfies that requirement.
"""

import uvicorn
from main import app  # Nuitka follows this import transitively

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=80,
        log_level="info",
    )
