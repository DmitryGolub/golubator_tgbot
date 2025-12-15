from celery import Celery
from celery.schedules import crontab

from src.core.config import settings


celery_app = Celery(
    "golubator",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "src.tasks.meeting",
        "src.tasks.notification",
    ],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "meeting.cleanup_stale": {
            "task": "meeting.cleanup_stale",
            "schedule": crontab(minute="*"),  # run every minute for timely cleanup
        },
        "notifications.tick": {
            "task": "notifications.tick",
            "schedule": crontab(minute="*"),
        },
    },
)

# NOTE: worker/beat entrypoints are in src/scripts. Make sure BOT_TOKEN/REDIS envs are set.
