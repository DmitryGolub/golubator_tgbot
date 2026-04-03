from src.celery_app import celery_app
from src.core.celery_healthcheck import start_celery_health_server


def main() -> None:
    # BOT_TOKEN / REDIS_* must be set in environment
    # Use solo pool to avoid asyncio loop sharing issues with asyncpg in prefork
    start_celery_health_server(8081)
    celery_app.worker_main(argv=["worker", "-l", "info", "-P", "solo"])


if __name__ == "__main__":
    main()
