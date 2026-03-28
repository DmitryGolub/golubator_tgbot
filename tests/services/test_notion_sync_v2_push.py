from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.notion_sync_v2 import NotionSyncServiceV2


def _mentee(
    *,
    id: int = 1,
    doc_name: str = "Test Mentee",
    notion_page_id: str = "page-1",
    mentor_id: int | None = 200,
    mentor: SimpleNamespace | None = None,
    updated_at="2026-01-01",
    synced_at=None,
):
    if mentor is None and mentor_id is not None:
        mentor = SimpleNamespace(telegram_id=mentor_id, email="mentor@example.com")
    return SimpleNamespace(
        id=id,
        doc_name=doc_name,
        notion_page_id=notion_page_id,
        mentor_id=mentor_id,
        mentor=mentor,
        updated_at=updated_at,
        synced_at=synced_at,
    )


def _mock_session(mentees, status=None):
    """Create a mock session with execute side effects for push_mentees."""
    session = AsyncMock()

    # result.scalars().all() — sync chain, use MagicMock
    mentee_result = MagicMock()
    mentee_result.scalars.return_value.all.return_value = mentees

    # result.scalar_one_or_none() — sync, use MagicMock
    status_result = MagicMock()
    status_result.scalar_one_or_none.return_value = status

    session.execute = AsyncMock(side_effect=[mentee_result, status_result, AsyncMock()])
    session.commit = AsyncMock()
    return session


def _mock_factory(session):
    engine = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return engine, lambda: ctx


class TestPushMentees:
    @patch("src.services.notion_sync_v2._make_session_factory")
    async def test_mentor_included_in_props(self, mock_factory):
        mentee = _mentee()
        session = _mock_session([mentee])
        mock_factory.return_value = _mock_factory(session)

        mentee_repo = AsyncMock()
        svc = NotionSyncServiceV2(
            mentor_repo=None, mentee_repo=mentee_repo, event_repo=None
        )
        svc._resolve_mentor_notion_ids = AsyncMock(return_value=["notion-uid-123"])

        pushed = await svc.push_mentees()

        assert pushed == 1
        mentee_repo.update_properties.assert_called_once()
        props = mentee_repo.update_properties.call_args[0][1]
        assert props["Mentor"] == {
            "people": [{"object": "user", "id": "notion-uid-123"}]
        }

    @patch("src.services.notion_sync_v2._make_session_factory")
    async def test_mentor_cleared_when_none(self, mock_factory):
        mentee = _mentee(mentor_id=None, mentor=None)
        session = _mock_session([mentee])
        mock_factory.return_value = _mock_factory(session)

        mentee_repo = AsyncMock()
        svc = NotionSyncServiceV2(
            mentor_repo=None, mentee_repo=mentee_repo, event_repo=None
        )
        svc._resolve_mentor_notion_ids = AsyncMock(return_value=None)

        pushed = await svc.push_mentees()

        assert pushed == 1
        props = mentee_repo.update_properties.call_args[0][1]
        assert props["Mentor"] == {"people": []}

    @patch("src.services.notion_sync_v2._make_session_factory")
    async def test_mentor_not_touched_when_unresolvable(self, mock_factory):
        mentee = _mentee(mentor_id=200)
        session = _mock_session([mentee])
        mock_factory.return_value = _mock_factory(session)

        mentee_repo = AsyncMock()
        svc = NotionSyncServiceV2(
            mentor_repo=None, mentee_repo=mentee_repo, event_repo=None
        )
        svc._resolve_mentor_notion_ids = AsyncMock(return_value=None)

        await svc.push_mentees()

        props = mentee_repo.update_properties.call_args[0][1]
        assert "Mentor" not in props


class TestResolveMentorNotionIds:
    async def test_uses_mentee_repo_client_when_no_event_repo(self):
        mock_client = AsyncMock()
        mock_client.get_users = AsyncMock(
            return_value={"mentor@example.com": "notion-uid-456"}
        )
        mentee_repo = SimpleNamespace(_client=mock_client)

        svc = NotionSyncServiceV2(
            mentor_repo=None, mentee_repo=mentee_repo, event_repo=None
        )

        mock_session = AsyncMock()
        email_result = MagicMock()
        email_result.scalar_one_or_none.return_value = "mentor@example.com"
        mock_session.execute = AsyncMock(return_value=email_result)

        result = await svc._resolve_mentor_notion_ids(mock_session, 200)

        assert result == ["notion-uid-456"]
        mock_client.get_users.assert_called_once()

    async def test_returns_none_when_no_telegram_id(self):
        svc = NotionSyncServiceV2(mentor_repo=None, mentee_repo=None, event_repo=None)
        result = await svc._resolve_mentor_notion_ids(AsyncMock(), None)
        assert result is None

    async def test_returns_none_when_no_client_available(self):
        svc = NotionSyncServiceV2(mentor_repo=None, mentee_repo=None, event_repo=None)
        result = await svc._resolve_mentor_notion_ids(AsyncMock(), 200)
        assert result is None
