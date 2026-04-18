"""Reusable formatter for meeting-proposal Telegram messages.

Used by bot handlers (when a participant proposes a meeting) and by the
CalDAV reverse-sync service (when a calendar move triggers a re-confirmation).
"""

from __future__ import annotations

from src.utils.escape import e
from src.utils.tz import MSK


def format_proposal_text(meeting, proposer_name: str) -> str:
    date_str = "—"
    if meeting.scheduled_at:
        try:
            date_str = meeting.scheduled_at.astimezone(MSK).strftime(
                "%d.%m.%Y %H:%M MSK"
            )
        except Exception:
            date_str = meeting.scheduled_at.isoformat()
    link_str = e(meeting.meeting_link) if meeting.meeting_link else "—"
    desc_str = e(meeting.description) if meeting.description else "—"
    return (
        f"📅 <b>Предложение о созвоне</b>\n\n"
        f"От: <b>{e(proposer_name)}</b>\n"
        f"Когда: {date_str}\n"
        f"Ссылка: {link_str}\n"
        f"Описание: {desc_str}"
    )
