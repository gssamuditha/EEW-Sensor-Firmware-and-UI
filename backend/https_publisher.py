"""
https_publisher.py — HTTPS Telemetry & Metadata Publisher
==========================================================
Pushes two types of JSON payloads to the central EEW aggregation server
via HTTPS POST:

  1. Telemetry  — system health snapshot every TELEMETRY_INTERVAL_SEC seconds
                  { cpu_temp_c, cpu_percent, disk_*, uptime_sec, avg_sps, ... }

  2. Metadata   — device identity payload
                  { device_id, owner, lat/lon, elevation, floor info }
                  Sent once automatically at node startup (after first
                  successful telemetry push) and once on every settings save.

Transport Design
----------------
* HTTPS POST with JSON body — no application-level API key.
* Uses httpx.Client (synchronous) inside a dedicated daemon thread —
  completely isolated from the FastAPI asyncio event loop and the sensor
  hardware thread (zero timing impact on waveform acquisition).
* Connection pooling: TLS handshake is performed once per session, not
  per 30-second request.
* Retry policy:
    - HTTP 2xx          → success
    - HTTP 4xx          → log + do not retry (config error)
    - HTTP 5xx / timeout→ retry up to MAX_RETRIES with RETRY_BACKOFF_SEC
    - Connection error  → retry with exponential backoff (5 s → 15 s → 60 s)

Authentication & Security
--------------------------
No application-level API key is used. Authentication is handled entirely
by the ZeroTier overlay network:
  * Only nodes explicitly authorised in the ZeroTier controller can reach
    the server's IP at all — unauthorised devices cannot route packets to it.
  * The server can identify each sensor by its stable ZeroTier-assigned IP
    address (plus the device_id field in the JSON payload for semantics).
  * ZeroTier encrypts all traffic in transit, so a self-signed TLS cert
    (or even plain HTTP over the ZeroTier interface) is acceptable.

ZeroTier LAN Deployment
------------------------
TLS_VERIFY is False by default — self-signed certs are the norm on private
ZeroTier networks and ZeroTier already handles link-layer encryption.
Set TLS_VERIFY = True (or a CA bundle path) for CA-signed server certs.

Configuration
-------------
All server config is hardcoded here — NOT exposed in the frontend UI.
Set CENTRAL_SERVER_URL before deployment.
"""

import json
import logging
import queue
import sys
import threading
import time

import psutil

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Central Server Configuration
# Set these values before deployment — not editable by end users.
# ---------------------------------------------------------------------------

# Base URL of the central EEW aggregation server.
# ZeroTier example:  "http://172.24.0.1:8080"
# HTTPS example:     "https://172.24.0.1:8443"
# Leave as None to disable publishing entirely (safe for development).
CENTRAL_SERVER_URL: str | None = "http://127.0.0.1:8080"   # TODO: set before deployment

# No API key — authentication is handled by the ZeroTier controller.
# Only nodes explicitly authorised in the ZeroTier network can reach this server.
# The server identifies each sensor by its stable ZeroTier-assigned source IP.

# TLS certificate verification.
# False  → skip verification (appropriate for ZeroTier LAN + self-signed certs).
# True   → full CA chain verification (requires a CA-signed server cert).
# "path" → path to a custom CA bundle PEM file.
TLS_VERIFY: bool | str = False

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

TELEMETRY_INTERVAL_SEC: int = 30    # heartbeat cadence
REQUEST_TIMEOUT_SEC: int = 10       # connect + read timeout per attempt
MAX_RETRIES: int = 3                # attempts before giving up for this cycle
RETRY_BACKOFF_SEC: int = 5          # wait between retries on 5xx / timeout


# ---------------------------------------------------------------------------
# CPU temperature helper (Raspberry Pi only)
# ---------------------------------------------------------------------------

def _read_cpu_temp() -> float | None:
    """
    Read the SoC temperature from the Linux thermal zone.

    Returns temperature in degrees Celsius, or None on platforms
    where the thermal zone file is not available (e.g. Windows dev).
    """
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            return int(f.read().strip()) / 1000.0
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# HttpsPublisher
# ---------------------------------------------------------------------------

