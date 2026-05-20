"""Unit tests for `src.utils.meeting_confirm.is_confirmable`."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from src.utils.meeting_confirm import is_confirmable


def _user(telegram_id, registered=True):
    return SimpleNamespace(
        telegram_id=telegram_id,
        registered_at=datetime(2025, 1, 1, tzinfo=timezone.utc) if registered else None,
    )


def test_real_registered_user_is_confirmable():
    assert is_confirmable(_user(100)) is True


def test_placeholder_is_not_confirmable():
    assert is_confirmable(_user(-1)) is False


def test_unregistered_user_is_not_confirmable():
    assert is_confirmable(_user(100, registered=False)) is False


def test_missing_telegram_id_is_not_confirmable():
    assert is_confirmable(SimpleNamespace(registered_at=None)) is False


def test_zero_telegram_id_is_not_confirmable():
    assert is_confirmable(_user(0)) is False
