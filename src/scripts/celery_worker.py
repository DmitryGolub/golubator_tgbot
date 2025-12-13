from src.celery_app import celery_app


def main() -> None:
    # BOT_TOKEN / REDIS_* must be set in environment
    celery_app.worker_main(argv=["worker", "-l", "info"])


if __name__ == "__main__":
    main()
