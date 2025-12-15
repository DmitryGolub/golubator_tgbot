from src.celery_app import celery_app


def main() -> None:
    # BOT_TOKEN / REDIS_* must be set in environment
    # Use solo pool to avoid asyncio loop sharing issues with asyncpg in prefork
    celery_app.worker_main(argv=["worker", "-l", "info", "-P", "solo"])


if __name__ == "__main__":
    main()
