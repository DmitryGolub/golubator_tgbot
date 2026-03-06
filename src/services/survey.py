from src.api.schemas.survey import SurveyQuestion, SurveyQuestionOption, SurveyStatus, SurveySubmitRequest
from src.survey.constants import DURATION_OPTION_LABELS


class CallNotFoundError(Exception):
    pass


class SurveyNotAvailableError(Exception):
    pass


class SurveyStudentNotFoundError(Exception):
    pass


class SurveyService:
    @staticmethod
    def build_questions() -> list[SurveyQuestion]:
        duration_options = [
            SurveyQuestionOption(value=option.value, label=label)
            for option, label in DURATION_OPTION_LABELS.items()
        ]

        return [
            SurveyQuestion(
                id="duration_option",
                title="Длительность созвона",
                kind="choice",
                required=True,
                options=duration_options,
            ),
            SurveyQuestion(
                id="mentor_style",
                title="Стиль общения ментора",
                kind="rating",
                required=True,
                min_value=1,
                max_value=5,
            ),
            SurveyQuestion(
                id="knowledge_depth",
                title="Глубина проверки знаний",
                kind="rating",
                required=True,
                min_value=1,
                max_value=5,
            ),
            SurveyQuestion(
                id="understanding",
                title="Насколько ученик понял материал",
                kind="rating",
                required=True,
                min_value=1,
                max_value=5,
            ),
            SurveyQuestion(
                id="comment",
                title="Комментарий",
                kind="text",
                required=False,
            ),
        ]

    @staticmethod
    def _resolve_student_id(meeting) -> int | None:
        mentor = next((p for p in meeting.participants if getattr(p.role, "name", "") == "mentor"), None)
        student = next((p for p in meeting.participants if getattr(p.role, "name", "") == "student"), None)

        if student:
            return student.telegram_id

        if mentor:
            fallback = next(
                (p for p in meeting.participants if p.telegram_id != mentor.telegram_id),
                None,
            )
            if fallback:
                return fallback.telegram_id

        return None

    async def get_survey_state(self, call_id: int) -> tuple[SurveyStatus, object | None]:
        from src.dao.survey import SurveyDAO

        meeting = await SurveyDAO.get_call_with_participants(call_id)
        if not meeting:
            raise CallNotFoundError

        if meeting.survey_response:
            return SurveyStatus.completed, meeting.survey_response

        if meeting.completed_at is None or meeting.survey_available_at is None:
            return SurveyStatus.not_available, None

        return SurveyStatus.available, None

    async def submit_survey(
        self,
        *,
        call_id: int,
        payload: SurveySubmitRequest,
    ) -> tuple[object, bool]:
        from src.dao.survey import SurveyDAO

        meeting = await SurveyDAO.get_call_with_participants(call_id)
        if not meeting:
            raise CallNotFoundError

        if meeting.completed_at is None or meeting.survey_available_at is None:
            raise SurveyNotAvailableError

        student_id = self._resolve_student_id(meeting)
        if student_id is None:
            raise SurveyStudentNotFoundError

        return await SurveyDAO.submit_response(
            call_id=call_id,
            student_id=student_id,
            duration_option=payload.duration_option.value,
            mentor_style=payload.mentor_style,
            knowledge_depth=payload.knowledge_depth,
            understanding=payload.understanding,
            comment=payload.comment,
        )
