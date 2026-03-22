from celery import Celery
from celery.schedules import crontab

from src.core.config import settings


celery_app = Celery(
    "golubator",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "src.tasks.meeting",
        "src.tasks.notion_sync",
        "src.tasks.trigger",
    ],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "notion.sync_cohorts": {
            "task": "notion.sync_cohorts",
            "schedule": crontab(minute="*/5"),
        },
        "triggers.tick_periodic": {
            "task": "triggers.tick_periodic",
            "schedule": crontab(minute="*"),
        },
        "triggers.process_pending": {
            "task": "triggers.process_pending",
            "schedule": crontab(minute="*"),
        },
    },
)

# NOTE: worker/beat entrypoints are in src/scripts. Make sure BOT_TOKEN/REDIS envs are set.
