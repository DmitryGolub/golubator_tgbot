import os

from src.celery_app import celery_app
from src.core.celery_healthcheck import start_celery_health_server
from src.tasks._db import start_worker_runtime


def main() -> None:
    # BOT_TOKEN / REDIS_* must be set in environment
    # Use solo pool to avoid asyncio loop sharing issues with asyncpg in prefork
    port = int(os.environ.get("CELERY_HEALTH_PORT", "8081"))
    start_celery_health_server(port, mode="worker")
    # Bring up the shared asyncio runtime (event loop thread + Bot + engine)
    # before handing control to Celery so tasks find it ready.
    start_worker_runtime()
    celery_app.worker_main(argv=["worker", "-l", "info", "-P", "solo"])


if __name__ == "__main__":
    main()
