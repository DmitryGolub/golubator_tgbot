from src.celery_app import celery_app
from src.core.celery_healthcheck import start_celery_health_server


def main() -> None:
    # BOT_TOKEN / REDIS_* must be set in environment
    # use default scheduler but store state in container tmpfs so files aren't persisted
    start_celery_health_server(8081)
    celery_app.start(argv=["beat", "-l", "info", "-s", "/tmp/celerybeat-schedule"])


if __name__ == "__main__":
    main()
