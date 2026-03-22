from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.services.feedback_export import (
    FEEDBACK_EXPORT_HEADERS,
    FeedbackExportDataset,
    FeedbackExportResult,
    FeedbackExportRow,
    FeedbackExportService,
)
from src.services.yandex_sheets import YandexSheetTarget


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _role(name: str, *, is_mentor: bool = False, is_student: bool = False) -> SimpleNamespace:
    return SimpleNamespace(name=name, display_name=name.capitalize(), is_mentor=is_mentor, is_student=is_student)


def _user(user_id: int, name: str, role_name: str) -> SimpleNamespace:
    is_mentor = role_name == "mentor"
    is_student = role_name == "student"
    return SimpleNamespace(
        telegram_id=user_id,
        name=name,
        role_rel=_role(role_name, is_mentor=is_mentor, is_student=is_student),
    )


def _survey_response(
    *,
    call_id: int,
    student_id: int,
    duration_option: str = "45_60",
    mentor_style: int = 5,
    knowledge_depth: int = 4,
    understanding: int = 3,
    comment: str | None = "Комментарий ученика",
    created_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        call_id=call_id,
        student_id=student_id,
        duration_option=duration_option,
        mentor_style=mentor_style,
        knowledge_depth=knowledge_depth,
        understanding=understanding,
        comment=comment,
        created_at=created_at or datetime(2026, 3, 10, 9, 30, tzinfo=timezone.utc),
    )


def _mentor_feedback(
    *,
    call_id: int,
    mentor_id: int,
    status: str = "ok",
    duration: str = "min_30_60",
    motivation: int = 4,
    neuromutation_stage: int = 7,
    comment: str | None = "Комментарий ментора",
    created_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        call_id=call_id,
        mentor_id=mentor_id,
        status=status,
        duration=duration,
        motivation=motivation,
        neuromutation_stage=neuromutation_stage,
        comment=comment,
        created_at=created_at or datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
    )


def _meeting(
    *,
    meeting_id: int,
    participants: list[SimpleNamespace],
    survey_response: SimpleNamespace | None = None,
    scheduled_at: datetime | None = None,
    created_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=meeting_id,
        participants=participants,
        survey_response=survey_response,
        scheduled_at=scheduled_at or datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc),
        created_at=created_at or datetime(2026, 3, 9, 8, 0, tzinfo=timezone.utc),
    )


class FakeExportDAO:
    def __init__(
        self,
        *,
        meetings: list[SimpleNamespace],
        mentor_feedback_map: dict[int, SimpleNamespace],
        fallback_users: dict[int, SimpleNamespace] | None = None,
    ) -> None:
        self._meetings = meetings
        self._mentor_feedback_map = mentor_feedback_map
        self._fallback_users = fallback_users or {}
        self.date_from = None
        self.date_to = None
        self.requested_user_ids: set[int] | None = None
        self.requested_call_ids: list[int] | None = None

    async def get_feedback_meetings(self, *, date_from=None, date_to=None):
        self.date_from = date_from
        self.date_to = date_to
        return self._meetings

    async def get_mentor_feedback_map(self, call_ids):
        self.requested_call_ids = list(call_ids)
        return self._mentor_feedback_map

    async def get_users_by_ids(self, user_ids):
        self.requested_user_ids = set(user_ids)
        return {user_id: self._fallback_users[user_id] for user_id in user_ids if user_id in self._fallback_users}


class FakeWriter:
    def __init__(self, *, target: YandexSheetTarget | None = None) -> None:
        self.target = target or YandexSheetTarget(
            file_path="/analytics/feedback_export.xlsx",
            sheet_name="feedback_export",
        )
        self.calls: list[dict[str, object]] = []

    async def replace_sheet(self, *, headers, rows):
        self.calls.append({"headers": headers, "rows": rows})
        return self.target


