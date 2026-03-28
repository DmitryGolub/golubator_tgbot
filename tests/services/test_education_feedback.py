from unittest.mock import AsyncMock, patch

from src.dao.education_feedback import EducationFeedbackRow
from src.services.education_feedback import EducationFeedbackService


@patch("src.services.education_feedback.EducationFeedbackDAO")
class TestEducationFeedbackService:
    async def test_empty_returns_empty_string(self, mock_dao):
        mock_dao.get_summary = AsyncMock(return_value=[])
        result = await EducationFeedbackService.get_summary()
        assert result == ""

    async def test_formats_rows(self, mock_dao):
        mock_dao.get_summary = AsyncMock(
            return_value=[
                EducationFeedbackRow(
                    direction="Backend",
                    mentor_name="Alice",
                    total_meetings=4,
                    surveys_completed=2,
                    avg_rating=4.5,
                ),
                EducationFeedbackRow(
                    direction="Frontend",
                    mentor_name="Bob",
                    total_meetings=3,
                    surveys_completed=1,
                    avg_rating=None,
                ),
            ]
        )
        result = await EducationFeedbackService.get_summary()
        assert "Backend" in result
        assert "Alice" in result
        assert "4.5" in result
        assert "Frontend" in result
        assert "—" in result

    async def test_passes_date_filters(self, mock_dao):
        from datetime import datetime, timezone

        mock_dao.get_summary = AsyncMock(return_value=[])
        date_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2026, 3, 1, tzinfo=timezone.utc)
        await EducationFeedbackService.get_summary(date_from=date_from, date_to=date_to)
        mock_dao.get_summary.assert_called_once_with(
            date_from=date_from, date_to=date_to
        )
