from datetime import datetime
from typing import Optional

from src.dao.education_feedback import EducationFeedbackDAO, EducationFeedbackRow


class EducationFeedbackService:
    @staticmethod
    async def get_summary(
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> str:
        rows = await EducationFeedbackDAO.get_summary(
            date_from=date_from, date_to=date_to
        )
        if not rows:
            return ""
        return _format_rows(rows)


def _format_rows(rows: list[EducationFeedbackRow]) -> str:
    lines = ["<b>📚 Обратная связь: Обучение</b>\n"]
    for row in rows:
        rating = f"{row.avg_rating:.1f}" if row.avg_rating is not None else "—"
        lines.append(
            f"📌 {row.direction} | {row.mentor_name}\n"
            f"   Встреч: {row.total_meetings}, опросов: {row.surveys_completed}, "
            f"ср. оценка: {rating}"
        )
    return "\n".join(lines)
