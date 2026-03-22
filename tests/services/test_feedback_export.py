from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.services.feedback_export import (
    FEEDBACK_EXPORT_HEADERS,
    FeedbackExportRow,
    FeedbackExportService,
    _role_name,
)
from tests.conftest import make_meeting, make_role, make_user


class TestRoleName:
    def test_none(self):
        assert _role_name(None) is None

    def test_user_with_role(self):
        user = make_user(role_rel=make_role(name="mentor"))
        assert _role_name(user) == "mentor"

    def test_user_without_role(self):
        user = make_user(role_rel=None)
        assert _role_name(user) is None


class TestFeedbackExportRow:
    def test_to_sheet_row(self):
        row = FeedbackExportRow(call_id=1, mentor_id=100, student_id=200)
        result = row.to_sheet_row()
        assert len(result) == len(FEEDBACK_EXPORT_HEADERS)
        assert result[0] == 1
        assert result[2] == 100
        assert result[4] == 200

    def test_to_payload(self):
        row = FeedbackExportRow(call_id=1, mentor_name="Alice")
        payload = row.to_payload()
        assert payload["call_id"] == 1
        assert payload["mentor_name"] == "Alice"


class TestBuildDataset:
    async def test_builds_rows(self):
        mentor = make_user(
            telegram_id=100,
            name="Mentor",
            role_rel=make_role(name="mentor"),
        )
        student = make_user(
            telegram_id=200,
            name="Student",
            role_rel=make_role(name="student"),
        )
        meeting = make_meeting(
            id=1,
            participants=[mentor, student],
            scheduled_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        mock_dao = AsyncMock()
        mock_dao.get_completed_meetings = AsyncMock(return_value=[meeting])
        mock_dao.get_sessions_for_meetings = AsyncMock(return_value={})

        svc = FeedbackExportService(export_dao=mock_dao)
        dataset = await svc.build_dataset()
        assert dataset.rows_count == 1
        assert dataset.rows[0].mentor_id == 100
        assert dataset.rows[0].student_id == 200


class TestRunExport:
    async def test_dry_run_skips_writer(self):
        mock_dao = AsyncMock()
        mock_dao.get_completed_meetings = AsyncMock(return_value=[])
        mock_dao.get_sessions_for_meetings = AsyncMock(return_value={})

        svc = FeedbackExportService(export_dao=mock_dao)
        result = await svc.run_export(dry_run=True)
        assert result.dry_run is True
        assert result.target is None

    async def test_real_export_calls_writer(self):
        mock_dao = AsyncMock()
        mock_dao.get_completed_meetings = AsyncMock(return_value=[])
        mock_dao.get_sessions_for_meetings = AsyncMock(return_value={})

        mock_writer = AsyncMock()
        target = SimpleNamespace(file_path="/test", sheet_name="test")
        mock_writer.replace_sheet = AsyncMock(return_value=target)

        svc = FeedbackExportService(export_dao=mock_dao, sheet_writer=mock_writer)
        result = await svc.run_export(dry_run=False)
        assert result.dry_run is False
        assert result.target is target
        mock_writer.replace_sheet.assert_called_once()
