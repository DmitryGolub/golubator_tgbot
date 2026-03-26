from __future__ import annotations

import logging
from datetime import datetime

from src.services.notion.client import NotionClient
from src.services.notion.dto import EventData, join_rich_text

logger = logging.getLogger(__name__)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


class NotionEventRepo:
    """Read/write access to the Созвоны менторов database in Notion."""

    def __init__(self, client: NotionClient):
        self._client = client

    @property
    def data_source_id(self) -> str | None:
        return self._client.data_source_id

    def _parse_page(self, page: dict) -> EventData:
        props = page.get("properties", {})

        topic_title = props.get("Тема", {}).get("title") or []
        topic = join_rich_text(topic_title).strip() or None

        date_data = props.get("Дата", {}).get("date")
        date = date_data.get("start") if date_data else None

        type_sel = props.get("Тип", {}).get("select")
        event_type = type_sel.get("name") if type_sel else None

        status_data = props.get("Статус", {}).get("status")
        status = status_data.get("name") if status_data else None

        mentee_rt = props.get("ТГ тег менти", {}).get("rich_text") or []
        mentee_tg_tag = join_rich_text(mentee_rt).strip() or None

        mentor_persons = props.get("Ментор", {}).get("person") or []
        mentor_name = mentor_persons[0].get("name") if mentor_persons else None

        link = props.get("Ссылка", {}).get("url")
        recording = props.get("Запись", {}).get("url")

        summary_rt = props.get("Итоги", {}).get("rich_text") or []
        summary = join_rich_text(summary_rt) or None

        actions_rt = props.get("Action items", {}).get("rich_text") or []
        action_items = join_rich_text(actions_rt) or None

        project_rt = props.get("Проект", {}).get("rich_text") or []
        project = join_rich_text(project_rt) or None

        return EventData(
            page_id=page["id"],
            topic=topic,
            date=date,
            event_type=event_type,
            status=status,
            mentee_tg_tag=mentee_tg_tag,
            mentor_name=mentor_name,
            link=link,
            recording=recording,
            summary=summary,
            action_items=action_items,
            project=project,
            last_edited_time=_parse_iso(page.get("last_edited_time")),
        )

    async def get_all(self, since: datetime | None = None) -> list[EventData]:
        filter_obj = None
        if since:
            filter_obj = {
                "property": "Дата",
                "date": {"on_or_after": since.isoformat()},
            }

        if filter_obj:
            pages: list[dict] = []
            cursor: str | None = None
            while True:
                resp = await self._client.query_pages(
                    filter=filter_obj, page_size=100, start_cursor=cursor
                )
                pages.extend(resp.get("results", []))
                if not resp.get("has_more"):
                    break
                cursor = resp.get("next_cursor")
        else:
            pages = await self._client.get_all_pages()

        return [self._parse_page(p) for p in pages]

    async def get_page(self, page_id: str) -> EventData | None:
        page = await self._client.get_page(page_id)
        return self._parse_page(page) if page else None

    async def create_event(
        self,
        *,
        topic: str,
        date: str | None = None,
        event_type: str | None = None,
        status: str = "Запланирован",
        mentee_tg_tag: str | None = None,
        link: str | None = None,
    ) -> str | None:
        properties: dict = {
            "Тема": {"title": [{"text": {"content": topic}}]},
            "Статус": {"status": {"name": status}},
        }
        if date:
            properties["Дата"] = {"date": {"start": date}}
        if event_type:
            properties["Тип"] = {"select": {"name": event_type}}
        if mentee_tg_tag:
            properties["ТГ тег менти"] = {
                "rich_text": [{"text": {"content": mentee_tg_tag}}]
            }
        if link:
            properties["Ссылка"] = {"url": link}

        page = await self._client.create_page(properties)
        return page["id"] if page else None

    async def update_status(self, page_id: str, status: str) -> bool:
        result = await self._client.update_page(
            page_id, {"Статус": {"status": {"name": status}}}
        )
        return result is not None

    async def update_properties(self, page_id: str, props: dict) -> bool:
        result = await self._client.update_page(page_id, props)
        return result is not None
