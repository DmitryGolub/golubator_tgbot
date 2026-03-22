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
    except Exception:
        logger.exception("Health check: database unreachable")
        errors.append("database")

    try:
        redis = get_redis()
        await redis.ping()
        await redis.aclose()
    except Exception:
        logger.exception("Health check: redis unreachable")
        errors.append("redis")

    if errors:
        return web.json_response(
            {"status": "unhealthy", "errors": errors}, status=503
        )
    return web.json_response({"status": "healthy"})


async def start_health_server() -> web.AppRunner:
    from src.api.notion_webhook import setup_webhook_routes

    app = web.Application()
    app.router.add_get("/health", _health_handler)
    setup_webhook_routes(app)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    logger.info("Health check server started on port %d", HEALTH_PORT)
    return runner