@pytest.mark.anyio
async def test_build_dataset_deduplicates_call_ids_and_maps_feedback_fields() -> None:
    mentor = _user(1001, "Ментор", "mentor")
    student = _user(2002, "Ученик", "student")
    survey_response = _survey_response(call_id=101, student_id=student.telegram_id)
    meeting = _meeting(
        meeting_id=101,
        participants=[mentor, student],
        survey_response=survey_response,
    )
    dao = FakeExportDAO(
        meetings=[meeting, meeting],
        mentor_feedback_map={101: _mentor_feedback(call_id=101, mentor_id=mentor.telegram_id)},
    )

    service = FeedbackExportService(export_dao=dao)
    dataset = await service.build_dataset()

    assert dataset.headers == FEEDBACK_EXPORT_HEADERS
    assert dataset.rows_count == 1
    row = dataset.rows[0].to_payload()

    assert row["call_id"] == 101
    assert row["call_started_at"] == meeting.scheduled_at
    assert row["mentor_id"] == 1001
    assert row["mentor_name"] == "Ментор"
    assert row["student_id"] == 2002
    assert row["student_name"] == "Ученик"
    assert row["student_status"] == 5
    assert row["student_duration"] == "45_60"
    assert row["student_motivation"] == 4
    assert row["student_neuromutation_stage"] == 3
    assert row["student_comment"] == "Комментарий ученика"
    assert row["mentor_status"] == "ok"
    assert row["mentor_duration"] == "min_30_60"
    assert row["mentor_motivation"] == 4
    assert row["mentor_neuromutation_stage"] == 7
    assert row["mentor_comment"] == "Комментарий ментора"
    assert dao.requested_call_ids == [101, 101]


@pytest.mark.anyio
async def test_run_export_dry_run_does_not_call_writer_and_passes_date_filters() -> None:
    dao = FakeExportDAO(
        meetings=[],
        mentor_feedback_map={},
    )
    writer = FakeWriter()
    service = FeedbackExportService(export_dao=dao, sheet_writer=writer)
    date_from = datetime(2026, 3, 1, tzinfo=timezone.utc)
    date_to = datetime(2026, 3, 31, tzinfo=timezone.utc)

    result = await service.run_export(
        date_from=date_from,
        date_to=date_to,
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.dataset.rows_count == 0
    assert writer.calls == []
    assert dao.date_from == date_from
    assert dao.date_to == date_to


@pytest.mark.anyio
async def test_run_export_calls_writer_with_headers_and_rows() -> None:
    mentor = _user(1001, "Ментор", "mentor")
    student = _user(2002, "Ученик", "student")
    dao = FakeExportDAO(
        meetings=[
            _meeting(
                meeting_id=101,
                participants=[mentor, student],
                survey_response=_survey_response(call_id=101, student_id=student.telegram_id),
            )
        ],
        mentor_feedback_map={101: _mentor_feedback(call_id=101, mentor_id=mentor.telegram_id)},
    )
    writer = FakeWriter()
    service = FeedbackExportService(export_dao=dao, sheet_writer=writer)

    result = await service.run_export(dry_run=False)

    assert result.dry_run is False
    assert result.target == writer.target
    assert len(writer.calls) == 1
    assert writer.calls[0]["headers"] == FEEDBACK_EXPORT_HEADERS
    assert writer.calls[0]["rows"][0][0] == 101
    assert writer.calls[0]["rows"][0][2] == 1001
    assert writer.calls[0]["rows"][0][4] == 2002


@pytest.mark.anyio
async def test_build_dataset_keeps_partial_row_for_incomplete_data() -> None:
    meeting = _meeting(
        meeting_id=202,
        participants=[],
        survey_response=_survey_response(call_id=202, student_id=2002),
    )
    dao = FakeExportDAO(
        meetings=[meeting],
        mentor_feedback_map={202: _mentor_feedback(call_id=202, mentor_id=1001)},
        fallback_users={1001: _user(1001, "Ментор", "mentor")},
    )

    service = FeedbackExportService(export_dao=dao)
    dataset = await service.build_dataset()

    assert dataset.rows_count == 1
    row = dataset.rows[0].to_payload()
    assert row["call_id"] == 202
    assert row["mentor_id"] == 1001
    assert row["mentor_name"] == "Ментор"
    assert row["student_id"] == 2002
    assert row["student_name"] is None
    assert dao.requested_user_ids == {1001, 2002}
