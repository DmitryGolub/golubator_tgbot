import os

from src.celery_app import celery_app
from src.core.celery_healthcheck import start_celery_health_server


def main() -> None:
    # BOT_TOKEN / REDIS_* must be set in environment
    # Use solo pool to avoid asyncio loop sharing issues with asyncpg in prefork
    port = int(os.environ.get("CELERY_HEALTH_PORT", "8081"))
    start_celery_health_server(port, mode="worker")
    celery_app.worker_main(argv=["worker", "-l", "info", "-P", "solo"])


if __name__ == "__main__":
    main()
