from __future__ import annotations

import hmac
import json
import logging

from aiohttp import web

logger = logging.getLogger(__name__)


async def _handle_automation(request: web.Request, source_db: str) -> web.Response:
    """Handle Notion Automation webhook (Send webhook action).

    Payload contains page properties directly (not sparse like API webhooks).
    """
    from src.core.config import settings

    secret = settings.NOTION_WEBHOOK_SECRET
    if not secret or not hmac.compare_digest(
        request.headers.get("X-Notion-Secret", ""), secret
    ):
        return web.json_response({"error": "unauthorized"}, status=401)

    body = await request.read()

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid json"}, status=400)

    logger.info("Notion automation webhook: source=%s", source_db)
    logger.debug("Payload: %s", json.dumps(payload, ensure_ascii=False)[:500])

    from src.services.notion_sync_v2 import get_sync_service

    sync = get_sync_service()
    if not sync:
        return web.json_response({"status": "sync not configured"})

    try:
        if source_db in ("mentor", "mentee"):
            await sync.handle_automation_user(payload, source_db)
        elif source_db == "event":
            await sync.handle_automation_event(payload)
        elif source_db == "cohort":
            await sync.handle_automation_cohort(payload)
    except Exception:
        logger.exception("Error handling automation webhook (source=%s)", source_db)
        return web.json_response({"error": "processing failed"}, status=500)

    return web.json_response({"status": "ok"})


async def webhook_mentors(request: web.Request) -> web.Response:
    return await _handle_automation(request, "mentor")


async def webhook_mentees(request: web.Request) -> web.Response:
    return await _handle_automation(request, "mentee")


async def webhook_events(request: web.Request) -> web.Response:
    return await _handle_automation(request, "event")


async def webhook_cohorts(request: web.Request) -> web.Response:
    return await _handle_automation(request, "cohort")


def setup_webhook_routes(app: web.Application) -> None:
    app.router.add_post("/api/webhooks/notion/mentors", webhook_mentors)
    app.router.add_post("/api/webhooks/notion/mentees", webhook_mentees)
    app.router.add_post("/api/webhooks/notion/events", webhook_events)
    app.router.add_post("/api/webhooks/notion/cohorts", webhook_cohorts)
