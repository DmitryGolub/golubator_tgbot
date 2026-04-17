import http.server
import logging
import sys
import threading

logger = logging.getLogger(__name__)

_CLIENT_DISCONNECT_ERRORS = (
    BrokenPipeError,
    ConnectionResetError,
    ConnectionAbortedError,
)


def _worker_alive(timeout: float = 0.5) -> bool:
    """Ping the local Celery worker via control inspect."""
    try:
        from src.celery_app import celery_app

        reply = celery_app.control.inspect(timeout=timeout).ping()
        return bool(reply)
    except Exception as exc:
        logger.warning("Celery healthcheck ping failed: %r", exc)
        return False


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
