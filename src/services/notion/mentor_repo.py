from __future__ import annotations

import logging

from src.services.notion.client import NotionClient
from src.services.notion.dto import MentorData, join_rich_text, parse_iso as _parse_iso

logger = logging.getLogger(__name__)


class NotionMentorRepo:
    """Read/write access to the Менторская база in Notion."""

    def __init__(self, client: NotionClient):
        self._client = client

    @property
    def data_source_id(self) -> str | None:
        return self._client.data_source_id

    def _parse_page(self, page: dict) -> MentorData:
        props = page.get("properties", {})

        name_title = props.get("Name", {}).get("title") or []
        name = join_rich_text(name_title).strip() or None
        logger.debug(
            "mentor _parse_page: page_id=%s, raw Name=%r, parsed=%r",
            page.get("id"),
            name_title,
            name,
        )

        tg_id_raw = props.get("Telegram ID", {}).get("number")
        telegram_id = int(tg_id_raw) if tg_id_raw is not None else None

        role_sel = props.get("Role", {}).get("select")
        role = role_sel.get("name") if role_sel else None

        email = props.get("Email", {}).get("email")

        about_rt = props.get("About", {}).get("rich_text") or []
        about = join_rich_text(about_rt) or None

        membership_sel = props.get("Membership Type", {}).get("select")
        membership_type = membership_sel.get("name") if membership_sel else None

        channel_id_raw = props.get("Channel ID", {}).get("number")
        channel_id = int(channel_id_raw) if channel_id_raw is not None else None

        return MentorData(
            page_id=page["id"],
            name=name,
            telegram_id=telegram_id,
            role=role,
            email=email,
            about=about,
            membership_type=membership_type,
            channel_id=channel_id,
            last_edited_time=_parse_iso(page.get("last_edited_time")),
        )

    async def find_by_telegram_id(self, tg_id: int) -> MentorData | None:
        resp = await self._client.query_pages(
            filter={"property": "Telegram ID", "number": {"equals": tg_id}},
            page_size=1,
        )
        results = resp.get("results", [])
        return self._parse_page(results[0]) if results else None

    async def get_all(self) -> list[MentorData]:
        pages = await self._client.get_all_pages()
        return [self._parse_page(p) for p in pages]

    async def get_page(self, page_id: str) -> MentorData | None:
        page = await self._client.get_page(page_id)
        return self._parse_page(page) if page else None

    async def create_page(
        self, name: str, telegram_id: int, role: str = "mentor"
    ) -> str | None:
        page = await self._client.create_page(
            {
                "Name": {"title": [{"text": {"content": name}}]},
                "Telegram ID": {"number": telegram_id},
                "Role": {"select": {"name": role}},
            }
        )
        return page["id"] if page else None

    async def update_properties(self, page_id: str, props: dict) -> bool:
        result = await self._client.update_page(page_id, props)
        return result is not None

    async def update_role(self, page_id: str, role: str) -> bool:
        return await self.update_properties(
            page_id, {"Role": {"select": {"name": role}}}
        )

    async def update_telegram_id(self, page_id: str, tg_id: int) -> bool:
        return await self.update_properties(page_id, {"Telegram ID": {"number": tg_id}})
