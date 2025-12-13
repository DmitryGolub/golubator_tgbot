from src.celery_app import celery_app


def main() -> None:
    # BOT_TOKEN / REDIS_* must be set in environment
    # use default scheduler but store state in container tmpfs so files aren't persisted
    celery_app.start(argv=["beat", "-l", "info", "-s", "/tmp/celerybeat-schedule"])


if __name__ == "__main__":
    main()
