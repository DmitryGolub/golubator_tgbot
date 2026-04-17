import http.server
import logging
import threading

logger = logging.getLogger(__name__)


def _worker_alive(timeout: float = 0.5) -> bool:
    """Ping the local Celery worker via control inspect."""
    try:
        from src.celery_app import celery_app

        reply = celery_app.control.inspect(timeout=timeout).ping()
        return bool(reply)
    except Exception:
        logger.exception("Celery healthcheck ping failed")
        return False


def start_celery_health_server(port: int = 8081) -> None:
    """Start a lightweight HTTP health server in a daemon thread."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                alive = _worker_alive()
                status = 200 if alive else 503
                body = b'{"status":"healthy"}' if alive else b'{"status":"unhealthy"}'
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # suppress access logs

    server = http.server.HTTPServer(("0.0.0.0", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
