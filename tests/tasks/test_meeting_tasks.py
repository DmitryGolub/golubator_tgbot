from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy.exc import IntegrityError

from tests.conftest import make_meeting, make_user
from src.tasks.meeting import _auto_start_due_calls_async, _split_participants


CREATOR_ID = 100
OTHER1_ID = 200
OTHER2_ID = 300
OTHER3_ID = 400


def _creator():
    return make_user(telegram_id=CREATOR_ID, name="Creator")


def _other(tid, name="Other"):
    return make_user(telegram_id=tid, name=name)


class TestSplitParticipants:
    def test_single_other(self):
        meeting = make_meeting(
            participants=[_creator(), _other(OTHER1_ID)],
            mentor_telegram_id=CREATOR_ID,
        )
        creator, others = _split_participants(meeting)
        assert creator is not None
        assert creator.telegram_id == CREATOR_ID
        assert len(others) == 1
        assert others[0].telegram_id == OTHER1_ID

    def test_multiple_others(self):
        meeting = make_meeting(
            participants=[
                _creator(),
                _other(OTHER1_ID),
                _other(OTHER2_ID),
                _other(OTHER3_ID),
            ],
            mentor_telegram_id=CREATOR_ID,
        )
        creator, others = _split_participants(meeting)
        assert creator is not None
        assert len(others) == 3
        assert {p.telegram_id for p in others} == {OTHER1_ID, OTHER2_ID, OTHER3_ID}

    def test_no_creator(self):
        meeting = make_meeting(
            participants=[_other(OTHER1_ID), _other(OTHER2_ID)],
            mentor_telegram_id=999,
        )
        creator, others = _split_participants(meeting)
        assert creator is None
        assert len(others) == 2

    def test_empty_participants(self):
        meeting = make_meeting(participants=[], mentor_telegram_id=CREATOR_ID)
        creator, others = _split_participants(meeting)
        assert creator is None
        assert others == []


class TestAutoStartDueCalls:
    def _patches(self):
        mock_db = patch("src.tasks.meeting.celery_db")
        mock_dao = patch("src.tasks.meeting.MeetingDAO")
        return mock_db, mock_dao

    async def test_no_due_meetings(self):
        with (
            patch("src.tasks.meeting.celery_db") as mock_db,
            patch("src.tasks.meeting.MeetingDAO") as mock_dao,
        ):
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()
            mock_dao.find_due_unstarted_call_ids = AsyncMock(return_value=[])
            mock_dao.start_call = AsyncMock()

            await _auto_start_due_calls_async()

            mock_dao.find_due_unstarted_call_ids.assert_awaited_once()
            mock_dao.start_call.assert_not_called()

    async def test_starts_each_meeting_with_scheduled_at(self):
        sched1 = datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc)
        sched2 = datetime(2026, 4, 12, 11, 0, tzinfo=timezone.utc)
        with (
            patch("src.tasks.meeting.celery_db") as mock_db,
            patch("src.tasks.meeting.MeetingDAO") as mock_dao,
        ):
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()
            mock_dao.find_due_unstarted_call_ids = AsyncMock(
                return_value=[(1, sched1), (2, sched2)]
            )
            mock_dao.start_call = AsyncMock(
                side_effect=[make_meeting(id=1), make_meeting(id=2)]
            )

            await _auto_start_due_calls_async()

            assert mock_dao.start_call.await_count == 2
            mock_dao.start_call.assert_any_await(1, started_at=sched1)
            mock_dao.start_call.assert_any_await(2, started_at=sched2)

    async def test_integrity_error_skips_and_continues(self):
        sched1 = datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc)
        sched2 = datetime(2026, 4, 12, 11, 0, tzinfo=timezone.utc)
        with (
            patch("src.tasks.meeting.celery_db") as mock_db,
            patch("src.tasks.meeting.MeetingDAO") as mock_dao,
        ):
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()
            mock_dao.find_due_unstarted_call_ids = AsyncMock(
                return_value=[(1, sched1), (2, sched2)]
            )
            mock_dao.start_call = AsyncMock(
                side_effect=[
                    IntegrityError("stmt", {}, Exception("active call exists")),
                    make_meeting(id=2),
                ]
            )

            await _auto_start_due_calls_async()

            assert mock_dao.start_call.await_count == 2

    async def test_race_none_result_skipped(self):
        sched1 = datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc)
        with (
            patch("src.tasks.meeting.celery_db") as mock_db,
            patch("src.tasks.meeting.MeetingDAO") as mock_dao,
        ):
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()
            mock_dao.find_due_unstarted_call_ids = AsyncMock(return_value=[(1, sched1)])
            mock_dao.start_call = AsyncMock(return_value=None)

            # Should not raise
            await _auto_start_due_calls_async()
            mock_dao.start_call.assert_awaited_once_with(1, started_at=sched1)
