from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.models.trigger import RecipientType
from src.services.events.recipient_resolver import RecipientResolver


def _rule(recipient_type, config=None):
    return SimpleNamespace(
        id=1,
        recipient_type=recipient_type,
        recipient_config=config,
    )


class TestEventBasedRecipients:
    async def test_event_student_from_context(self):
        result = await RecipientResolver.resolve(
            _rule(RecipientType.event_student), {"student_id": 200}
        )
        assert result == [200]

    async def test_event_student_missing(self):
        result = await RecipientResolver.resolve(_rule(RecipientType.event_student), {})
        assert result == []

    async def test_event_mentor_from_context(self):
        result = await RecipientResolver.resolve(
            _rule(RecipientType.event_mentor), {"mentor_id": 100}
        )
        assert result == [100]

    async def test_event_mentor_missing(self):
        result = await RecipientResolver.resolve(_rule(RecipientType.event_mentor), {})
        assert result == []


class TestSpecificUsers:
    async def test_returns_user_ids(self):
        result = await RecipientResolver.resolve(
            _rule(RecipientType.specific_users, {"user_ids": [100, 200, 300]}),
            {},
        )
        assert result == [100, 200, 300]

    async def test_empty_list(self):
        result = await RecipientResolver.resolve(
            _rule(RecipientType.specific_users, {"user_ids": []}),
            {},
        )
        assert result == []


@patch("src.services.events.recipient_resolver.UserDAO")
class TestByRole:
    async def test_fetches_users(self, mock_dao):
        mock_dao.get_all = AsyncMock(
            return_value=[
                SimpleNamespace(telegram_id=100),
                SimpleNamespace(telegram_id=200),
            ]
        )
        result = await RecipientResolver.resolve(
            _rule(RecipientType.by_role, {"role_name": "student"}),
            {},
        )
        assert result == [100, 200]
        mock_dao.get_all.assert_called_once_with(role_name="student")

    async def test_no_role_name(self, mock_dao):
        result = await RecipientResolver.resolve(
            _rule(RecipientType.by_role, {}),
            {},
        )
        assert result == []


@patch("src.dao.cohort.CohortDAO")
class TestByState:
    async def test_fetches_users(self, mock_dao):
        mock_dao.get_telegram_ids_in_cohort = AsyncMock(return_value=[300])
        result = await RecipientResolver.resolve(
            _rule(RecipientType.by_state, {"state": "Отбор"}),
            {},
        )
        assert result == [300]
        mock_dao.get_telegram_ids_in_cohort.assert_called_once_with("Status", "Отбор")

    async def test_no_state(self, mock_dao):
        result = await RecipientResolver.resolve(
            _rule(RecipientType.by_state, {}),
            {},
        )
        assert result == []
