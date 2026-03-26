from __future__ import annotations

import logging
from datetime import datetime

from src.services.notion.client import NotionClient
from src.services.notion.dto import MenteeData, join_rich_text

logger = logging.getLogger(__name__)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


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

        tags_items = props.get("Tags", {}).get("multi_select") or []
        tags = [t["name"] for t in tags_items if t.get("name")]

        mentor_persons = props.get("Mentor", {}).get("person") or []
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
            tags=tags,
            mentor_name=mentor_name,
            mentor_email=mentor_email,
            contract=contract,
            intern=intern,
            contract_version=contract_ver,
            contract_expires=contract_expires,
            student_score=score,
            last_edited_time=_parse_iso(page.get("last_edited_time")),
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

    async def get_page(self, page_id: str) -> MenteeData | None:
        page = await self._client.get_page(page_id)
        return self._parse_page(page) if page else None

    async def create_page(self, username: str, telegram_id: int) -> str | None:
        clean = username.lstrip("@")
        page = await self._client.create_page(
            {
                "Doc name": {"title": [{"text": {"content": f"@{clean}"}}]},
                "Telegram ID": {"number": telegram_id},
            }
        )
        return page["id"] if page else None

    async def update_properties(self, page_id: str, props: dict) -> bool:
        result = await self._client.update_page(page_id, props)
        return result is not None

    async def update_status(self, page_id: str, status: str) -> bool:
        return await self.update_properties(
            page_id, {"Status": {"status": {"name": status}}}
        )

    async def update_tags(self, page_id: str, tags: list[str]) -> bool:
        return await self.update_properties(
            page_id,
            {"Tags": {"multi_select": [{"name": t} for t in tags]}},
        )

    async def update_telegram_id(self, page_id: str, tg_id: int) -> bool:
        return await self.update_properties(page_id, {"Telegram ID": {"number": tg_id}})

    async def create_tags_property(self) -> bool:
        """Create the 'Tags' multi_select property in the Notion database."""
        return await self._client.update_schema(
            {"Tags": {"multi_select": {"options": []}}}
        )