class HttpsPublisher:
    """
    Background HTTPS publisher for system telemetry and device metadata.

    Lifecycle (called from main.py):
        https_publisher.start(sensor_manager)   # at application startup
        https_publisher.stop()                  # at application shutdown

    On user settings save (called from api_set_settings):
        https_publisher.send_metadata(payload)  # enqueue for immediate push
        https_publisher.refresh_settings()      # pull updated device_id from DB
    """

    def __init__(self):
        self._sensor_manager = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._client = None                         # httpx.Client, created in start()

        # Thread-safe queue for on-demand metadata pushes
        self._metadata_queue: queue.Queue = queue.Queue(maxsize=10)

        # Cached device_id — updated from DB by refresh_settings()
        self._device_id: str = "UNKNW"
        self._settings_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, sensor_manager) -> None:
        """
        Start the background publisher thread.
        Call once inside the FastAPI lifespan, after sensor init.
        """
        if self._running:
            return

        self._sensor_manager = sensor_manager
        self._refresh_settings()

        if CENTRAL_SERVER_URL is None:
            logger.warning(
                "https_publisher: CENTRAL_SERVER_URL is not configured — "
                "telemetry and metadata publishing is disabled."
            )
            return

        # Import here so the module can be loaded in environments
        # without httpx installed (e.g. if the operator hasn't run pip install yet)
        try:
            import httpx as _httpx
        except ImportError:
            logger.error(
                "https_publisher: 'httpx' is not installed. "
                "Run: pip install httpx"
            )
            return

        self._client = _httpx.Client(
            verify=TLS_VERIFY,
            timeout=REQUEST_TIMEOUT_SEC,
            headers={
                "Content-Type": "application/json",
                # No API key — ZeroTier network-layer authorisation is sufficient.
            },
        )

        self._running = True
        self._thread = threading.Thread(
            target=self._publisher_loop,
            daemon=True,
            name="https-publisher",
        )
        self._thread.start()
        logger.info(
            f"https_publisher: started — target server: {CENTRAL_SERVER_URL} "
            f"| interval: {TELEMETRY_INTERVAL_SEC}s | tls_verify: {TLS_VERIFY}"
        )

    def stop(self) -> None:
        """Gracefully stop the publisher thread and close the HTTP session."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=15)
        if self._client:
            self._client.close()
            self._client = None

    def send_metadata(self, payload: dict) -> None:
        """
        Enqueue a metadata payload for immediate dispatch to the central server.
        This is non-blocking — the background thread drains the queue.

        Called by api_set_settings() in main.py after every settings save.
        Also called internally at startup via _send_startup_metadata().
        """
        if CENTRAL_SERVER_URL is None:
            return
        try:
            self._metadata_queue.put_nowait(payload)
        except queue.Full:
            logger.warning(
                "https_publisher: metadata queue is full — payload dropped. "
                "This should not happen under normal usage."
            )

    def refresh_settings(self) -> None:
        """
        Re-read device_id from the SQLite settings table.
        Call this after a settings save so the next telemetry payload
        carries the updated device identity.
        """
        self._refresh_settings()

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------

    def _publisher_loop(self) -> None:
        """
        Main loop running in the 'https-publisher' daemon thread.

        Responsibilities (in priority order per iteration):
          1. Drain any pending metadata payloads immediately.
          2. Send a telemetry heartbeat when the interval has elapsed.
          3. Send startup metadata once after the first successful telemetry push.
        """
        # Fire telemetry immediately on first iteration
        next_telemetry_at = time.monotonic()
        startup_metadata_sent = False

        while self._running:
            now = time.monotonic()

            # ---- Priority 1: flush pending metadata (on-demand) ----
            while not self._metadata_queue.empty():
                try:
                    payload = self._metadata_queue.get_nowait()
                    self._post("/api/ingest/metadata", payload)
                except queue.Empty:
                    break

            # ---- Priority 2: periodic telemetry heartbeat ----
            if now >= next_telemetry_at:
                telemetry = self._build_telemetry_payload()
                success = self._post("/api/ingest/telemetry", telemetry)
                next_telemetry_at = time.monotonic() + TELEMETRY_INTERVAL_SEC

                # ---- Priority 3: one-time startup metadata ----
                if success and not startup_metadata_sent:
                    startup_metadata_sent = True
                    self._send_startup_metadata()

            # Sleep 1 s between iterations — low CPU, responsive enough
            time.sleep(1.0)

    # ------------------------------------------------------------------
    # Payload builders
    # ------------------------------------------------------------------

    def _build_telemetry_payload(self) -> dict:
        """
        Collect system health metrics and return a telemetry dict.

        Metrics:
          cpu_temp_c        — SoC temperature (°C), None on non-Pi platforms
          cpu_percent       — CPU utilisation (0–100), non-blocking snapshot
          disk_percent      — root filesystem usage percentage
          uptime_sec        — seconds since last boot
          avg_sps           — rolling average sensor samples/sec
        """
        with self._settings_lock:
            device_id = self._device_id

        disk = psutil.disk_usage('/')
        uptime_sec = int(time.time() - psutil.boot_time())

        sm = self._sensor_manager
        return {
            "device_id":        device_id,
            "ts":               time.time(),
            "cpu_temp_c":       _read_cpu_temp(),
            "cpu_percent":      psutil.cpu_percent(interval=None),
            "disk_percent":     round(disk.percent, 1),
            "uptime_sec":       uptime_sec,
            "avg_sps":          sm.avg_sps if sm else None,
        }

    def _send_startup_metadata(self) -> None:
        """
        Build and push a metadata payload from current DB settings.
        Called automatically once after the first successful telemetry push.
        """
        try:
            from database import get_settings
            s = get_settings()
            payload = {
                "device_id":    s.get("device_id",      "UNKNW"),
                "ts":           time.time(),
                "device_name":  s.get("device_name",    "CRISIS-NODE-01"),
                "owner_name":   s.get("owner_name",     ""),
                "owner_email":  s.get("owner_email",    ""),
                "latitude":     float(s.get("latitude",  0.0)),
                "longitude":    float(s.get("longitude", 0.0)),
                "elevation_m":  float(s.get("elevation", 0.0)),
                "floor":        int(s.get("floor_unit",  0)),
                "total_floors": int(s.get("total_floors", 1)),
            }
            self._post("/api/ingest/metadata", payload)
        except Exception as e:
            logger.error(f"https_publisher: startup metadata failed: {e}")

    # ------------------------------------------------------------------
    # HTTP transport
    # ------------------------------------------------------------------

    def _post(self, endpoint: str, payload: dict) -> bool:
        """
        POST a JSON payload to the central server.

        Retry policy:
          - HTTP 2xx          → return True (success)
          - HTTP 4xx          → log error, return False (do NOT retry —
                                likely a config error, retrying won't help)
          - HTTP 5xx / timeout→ retry up to MAX_RETRIES with RETRY_BACKOFF_SEC
          - Connection error  → retry with RETRY_BACKOFF_SEC

        Returns True if the server acknowledged the payload, False otherwise.
        """
        if self._client is None:
            return False

        url = CENTRAL_SERVER_URL.rstrip('/') + endpoint
        body = json.dumps(payload)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._client.post(url, content=body)

                if response.status_code in (200, 201, 204):
                    logger.debug(
                        f"https_publisher: {endpoint} → HTTP {response.status_code} ✓"
                    )
                    return True

                if 400 <= response.status_code < 500:
                    # Client error — retrying won't help; alert the operator
                    logger.error(
                        f"https_publisher: {endpoint} → HTTP {response.status_code} "
                        f"(client error, check API key / URL): "
                        f"{response.text[:300]}"
                    )
                    return False

                # 5xx — server-side problem, worth retrying
                logger.warning(
                    f"https_publisher: {endpoint} → HTTP {response.status_code} "
                    f"(attempt {attempt}/{MAX_RETRIES})"
                )

            except Exception as e:
                # Covers httpx.ConnectError, httpx.TimeoutException, etc.
                logger.warning(
                    f"https_publisher: {endpoint} → connection error "
                    f"(attempt {attempt}/{MAX_RETRIES}): {type(e).__name__}: {e}"
                )

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SEC)

        logger.error(
            f"https_publisher: {endpoint} → all {MAX_RETRIES} attempts failed. "
            f"Will retry on the next cycle."
        )
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh_settings(self) -> None:
        """Pull the current device_id from the SQLite settings table."""
        try:
            from database import get_settings
            s = get_settings()
            with self._settings_lock:
                self._device_id = s.get("device_id", "UNKNW")
        except Exception as e:
            logger.warning(f"https_publisher: settings refresh error: {e}")


# ---------------------------------------------------------------------------
# Singleton instance — imported by main.py
# ---------------------------------------------------------------------------

https_publisher = HttpsPublisher()
