import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from src.dao.feedback_export import FeedbackExportDAO
from src.models.meeting import Meeting
from src.models.survey_session import SurveySession
from src.models.user import User
from src.services.yandex_sheets import CellValue, YandexSheetTarget, YandexSheetsWriter

logger = logging.getLogger(__name__)

FEEDBACK_EXPORT_HEADERS: tuple[str, ...] = (
    "call_id",
    "call_started_at",
    "mentor_id",
    "mentor_name",
    "student_id",
    "student_name",
    "student_survey_status",
    "student_survey_created_at",
    "mentor_feedback_status",
    "mentor_feedback_created_at",
)


def _role_name(user: User | Any | None) -> str | None:
    if user is None:
        return None
    role_rel = getattr(user, "role_rel", None)
    if role_rel is not None:
        return role_rel.name
    return None


@dataclass(slots=True)
class FeedbackExportRow:
    call_id: int
    call_started_at: Optional[datetime] = None
    mentor_id: Optional[int] = None
    mentor_name: Optional[str] = None
    student_id: Optional[int] = None
    student_name: Optional[str] = None
    student_survey_status: Optional[str] = None
    student_survey_created_at: Optional[datetime] = None
    mentor_feedback_status: Optional[str] = None
    mentor_feedback_created_at: Optional[datetime] = None

    def to_payload(self) -> dict[str, Any]:
        return {
            header: getattr(self, header)
            for header in FEEDBACK_EXPORT_HEADERS
        }

    def to_sheet_row(self) -> list[CellValue]:
        return [getattr(self, header) for header in FEEDBACK_EXPORT_HEADERS]


@dataclass(frozen=True, slots=True)
class FeedbackExportDataset:
    headers: tuple[str, ...]
    rows: list[FeedbackExportRow]

    @property
    def rows_count(self) -> int:
        return len(self.rows)

    def sample_rows(self, limit: int = 5) -> list[dict[str, Any]]:
        return [row.to_payload() for row in self.rows[:limit]]

    def serialized_rows(self) -> list[list[CellValue]]:
        return [row.to_sheet_row() for row in self.rows]


@dataclass(frozen=True, slots=True)
class FeedbackExportResult:
    dataset: FeedbackExportDataset
    dry_run: bool
    target: YandexSheetTarget | None = None


class FeedbackExportService:
    def __init__(
        self,
        *,
        export_dao: FeedbackExportDAO | type[FeedbackExportDAO] | None = None,
        sheet_writer: YandexSheetsWriter | None = None,
    ) -> None:
        self._export_dao = export_dao or FeedbackExportDAO
        self._sheet_writer = sheet_writer

    async def run_export(
        self,
        *,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        dry_run: bool = False,
    ) -> FeedbackExportResult:
        dataset = await self.build_dataset(date_from=date_from, date_to=date_to)
        if dry_run:
            return FeedbackExportResult(dataset=dataset, dry_run=True)

        writer = self._sheet_writer or YandexSheetsWriter()
        target = await writer.replace_sheet(
            headers=dataset.headers,
            rows=dataset.serialized_rows(),
        )
        return FeedbackExportResult(
            dataset=dataset,
            dry_run=False,
            target=target,
        )

    async def build_dataset(
        self,
        *,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> FeedbackExportDataset:
        meetings = await self._export_dao.get_completed_meetings(
            date_from=date_from,
            date_to=date_to,
        )

        meeting_ids = [m.id for m in meetings]
        sessions_map = await self._export_dao.get_sessions_for_meetings(meeting_ids)

        rows = []
        for meeting in meetings:
            mid = str(meeting.id)
            student_session = sessions_map.get(f"post_call_student:{mid}")
            mentor_session = sessions_map.get(f"mentor_feedback:{mid}")

            row = self._build_row(
                meeting=meeting,
                student_session=student_session,
                mentor_session=mentor_session,
            )
            rows.append(row)

        return FeedbackExportDataset(
            headers=FEEDBACK_EXPORT_HEADERS,
            rows=rows,
        )

    def _build_row(
        self,
        *,
        meeting: Meeting,
        student_session: SurveySession | None,
        mentor_session: SurveySession | None,
    ) -> FeedbackExportRow:
        participants = list(getattr(meeting, "participants", []))

        mentor = next(
            (p for p in participants if _role_name(p) == "mentor"),
            None,
        )
        student = next(
            (p for p in participants if _role_name(p) == "student"),
            None,
        )
        if not student and mentor:
            student = next(
                (p for p in participants if p.telegram_id != mentor.telegram_id),
                None,
            )

        row = FeedbackExportRow(
            call_id=meeting.id,
            call_started_at=getattr(meeting, "scheduled_at", None)
            or getattr(meeting, "created_at", None),
            mentor_id=getattr(mentor, "telegram_id", None),
            mentor_name=getattr(mentor, "name", None),
            student_id=getattr(student, "telegram_id", None),
            student_name=getattr(student, "name", None),
        )

        if student_session:
            row.student_survey_status = student_session.status.value
            row.student_survey_created_at = student_session.completed_at

        if mentor_session:
            row.mentor_feedback_status = mentor_session.status.value
            row.mentor_feedback_created_at = mentor_session.completed_at

        return row
