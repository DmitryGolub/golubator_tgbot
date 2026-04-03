import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.core.database import async_session_maker
from src.dao.survey_alert import SurveyAlertDAO
from src.models.survey_alert import AlertType, SurveyAlert
from src.models.survey_session import SessionStatus, SurveyAnswer, SurveySession

logger = logging.getLogger(__name__)

# slug -> low_score threshold (inclusive: score <= threshold triggers alert)
THRESHOLDS: dict[str, int] = {
    "mentor_self_review": 5,
}
DEFAULT_THRESHOLD = 4

# slug -> number of consecutive sessions for delta-tracking
DELTA_COUNTS: dict[str, int] = {
    "weekly_mentee_study": 3,
    "weekly_mentor_per_student": 3,
    "search_mentee_biweekly": 3,
    "search_mentor_biweekly": 3,
    "probation_mentee_biweekly": 2,
    "probation_mentor_biweekly": 2,
}

# mentee_slug -> mentor_slug for cross-validation
CROSS_PAIRS: dict[str, str] = {
    "search_mentee_biweekly": "search_mentor_biweekly",
    "probation_mentee_biweekly": "probation_mentor_biweekly",
    "weekly_mentee_study": "weekly_mentor_per_student",
}

# Context ID pattern: "2026-W14:12345" -> extract student telegram_id
_CONTEXT_STUDENT_RE = re.compile(r"^\d{4}-W\d{2}:(\d+)$")


