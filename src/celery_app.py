import time

from celery import Celery
from celery.schedules import crontab
from celery.signals import (
    setup_logging as celery_setup_logging,
    task_postrun,
    task_prerun,
)
from prometheus_client import Counter, Histogram

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
        "src.tasks.weekly_survey",
        "src.tasks.survey_alerts",
        "src.tasks.survey_escalation",
        "src.tasks.caldav",
    ],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Hard guard so -P solo can't be pinned forever by a hung external I/O.
    task_soft_time_limit=180,
    task_time_limit=240,
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=None,
    broker_transport_options={
        "fanout_prefix": True,
        "fanout_patterns": True,
    },
    result_backend_transport_options={
        "fanout_prefix": True,
        "fanout_patterns": True,
    },
    beat_schedule={
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
        "notion.backup_pull_cohorts": {
            "task": "notion.backup_pull_cohorts",
            "schedule": crontab(minute="*/5"),
        },
        # Meetings: auto-start confirmed meetings whose scheduled_at has passed
        "meeting.auto_start_due_calls": {
            "task": "meeting.auto_start_due_calls",
            "schedule": crontab(minute="*"),
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
        # Weekly mentor per-student survey (Mon 12:00 UTC = 15:00 MSK)
        "surveys.send_weekly_mentor_per_student": {
            "task": "surveys.send_weekly_mentor_per_student",
            "schedule": crontab(minute=0, hour=12, day_of_week=1),
        },
        # Biweekly search mentor per-student survey (Mon 12:00 UTC = 15:00 MSK)
        # Task itself checks even ISO week
        "surveys.send_search_biweekly_mentor": {
            "task": "surveys.send_search_biweekly_mentor",
            "schedule": crontab(minute=0, hour=12, day_of_week=1),
        },
        # Biweekly probation mentee survey (Mon 12:00 UTC = 15:00 MSK)
        # Task itself checks even ISO week
        "surveys.send_probation_biweekly_mentee": {
            "task": "surveys.send_probation_biweekly_mentee",
            "schedule": crontab(minute=0, hour=12, day_of_week=1),
        },
        # Biweekly probation mentor per-student survey (Mon 12:00 UTC = 15:00 MSK)
        # Task itself checks even ISO week
        "surveys.send_probation_biweekly_mentor": {
            "task": "surveys.send_probation_biweekly_mentor",
            "schedule": crontab(minute=0, hour=12, day_of_week=1),
        },
        # Survey alerts: send notifications for low scores / trends / mismatches
        "surveys.process_alerts": {
            "task": "surveys.process_alerts",
            "schedule": crontab(minute="*/5"),
        },
        # Survey escalation: remind / notify mentor / escalate unanswered surveys (every 2 min)
        "surveys.check_escalations": {
            "task": "surveys.check_escalations",
            "schedule": crontab(minute="*/2"),
        },
        # CalDAV sync: periodic backfill of dirty meetings for mentor calendars
        "caldav.sync_dirty_meetings": {
            "task": "caldav.sync_dirty_meetings",
            "schedule": settings.CALDAV_SYNC_INTERVAL_SECONDS,
        },
        # CalDAV pull: detect changes in mentor calendars and apply to PG
        "caldav.pull_all_accounts": {
            "task": "caldav.pull_all_accounts",
            "schedule": settings.CALDAV_PULL_INTERVAL_SECONDS,
        },
    },
)

CELERY_TASK_DURATION = Histogram(
    "celery_task_duration_seconds",
    "Celery task duration",
    ["task_name"],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120],
)
CELERY_TASK_TOTAL = Counter(
    "celery_task_total",
    "Celery task executions",
    ["task_name", "status"],
)


@task_prerun.connect
def _on_task_prerun(task, **kwargs):
    task._prom_start = time.monotonic()


@task_postrun.connect
def _on_task_postrun(task, state, **kwargs):
    duration = time.monotonic() - getattr(task, "_prom_start", time.monotonic())
    status = "success" if state == "SUCCESS" else "failure"
    CELERY_TASK_DURATION.labels(task_name=task.name).observe(duration)
    CELERY_TASK_TOTAL.labels(task_name=task.name, status=status).inc()


# NOTE: worker/beat entrypoints are in src/scripts. Make sure BOT_TOKEN/REDIS envs are set.

# Ensure the worker_shutdown handler in src.tasks._db is registered even when
# this module is imported without the task modules being touched first.
import src.tasks._db  # noqa: E402, F401
