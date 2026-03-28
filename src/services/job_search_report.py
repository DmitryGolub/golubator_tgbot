from datetime import datetime
from typing import Optional

from src.dao.job_search_report import JobSearchReportDAO, JobSearchRow


class JobSearchReportService:
    @staticmethod
    async def get_summary(
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> str:
        rows = await JobSearchReportDAO.get_summary(
            date_from=date_from, date_to=date_to
        )
        if not rows:
            return ""
        return _format_rows(rows)


def _format_rows(rows: list[JobSearchRow]) -> str:
    lines = ["<b>💼 Отчёт: Поиск работы</b>\n"]
    for row in rows:
        lines.append(
            f"📌 {row.direction} | {row.mentor_name}\n"
            f"   Встреч: {row.total_meetings}, опросов: {row.surveys_completed}"
        )
    return "\n".join(lines)
