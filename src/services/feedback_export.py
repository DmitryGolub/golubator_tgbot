import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from src.dao.feedback_export import FeedbackExportDAO
from src.models.meeting import Meeting
from src.models.mentor_feedback import MentorFeedback
from src.models.survey import SurveyResponse
from src.models.user import Role, User
from src.services.yandex_sheets import CellValue, YandexSheetTarget, YandexSheetsWriter

logger = logging.getLogger(__name__)

FEEDBACK_EXPORT_HEADERS: tuple[str, ...] = (
    "call_id",
    "call_started_at",
    "mentor_id",
    "mentor_name",
    "student_id",
    "student_name",
    "student_status",
    "student_duration",
    "student_motivation",
    "student_neuromutation_stage",
    "student_comment",
    "student_feedback_created_at",
    "mentor_status",
    "mentor_duration",
    "mentor_motivation",
    "mentor_neuromutation_stage",
    "mentor_comment",
    "mentor_feedback_created_at",
)


def _role_name(user: User | Any | None) -> str | None:
    if user is None:
        return None
    role = getattr(user, "role", None)
    if role is None:
        return None
    if role == Role.mentor:
        return "mentor"
    if role == Role.student:
        return "student"
    return getattr(role, "name", None)


def _normalize_datetime(value: Optional[datetime]) -> Optional[datetime]:
    return value


