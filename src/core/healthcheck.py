import logging

from aiohttp import web
from sqlalchemy import text

from src.core.database import async_session_maker
from src.core.redis import get_redis

logger = logging.getLogger(__name__)

HEALTH_PORT = 8080


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


async def _trigger_task_handler(request: web.Request) -> web.Response:
    task_name = request.match_info["task_name"]
    from src.celery_app import celery_app

    celery_app.send_task(task_name)
    logger.info("Test trigger: queued task %s", task_name)
    return web.json_response({"status": "queued", "task": task_name})


async def start_health_server() -> web.AppRunner:
    from src.api.notion_webhook import setup_webhook_routes
    from src.core.config import settings

    app = web.Application(client_max_size=1024 * 1024)  # 1 MB limit
    app.router.add_get("/health", _health_handler)
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
