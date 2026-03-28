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


async def start_health_server() -> web.AppRunner:
    from src.api.notion_webhook import setup_webhook_routes

    app = web.Application(client_max_size=1024 * 1024)  # 1 MB limit
    app.router.add_get("/health", _health_handler)
    setup_webhook_routes(app)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    logger.info("Health check server started on port %d", HEALTH_PORT)
    return runner
