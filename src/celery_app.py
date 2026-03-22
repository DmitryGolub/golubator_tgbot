from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging as celery_setup_logging

from src.core.config import settings
from src.core.logging_config import setup_logging

setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)


@celery_setup_logging.connect
def _on_celery_setup_logging(**kwargs):
    """Prevent Celery from overriding our logging config."""


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
        # Legacy cohort sync (kept until full migration to v2)
        "notion.sync_cohorts": {
            "task": "notion.sync_cohorts",
            "schedule": crontab(minute="*/5"),
        },
        # Bidirectional Notion sync
        "notion.push_changes": {
            "task": "notion.push_changes",
            "schedule": settings.NOTION_PUSH_INTERVAL,
        },
        "notion.backup_pull_users": {
            "task": "notion.backup_pull_users",
            "schedule": settings.NOTION_BACKUP_POLL_USERS_INTERVAL,
        },
        "notion.backup_pull_events": {
            "task": "notion.backup_pull_events",
            "schedule": settings.NOTION_BACKUP_POLL_EVENTS_INTERVAL,
        },
        # Triggers
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
