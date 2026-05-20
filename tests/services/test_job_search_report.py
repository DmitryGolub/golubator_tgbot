from unittest.mock import AsyncMock, patch

from src.dao.job_search_report import JobSearchRow
from src.services.job_search_report import JobSearchReportService


@patch("src.services.job_search_report.JobSearchReportDAO")
class TestJobSearchReportService:
    async def test_empty_returns_empty_string(self, mock_dao):
        mock_dao.get_summary = AsyncMock(return_value=[])
        result = await JobSearchReportService.get_summary()
        assert result == ""

    async def test_formats_rows(self, mock_dao):
        mock_dao.get_summary = AsyncMock(
            return_value=[
                JobSearchRow(
                    direction="Backend",
                    mentor_name="Alice",
                    total_meetings=5,
                    surveys_completed=3,
                ),
                JobSearchRow(
                    direction="Frontend",
                    mentor_name="Bob",
                    total_meetings=2,
                    surveys_completed=1,
                ),
            ]
        )
        result = await JobSearchReportService.get_summary()
        assert "Backend" in result
        assert "Alice" in result
        assert "Встреч: 5" in result
        assert "Frontend" in result
        assert "Bob" in result

    async def test_passes_date_filters(self, mock_dao):
        from datetime import datetime, timezone

        mock_dao.get_summary = AsyncMock(return_value=[])
        date_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2026, 3, 1, tzinfo=timezone.utc)
        await JobSearchReportService.get_summary(date_from=date_from, date_to=date_to)
        mock_dao.get_summary.assert_called_once_with(
            date_from=date_from, date_to=date_to
        )
