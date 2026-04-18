import logging

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from src.core.database import async_session_maker
from src.core.redis import get_redis

logger = logging.getLogger(__name__)

HEALTH_PORT = 8080


async def _metrics_handler(_request: web.Request) -> web.Response:
    body = generate_latest()
    return web.Response(body=body, content_type=CONTENT_TYPE_LATEST.split(";")[0])


async def _health_handler(_request: web.Request) -> web.Response:
    errors: list[str] = []

    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("Health check: database unreachable: %s", exc)
        errors.append("database")

    try:
        redis = get_redis()
        try:
            await redis.ping()
        finally:
            await redis.aclose()
    except Exception as exc:
        logger.warning("Health check: redis unreachable: %s", exc)
        errors.append("redis")

    if errors:
        return web.json_response({"status": "unhealthy", "errors": errors}, status=503)
    return web.json_response({"status": "healthy"})


_ALLOWED_TEST_TASKS: frozenset[str] = frozenset(
    {
        "triggers.execute_action",
        "triggers.tick_periodic",
        "triggers.process_pending",
        "notion.push_changes",
        "notion.backup_pull_users",
        "notion.backup_pull_events",
        "notion.backup_pull_cohorts",
        "surveys.send_weekly_mentor_per_student",
        "surveys.send_search_biweekly_mentor",
        "surveys.send_probation_biweekly_mentee",
        "surveys.send_probation_biweekly_mentor",
        "surveys.process_alerts",
        "surveys.check_escalations",
        "meeting.notify_created",
        "meeting.notify_reminder",
        "meeting.archive_notion_page",
    }
)


async def _trigger_task_handler(request: web.Request) -> web.Response:
    task_name = request.match_info["task_name"]

    if task_name not in _ALLOWED_TEST_TASKS:
        return web.json_response(
            {"status": "rejected", "error": "unknown task"}, status=403
        )

    from src.celery_app import celery_app

    celery_app.send_task(task_name)
    logger.info("Test trigger: queued task %s", task_name)
    return web.json_response({"status": "queued", "task": task_name})


async def start_health_server() -> web.AppRunner:
    from src.api.notion_webhook import setup_webhook_routes
    from src.core.config import settings

    app = web.Application(client_max_size=1024 * 1024)  # 1 MB limit
    app.router.add_get("/health", _health_handler)
    app.router.add_get("/metrics", _metrics_handler)
    setup_webhook_routes(app)
    if settings.TEST_MODE:
        app.router.add_post("/test/trigger/{task_name}", _trigger_task_handler)
        logger.info("TEST_MODE: /test/trigger/{task_name} endpoint enabled")
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    logger.info("Health check server started on port %d", HEALTH_PORT)
    return runner
