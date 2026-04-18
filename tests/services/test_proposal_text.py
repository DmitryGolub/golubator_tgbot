"""Unit tests for format_proposal_text — covers new-proposal vs reschedule."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from src.services.meeting.proposal_text import format_proposal_text


def _meeting(scheduled_at, original_scheduled_at=None, link=None, description=None):
    return SimpleNamespace(
        scheduled_at=scheduled_at,
        original_scheduled_at=original_scheduled_at,
        meeting_link=link,
        description=description,
    )


def test_format_proposal_text_new_meeting():
    meeting = _meeting(
        scheduled_at=datetime(2026, 5, 10, 9, 0, tzinfo=timezone.utc),
        link="https://example.com/meet",
        description="kick-off",
    )

    text = format_proposal_text(meeting, "Алиса")

    assert "📅 <b>Предложение о созвоне</b>" in text
    assert "🔄" not in text
    assert "От: <b>Алиса</b>" in text
    assert "Когда: 10.05.2026 12:00 MSK" in text
    assert "Было:" not in text
    assert "Станет:" not in text
    assert "https://example.com/meet" in text
    assert "kick-off" in text


def test_format_proposal_text_reschedule():
    meeting = _meeting(
        scheduled_at=datetime(2026, 5, 10, 15, 0, tzinfo=timezone.utc),
        original_scheduled_at=datetime(2026, 5, 10, 9, 0, tzinfo=timezone.utc),
    )

    text = format_proposal_text(meeting, "Боб")

    assert "🔄 <b>Перенос созвона</b>" in text
    assert "📅 <b>Предложение о созвоне</b>" not in text
    assert "От: <b>Боб</b>" in text
    assert "Было: 10.05.2026 12:00 MSK" in text
    assert "Станет: 10.05.2026 18:00 MSK" in text
    assert "Ссылка: —" in text
    assert "Описание: —" in text


def test_format_proposal_text_escapes_proposer_name():
    meeting = _meeting(
        scheduled_at=datetime(2026, 5, 10, 9, 0, tzinfo=timezone.utc),
    )

    text = format_proposal_text(meeting, "<script>")

    assert "<script>" not in text
    assert "&lt;script&gt;" in text
