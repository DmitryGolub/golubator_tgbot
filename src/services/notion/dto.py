from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


def join_rich_text(blocks: list[dict]) -> str:
    """Join all rich_text/title blocks into a single plain-text string."""
    return "".join(item.get("plain_text", "") for item in blocks)


def parse_iso(value: str | None) -> datetime | None:
    """Parse ISO datetime string, handling Notion's 'Z' suffix."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


@dataclass
class MentorData:
    page_id: str
    name: str | None = None
    telegram_id: int | None = None
    role: str | None = None
    email: str | None = None
    about: str | None = None
    membership_type: str | None = None
    channel_id: int | None = None
    last_edited_time: datetime | None = None


@dataclass
class MenteeData:
    page_id: str
    doc_name: str | None = None
    telegram_id: int | None = None
    status: str | None = None
    categories: list[str] = field(default_factory=list)
    mentor_name: str | None = None
    mentor_email: str | None = None
    contract: bool = False
    intern: str | None = None
    contract_version: float | None = None
    contract_expires: str | None = None
    student_score: float | None = None
    last_edited_time: datetime | None = None
    created_time: datetime | None = None


@dataclass
class EventData:
    page_id: str
    topic: str | None = None
    date: str | None = None
    event_type: str | None = None
    status: str | None = None
    mentee_tg_tag: str | None = None
    mentor_name: str | None = None
    link: str | None = None
    recording: str | None = None
    summary: str | None = None
    action_items: str | None = None
    project: str | None = None
    last_edited_time: datetime | None = None
