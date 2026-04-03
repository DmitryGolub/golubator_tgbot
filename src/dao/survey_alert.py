from typing import Optional

from sqlalchemy import select, update

from src.core.database import async_session_maker
from src.models.survey_alert import AlertType, SurveyAlert


class SurveyAlertDAO:
    @classmethod
    async def create(
        cls,
        *,
        alert_type: AlertType,
        session_id: int,
        student_id: int | None = None,
        details: dict | None = None,
    ) -> SurveyAlert:
        async with async_session_maker() as db:
            alert = SurveyAlert(
                alert_type=alert_type,
                session_id=session_id,
                student_id=student_id,
                details=details,
            )
            db.add(alert)
            await db.commit()
            await db.refresh(alert)
            return alert

    @classmethod
    async def get_unnotified(cls) -> list[SurveyAlert]:
        async with async_session_maker() as db:
            query = (
                select(SurveyAlert)
                .where(SurveyAlert.notified.is_(False))
                .order_by(SurveyAlert.created_at)
            )
            result = await db.execute(query)
            return list(result.scalars().all())

    @classmethod
    async def mark_notified(cls, alert_id: int) -> None:
        async with async_session_maker() as db:
            await db.execute(
                update(SurveyAlert)
                .where(SurveyAlert.id == alert_id)
                .values(notified=True)
            )
            await db.commit()

    @classmethod
    async def get_for_student(
        cls,
        student_id: int,
        template_slug: str | None = None,
        limit: int = 20,
    ) -> list[SurveyAlert]:
        async with async_session_maker() as db:
            query = (
                select(SurveyAlert)
                .where(SurveyAlert.student_id == student_id)
                .order_by(SurveyAlert.created_at.desc())
                .limit(limit)
            )
            result = await db.execute(query)
            return list(result.scalars().all())

    @classmethod
    async def get_by_id(cls, alert_id: int) -> Optional[SurveyAlert]:
        async with async_session_maker() as db:
            return await db.get(SurveyAlert, alert_id)
