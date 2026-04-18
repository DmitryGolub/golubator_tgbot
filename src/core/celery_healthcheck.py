import http.server
import logging
import os
import sys
import threading
import time
from typing import Literal

from src.core.celery_beat_scheduler import HEARTBEAT_FILE as _BEAT_HEARTBEAT

logger = logging.getLogger(__name__)

_CLIENT_DISCONNECT_ERRORS = (
    BrokenPipeError,
    ConnectionResetError,
    ConnectionAbortedError,
)

# Beat's loop ticks at least every `beat_max_loop_interval` (default 5s for
# PersistentScheduler), so 120s gives a wide safety margin while still
# catching a genuinely frozen beat loop.
_BEAT_MAX_STALE_SECONDS = 120.0


def _worker_alive(timeout: float = 3.0) -> bool:
    """Ping the local Celery worker via control inspect."""
    try:
        from src.celery_app import celery_app

        reply = celery_app.control.inspect(timeout=timeout).ping()
        return bool(reply)
    except Exception as exc:
        logger.warning("Celery healthcheck ping failed: %r", exc)
        return False


def _beat_alive(max_stale_seconds: float = _BEAT_MAX_STALE_SECONDS) -> bool:
    """Check beat health by mtime of the heartbeat file written every tick.

    HeartbeatPersistentScheduler (see celery_beat_scheduler.py) touches this
    file inside the beat loop, giving a direct liveness signal independent
    of when shelve decides to flush the schedule state.
    """
    try:
        mtime = os.path.getmtime(_BEAT_HEARTBEAT)
    except OSError:
        logger.warning(
            "Celery beat healthcheck: heartbeat file %s not found", _BEAT_HEARTBEAT
        )
        return False
    age = time.time() - mtime
    if age > max_stale_seconds:
        logger.warning(
            "Celery beat healthcheck: heartbeat stale (%.1fs > %.1fs)",
            age,
            max_stale_seconds,
        )
        return False
    return True


class _HealthHTTPServer(http.server.HTTPServer):
    """HTTPServer that routes handler errors through our JSON logger.

    Default BaseServer.handle_error writes traceback.print_exc() to stderr
    line-by-line, bypassing the JsonFormatter and breaking Loki/Grafana
    level filtering. Here we emit a single structured log record instead.
    """

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, _CLIENT_DISCONNECT_ERRORS):
            logger.debug(
                "health client dropped connection from %s: %r", client_address, exc
            )
            return
        logger.exception("Celery health server request failed from %s", client_address)


def start_celery_health_server(
    port: int = 8081, mode: Literal["worker", "beat"] = "worker"
) -> None:
    """Start a lightweight HTTP health server in a daemon thread."""

    if mode == "worker":
        check = _worker_alive
    elif mode == "beat":
        check = _beat_alive
    else:
        raise ValueError(f"Unknown celery health mode: {mode!r}")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                alive = check()
                status = 200 if alive else 503
                body = b'{"status":"healthy"}' if alive else b'{"status":"unhealthy"}'
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/metrics":
                from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

                body = generate_latest()
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def handle_one_request(self):
            try:
                super().handle_one_request()
            except _CLIENT_DISCONNECT_ERRORS as exc:
                logger.debug("health client dropped mid-request: %r", exc)

        def log_message(self, format, *args):
            pass  # suppress access logs

        def log_error(self, format, *args):
            pass  # suppress stderr error logs (handled by server.handle_error)

    server = _HealthHTTPServer(("0.0.0.0", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
