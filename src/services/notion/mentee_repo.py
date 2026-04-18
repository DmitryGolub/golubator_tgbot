from __future__ import annotations

import logging
from datetime import datetime

from src.services.notion.client import NotionClient
from src.services.notion.dto import MenteeData, join_rich_text, parse_iso as _parse_iso

logger = logging.getLogger(__name__)


class NotionMenteeRepo:
    """Read/write access to the Голубиная база in Notion."""

    def __init__(self, client: NotionClient):
        self._client = client

    @property
    def data_source_id(self) -> str | None:
        return self._client.data_source_id

    def _parse_page(self, page: dict) -> MenteeData:
        props = page.get("properties", {})

        doc_title = props.get("Doc name", {}).get("title") or []
        doc_name = join_rich_text(doc_title).strip() or None

        tg_id_raw = props.get("Telegram ID", {}).get("number")
        telegram_id = int(tg_id_raw) if tg_id_raw is not None else None

        status_data = props.get("Status", {}).get("status")
        status = status_data.get("name") if status_data else None

        category_items = props.get("Category", {}).get("multi_select") or []
        categories = [c["name"] for c in category_items if c.get("name")]

        mentor_prop = props.get("Mentor", {})
        mentor_persons = mentor_prop.get("people") or mentor_prop.get("person") or []
        if not isinstance(mentor_persons, list):
            mentor_persons = [mentor_persons]
        logger.debug("Mentor raw property for page %s: %s", page.get("id"), mentor_prop)
        mentor_name = mentor_persons[0].get("name") if mentor_persons else None
        mentor_person = mentor_persons[0].get("person", {}) if mentor_persons else {}
        mentor_email = mentor_person.get("email") if mentor_person else None

        contract_data = props.get("Договор", {})
        contract = contract_data.get("checkbox", False)

        intern_sel = props.get("Стажор", {}).get("select")
        intern = intern_sel.get("name") if intern_sel else None

        contract_ver = props.get("Версия договора с ментором", {}).get("number")

        expires_date = props.get("Истекает договор", {}).get("date")
        contract_expires = expires_date.get("start") if expires_date else None

        score = props.get("Оценка ученика (0-10)", {}).get("number")

        return MenteeData(
            page_id=page["id"],
            doc_name=doc_name,
            telegram_id=telegram_id,
            status=status,
            categories=categories,
            mentor_name=mentor_name,
            mentor_email=mentor_email,
            contract=contract,
            intern=intern,
            contract_version=contract_ver,
            contract_expires=contract_expires,
            student_score=score,
            last_edited_time=_parse_iso(page.get("last_edited_time")),
            created_time=_parse_iso(page.get("created_time")),
        )

    async def find_by_telegram_id(self, tg_id: int) -> MenteeData | None:
        resp = await self._client.query_pages(
            filter={"property": "Telegram ID", "number": {"equals": tg_id}},
            page_size=1,
        )
        results = resp.get("results", [])
        return self._parse_page(results[0]) if results else None

    async def find_by_username(self, username: str) -> MenteeData | None:
        clean = username.lstrip("@")
        for query_val in [f"@{clean}", clean]:
            resp = await self._client.query_pages(
                filter={"property": "Doc name", "title": {"equals": query_val}},
                page_size=1,
            )
            results = resp.get("results", [])
            if results:
                return self._parse_page(results[0])
        return None

    async def get_all(self) -> list[MenteeData]:
        pages = await self._client.get_all_pages()
        return [self._parse_page(p) for p in pages]

    async def get_changed_since(self, since: datetime) -> list[MenteeData]:
        """Return mentees edited on-or-after `since` (Notion system timestamp)."""
        filter_obj = {
            "timestamp": "last_edited_time",
            "last_edited_time": {"on_or_after": since.isoformat()},
        }
        pages = await self._client.get_all_pages(filter=filter_obj)
        return [self._parse_page(p) for p in pages]

    async def get_page(self, page_id: str) -> MenteeData | None:
        page = await self._client.get_page(page_id)
        return self._parse_page(page) if page else None

    _STRIP_KEYS = frozenset(
        {
            "id",
            "created_time",
            "last_edited_time",
            "created_by",
            "last_edited_by",
            "has_children",
            "archived",
            "in_trash",
            "parent",
            "object",
            "request_id",
        }
    )

    @staticmethod
    def _clean_block(block: dict) -> dict:
        block_type = block["type"]
        return {"type": block_type, block_type: block[block_type]}

    async def _fetch_template_children(self) -> list[dict]:
        from src.core.config import settings

        template_id = settings.NOTION_MENTEE_TEMPLATE_PAGE_ID
        if not template_id:
            return []
        try:
            blocks = await self._client.get_block_children(template_id)
            return [self._clean_block(b) for b in blocks]
        except Exception:
            logger.exception("Failed to fetch template blocks from %s", template_id)
            return []

    async def create_page(self, username: str, telegram_id: int) -> str | None:
        clean = username.lstrip("@")
        children = await self._fetch_template_children()
        page = await self._client.create_page(
            {
                "Doc name": {"title": [{"text": {"content": f"@{clean}"}}]},
                "Telegram ID": {"number": telegram_id},
                "Status": {"status": {"name": "Lead"}},
            },
            children=children,
        )
        return page["id"] if page else None

    async def update_properties(self, page_id: str, props: dict) -> bool:
        result = await self._client.update_page(page_id, props)
        return result is not None

    async def update_status(self, page_id: str, status: str) -> bool:
        return await self.update_properties(
            page_id, {"Status": {"status": {"name": status}}}
        )

    async def update_telegram_id(self, page_id: str, tg_id: int) -> bool:
        return await self.update_properties(page_id, {"Telegram ID": {"number": tg_id}})
