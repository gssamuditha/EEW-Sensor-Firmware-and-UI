# The IP address of the central EEW aggregation server.
# Used for live ping checks on the dashboard and for data publishing.
SERVER_IP: str = "10.82.183.1"

# Base URL of the central EEW aggregation server.
# ZeroTier example:  "http://172.24.0.1:8080"
# HTTPS example:     "https://172.24.0.1:8443"
# Leave as None to disable publishing entirely (safe for development).
CENTRAL_SERVER_URL: str | None = f"http://{SERVER_IP}:8000"

# TLS certificate verification for the central server.
# False  -> skip verification (appropriate for ZeroTier LAN + self-signed certs).
# True   -> full CA chain verification (requires a CA-signed server cert).
# "path" -> path to a custom CA bundle PEM file.
TLS_VERIFY = False
