"""Reusable formatter for meeting-proposal Telegram messages.

Used by bot handlers (when a participant proposes a meeting) and by the
CalDAV reverse-sync service (when a calendar move triggers a re-confirmation).
"""

from __future__ import annotations

from datetime import datetime

from src.utils.escape import e
from src.utils.tz import MSK


def format_when(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    try:
        return dt.astimezone(MSK).strftime("%d.%m.%Y %H:%M MSK")
    except Exception:
        return dt.isoformat()


def format_proposal_text(meeting, proposer_name: str) -> str:
    link_str = e(meeting.meeting_link) if meeting.meeting_link else "—"
    desc_str = e(meeting.description) if meeting.description else "—"
    proposer_str = e(proposer_name)

    if meeting.original_scheduled_at is not None:
        return (
            f"🔄 <b>Перенос созвона</b>\n\n"
            f"От: <b>{proposer_str}</b>\n"
            f"Было: {format_when(meeting.original_scheduled_at)}\n"
            f"Станет: {format_when(meeting.scheduled_at)}\n"
            f"Ссылка: {link_str}\n"
            f"Описание: {desc_str}"
        )

    return (
        f"📅 <b>Предложение о созвоне</b>\n\n"
        f"От: <b>{proposer_str}</b>\n"
        f"Когда: {format_when(meeting.scheduled_at)}\n"
        f"Ссылка: {link_str}\n"
        f"Описание: {desc_str}"
    )
