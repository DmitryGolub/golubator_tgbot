from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.notion_sync_v2 import _ensure_user_exists


def _make_session(ph_user=None):
    """Create a mock async session that returns ph_user on SELECT User."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = ph_user
    session.execute = AsyncMock(return_value=result)
    return session


@patch("src.services.notion_sync_v2.select")
async def test_placeholder_name_updated_on_resync(mock_select):
    """Existing placeholder with stale name gets updated from Notion."""
    ph_user = SimpleNamespace(name="Anonymous", telegram_id=-2)
    session = _make_session(ph_user)

    tid = await _ensure_user_exists(
        session,
        telegram_id=None,
        name="@Octa View",
        role_name="mentor",
        current_placeholder_id=-2,
    )

    assert tid == -2
    assert ph_user.name == "Octa View"


@patch("src.services.notion_sync_v2.select")
async def test_placeholder_name_not_downgraded_to_none(mock_select):
    """Sync with name=None must not overwrite existing placeholder name."""
    ph_user = SimpleNamespace(name="Octa View", telegram_id=-2)
    session = _make_session(ph_user)

    tid = await _ensure_user_exists(
        session,
        telegram_id=None,
        name=None,
        role_name="mentor",
        current_placeholder_id=-2,
    )

    assert tid == -2
    assert ph_user.name == "Octa View"
    # No SELECT should be issued when clean is None
    session.execute.assert_not_awaited()


@patch("src.services.notion_sync_v2.select")
async def test_placeholder_name_unchanged_when_same(mock_select):
    """When Notion name matches DB — no update needed."""
    ph_user = SimpleNamespace(name="Octa View", telegram_id=-2)
    session = _make_session(ph_user)

    tid = await _ensure_user_exists(
        session,
        telegram_id=None,
        name="@Octa View",
        role_name="mentor",
        current_placeholder_id=-2,
    )

    assert tid == -2
    # Name stays the same object (not reassigned)
    assert ph_user.name == "Octa View"