class SurveyAnalytics:
    async def process_completed_session(
        self, session: SurveySession
    ) -> list[SurveyAlert]:
        alerts: list[SurveyAlert] = []
        slug = session.template.slug if session.template else None
        if not slug:
            return alerts

        alerts += await self._check_low_scores(session, slug)
        alerts += await self._check_mentor_not_recommend(session, slug)
        alerts += await self._check_delta_trend(session, slug)
        alerts += await self._check_cross_validation(session, slug)

        if alerts:
            logger.info(
                "SurveyAnalytics: %d alert(s) for session %d (slug=%s)",
                len(alerts),
                session.id,
                slug,
            )
        return alerts

    async def _check_low_scores(
        self, session: SurveySession, slug: str
    ) -> list[SurveyAlert]:
        threshold = THRESHOLDS.get(slug, DEFAULT_THRESHOLD)
        student_id = self._resolve_student_id(session)
        alerts: list[SurveyAlert] = []

        for answer in session.answers:
            if answer.value_int is not None and answer.value_int <= threshold:
                question_title = answer.question.title if answer.question else "unknown"
                alert = await SurveyAlertDAO.create(
                    alert_type=AlertType.low_score,
                    session_id=session.id,
                    student_id=student_id,
                    details={
                        "question": question_title,
                        "score": answer.value_int,
                        "threshold": threshold,
                        "slug": slug,
                        "respondent_id": session.respondent_id,
                    },
                )
                alerts.append(alert)
        return alerts

    async def _check_mentor_not_recommend(
        self, session: SurveySession, slug: str
    ) -> list[SurveyAlert]:
        if slug != "greeting_mentor_feedback":
            return []

        student_id = self._resolve_student_id(session)
        for answer in session.answers:
            if answer.value_choice and "no" in answer.value_choice:
                question_title = answer.question.title if answer.question else "unknown"
                alert = await SurveyAlertDAO.create(
                    alert_type=AlertType.mentor_not_recommend,
                    session_id=session.id,
                    student_id=student_id,
                    details={
                        "question": question_title,
                        "slug": slug,
                        "respondent_id": session.respondent_id,
                    },
                )
                return [alert]
        return []

    async def _check_delta_trend(
        self, session: SurveySession, slug: str
    ) -> list[SurveyAlert]:
        count = DELTA_COUNTS.get(slug)
        if not count:
            return []

        recent_sessions = await self._get_recent_completed_sessions(
            template_id=session.template_id,
            respondent_id=session.respondent_id,
            limit=count,
        )
        if len(recent_sessions) < count:
            return []

        student_id = self._resolve_student_id(session)
        alerts: list[SurveyAlert] = []

        # Group answers by question_id across sessions (most recent first)
        question_scores: dict[int, list[int]] = {}
        for s in recent_sessions:
            for answer in s.answers:
                if answer.value_int is not None:
                    question_scores.setdefault(answer.question_id, []).append(
                        answer.value_int
                    )

        for question_id, scores in question_scores.items():
            if len(scores) < count:
                continue
            # scores[0] is most recent, scores[-1] is oldest
            # Monotonically declining: each older score > next newer score
            is_declining = all(scores[i] < scores[i + 1] for i in range(count - 1))
            if is_declining:
                alert = await SurveyAlertDAO.create(
                    alert_type=AlertType.delta_decline,
                    session_id=session.id,
                    student_id=student_id,
                    details={
                        "question_id": question_id,
                        "scores": scores[:count],
                        "count": count,
                        "slug": slug,
                        "respondent_id": session.respondent_id,
                    },
                )
                alerts.append(alert)
        return alerts

    async def _check_cross_validation(
        self, session: SurveySession, slug: str
    ) -> list[SurveyAlert]:
        paired_slug = CROSS_PAIRS.get(slug)
        if not paired_slug:
            return []

        if not session.context_id:
            return []

        student_id = self._resolve_student_id(session)

        # Find paired session with same context_id pattern (same week, same student)
        paired_session = await self._find_paired_session(
            paired_slug=paired_slug,
            context_id=session.context_id,
        )
        if not paired_session:
            return []

        # Compare average ratings
        avg_current = self._avg_rating(session.answers)
        avg_paired = self._avg_rating(paired_session.answers)

        if avg_current is None or avg_paired is None:
            return []

        diff = abs(avg_current - avg_paired)
        if diff > 4:
            alert = await SurveyAlertDAO.create(
                alert_type=AlertType.cross_mismatch,
                session_id=session.id,
                student_id=student_id,
                details={
                    "slug": slug,
                    "paired_slug": paired_slug,
                    "avg_current": round(avg_current, 2),
                    "avg_paired": round(avg_paired, 2),
                    "diff": round(diff, 2),
                    "respondent_id": session.respondent_id,
                    "paired_respondent_id": paired_session.respondent_id,
                },
            )
            return [alert]
        return []

    def _resolve_student_id(self, session: SurveySession) -> int | None:
        if not session.context_id:
            return None
        m = _CONTEXT_STUDENT_RE.match(session.context_id)
        if m:
            return int(m.group(1))
        return None

    @staticmethod
    def _avg_rating(answers: list[SurveyAnswer]) -> float | None:
        ratings = [a.value_int for a in answers if a.value_int is not None]
        if not ratings:
            return None
        return sum(ratings) / len(ratings)

    @staticmethod
    async def _get_recent_completed_sessions(
        *, template_id: int, respondent_id: int, limit: int
    ) -> list[SurveySession]:
        async with async_session_maker() as db:
            query = (
                select(SurveySession)
                .where(
                    SurveySession.template_id == template_id,
                    SurveySession.respondent_id == respondent_id,
                    SurveySession.status == SessionStatus.completed,
                )
                .options(
                    joinedload(SurveySession.answers).joinedload(SurveyAnswer.question),
                )
                .order_by(SurveySession.completed_at.desc())
                .limit(limit)
            )
            result = await db.execute(query)
            return list(result.unique().scalars().all())

    @staticmethod
    async def _find_paired_session(
        *, paired_slug: str, context_id: str
    ) -> SurveySession | None:
        async with async_session_maker() as db:
            from src.models.survey_template import SurveyTemplate

            query = (
                select(SurveySession)
                .join(SurveyTemplate, SurveySession.template_id == SurveyTemplate.id)
                .where(
                    SurveyTemplate.slug == paired_slug,
                    SurveySession.context_id == context_id,
                    SurveySession.status == SessionStatus.completed,
                )
                .options(
                    joinedload(SurveySession.answers).joinedload(SurveyAnswer.question),
                )
                .limit(1)
            )
            result = await db.execute(query)
            return result.unique().scalar_one_or_none()