@dataclass(slots=True)
class FeedbackExportRow:
    call_id: int
    call_started_at: Optional[datetime] = None
    mentor_id: Optional[int] = None
    mentor_name: Optional[str] = None
    student_id: Optional[int] = None
    student_name: Optional[str] = None
    student_status: Optional[int] = None
    student_duration: Optional[str] = None
    student_motivation: Optional[int] = None
    student_neuromutation_stage: Optional[int] = None
    student_comment: Optional[str] = None
    student_feedback_created_at: Optional[datetime] = None
    mentor_status: Optional[str] = None
    mentor_duration: Optional[str] = None
    mentor_motivation: Optional[int] = None
    mentor_neuromutation_stage: Optional[int] = None
    mentor_comment: Optional[str] = None
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
        meetings = await self._export_dao.get_feedback_meetings(
            date_from=date_from,
            date_to=date_to,
        )
        mentor_feedback_map = await self._export_dao.get_mentor_feedback_map(
            [meeting.id for meeting in meetings]
        )
        fallback_users = await self._load_fallback_users(meetings, mentor_feedback_map)

        rows_by_call_id: dict[int, FeedbackExportRow] = {}
        for meeting in meetings:
            mentor_feedback = mentor_feedback_map.get(meeting.id)
            row = self._build_row(
                meeting=meeting,
                survey_response=getattr(meeting, "survey_response", None),
                mentor_feedback=mentor_feedback,
                fallback_users=fallback_users,
            )
            rows_by_call_id[row.call_id] = row

        rows = [rows_by_call_id[call_id] for call_id in sorted(rows_by_call_id)]
        return FeedbackExportDataset(
            headers=FEEDBACK_EXPORT_HEADERS,
            rows=rows,
        )

    async def _load_fallback_users(
        self,
        meetings: list[Meeting],
        mentor_feedback_map: dict[int, MentorFeedback],
    ) -> dict[int, User]:
        unresolved_user_ids: set[int] = set()

        for meeting in meetings:
            participant_ids = {
                participant.telegram_id
                for participant in getattr(meeting, "participants", [])
            }
            survey_response = getattr(meeting, "survey_response", None)
            mentor_feedback = mentor_feedback_map.get(meeting.id)
            if survey_response and survey_response.student_id not in participant_ids:
                unresolved_user_ids.add(survey_response.student_id)
            if mentor_feedback and mentor_feedback.mentor_id not in participant_ids:
                unresolved_user_ids.add(mentor_feedback.mentor_id)

        return await self._export_dao.get_users_by_ids(unresolved_user_ids)

    def _build_row(
        self,
        *,
        meeting: Meeting,
        survey_response: SurveyResponse | None,
        mentor_feedback: MentorFeedback | None,
        fallback_users: dict[int, User],
    ) -> FeedbackExportRow:
        participants = list(getattr(meeting, "participants", []))
        participant_by_id = {participant.telegram_id: participant for participant in participants}

        mentor = self._resolve_mentor(
            participants=participants,
            participant_by_id=participant_by_id,
            mentor_feedback=mentor_feedback,
            fallback_users=fallback_users,
        )
        student = self._resolve_student(
            participants=participants,
            participant_by_id=participant_by_id,
            mentor=mentor,
            survey_response=survey_response,
            fallback_users=fallback_users,
        )
        if mentor is None and student is not None:
            mentor = next(
                (
                    participant
                    for participant in participants
                    if participant.telegram_id != getattr(student, "telegram_id", None)
                ),
                None,
            )

        row = FeedbackExportRow(
            call_id=meeting.id,
            call_started_at=self._resolve_call_started_at(meeting),
            mentor_id=getattr(mentor, "telegram_id", None)
            or getattr(mentor_feedback, "mentor_id", None),
            mentor_name=getattr(mentor, "name", None),
            student_id=getattr(student, "telegram_id", None)
            or getattr(survey_response, "student_id", None),
            student_name=getattr(student, "name", None),
        )

        if mentor is None or student is None:
            logger.warning(
                "Feedback export uses partial row for call_id=%s mentor_id=%s student_id=%s",
                meeting.id,
                row.mentor_id,
                row.student_id,
            )

        if survey_response is not None:
            row.student_status = survey_response.mentor_style
            row.student_duration = survey_response.duration_option
            row.student_motivation = survey_response.knowledge_depth
            row.student_neuromutation_stage = survey_response.understanding
            row.student_comment = survey_response.comment
            row.student_feedback_created_at = _normalize_datetime(
                survey_response.created_at
            )

        if mentor_feedback is not None:
            row.mentor_status = mentor_feedback.status
            row.mentor_duration = mentor_feedback.duration
            row.mentor_motivation = mentor_feedback.motivation
            row.mentor_neuromutation_stage = mentor_feedback.neuromutation_stage
            row.mentor_comment = mentor_feedback.comment
            row.mentor_feedback_created_at = _normalize_datetime(
                mentor_feedback.created_at
            )

        return row

    @staticmethod
    def _resolve_call_started_at(meeting: Meeting) -> Optional[datetime]:
        scheduled_at = getattr(meeting, "scheduled_at", None)
        if scheduled_at is not None:
            return _normalize_datetime(scheduled_at)
        return _normalize_datetime(getattr(meeting, "created_at", None))

    @staticmethod
    def _resolve_mentor(
        *,
        participants: list[User],
        participant_by_id: dict[int, User],
        mentor_feedback: MentorFeedback | None,
        fallback_users: dict[int, User],
    ) -> User | Any | None:
        mentor = next(
            (participant for participant in participants if _role_name(participant) == "mentor"),
            None,
        )
        if mentor is not None:
            return mentor
        if mentor_feedback is not None:
            return participant_by_id.get(mentor_feedback.mentor_id) or fallback_users.get(
                mentor_feedback.mentor_id
            )
        return None

    @staticmethod
    def _resolve_student(
        *,
        participants: list[User],
        participant_by_id: dict[int, User],
        mentor: User | Any | None,
        survey_response: SurveyResponse | None,
        fallback_users: dict[int, User],
    ) -> User | Any | None:
        student = next(
            (participant for participant in participants if _role_name(participant) == "student"),
            None,
        )
        if student is not None:
            return student
        if survey_response is not None:
            return participant_by_id.get(survey_response.student_id) or fallback_users.get(
                survey_response.student_id
            )
        if mentor is not None:
            return next(
                (
                    participant
                    for participant in participants
                    if participant.telegram_id != getattr(mentor, "telegram_id", None)
                ),
                None,
            )
        return None
