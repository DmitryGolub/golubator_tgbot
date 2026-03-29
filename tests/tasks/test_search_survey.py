from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tasks.weekly_survey import _send_mentor_survey_batch


def _make_mentee(telegram_id, mentor_tid, student_name="Student"):
    user = SimpleNamespace(name=student_name)
    mentor = SimpleNamespace(telegram_id=mentor_tid)
    return SimpleNamespace(
        telegram_id=telegram_id,
        user=user,
        mentor=mentor,
        doc_name=student_name,
    )


def _make_template(id=1):
    return SimpleNamespace(id=id, slug="search_mentor_biweekly")


def _make_session(id=10):
    return SimpleNamespace(id=id)


# ---------------------------------------------------------------------------
# Even ISO week: 2026-01-05 is Monday of week 2 (even)
# Odd ISO week: 2026-01-12 is Monday of week 3 (odd)
# ---------------------------------------------------------------------------

EVEN_WEEK = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
ODD_WEEK = datetime(2026, 1, 12, 12, 0, tzinfo=timezone.utc)

BATCH_KWARGS = dict(
    template_slug="search_mentor_biweekly",
    cohort_type="Status",
    cohort_value="search",
    context_type="search_biweekly",
    title="Опрос по ученику в поиске работы",
    log_prefix="Search biweekly mentor",
    biweekly=True,
)


class TestSearchBiweeklyMentor:
    @pytest.mark.parametrize("odd_dt", [ODD_WEEK])
    async def test_skip_odd_week(self, odd_dt):
        with patch(
            "src.tasks.weekly_survey.datetime",
        ) as mock_dt:
            mock_dt.now.return_value = odd_dt
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            # Should return early without touching DB
            with patch("src.tasks.weekly_survey.celery_db") as mock_db:
                await _send_mentor_survey_batch(**BATCH_KWARGS)
                mock_db.assert_not_called()

    async def test_no_mentees_in_search(self):
        with (
            patch("src.tasks.weekly_survey.datetime") as mock_dt,
            patch("src.tasks.weekly_survey.celery_db") as mock_db,
            patch("src.tasks.weekly_survey.Bot") as MockBot,
        ):
            mock_dt.now.return_value = EVEN_WEEK
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            bot_instance = AsyncMock()
            bot_instance.session = MagicMock()
            bot_instance.session.close = AsyncMock()
            MockBot.return_value = bot_instance
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()

            with (
                patch(
                    "src.dao.survey_template.SurveyTemplateDAO.get_by_slug",
                    new_callable=AsyncMock,
                    return_value=_make_template(),
                ),
                patch(
                    "src.dao.cohort.CohortDAO.get_telegram_ids_in_cohort",
                    new_callable=AsyncMock,
                    return_value=[],
                ),
            ):
                await _send_mentor_survey_batch(**BATCH_KWARGS)
                bot_instance.send_message.assert_not_called()

    async def test_mentor_surveys_sent(self):
        mentee = _make_mentee(200, mentor_tid=300, student_name="Alice")
        template = _make_template(id=5)
        session = _make_session(id=42)

        with (
            patch("src.tasks.weekly_survey.datetime") as mock_dt,
            patch("src.tasks.weekly_survey.celery_db") as mock_db,
            patch("src.tasks.weekly_survey.Bot") as MockBot,
        ):
            mock_dt.now.return_value = EVEN_WEEK
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            bot_instance = AsyncMock()
            bot_instance.session = MagicMock()
            bot_instance.session.close = AsyncMock()
            MockBot.return_value = bot_instance
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()

            with (
                patch(
                    "src.dao.survey_template.SurveyTemplateDAO.get_by_slug",
                    new_callable=AsyncMock,
                    return_value=template,
                ),
                patch(
                    "src.dao.cohort.CohortDAO.get_telegram_ids_in_cohort",
                    new_callable=AsyncMock,
                    return_value=[200],
                ),
                patch(
                    "src.dao.mentee.MenteeDAO.get_by_telegram_ids",
                    new_callable=AsyncMock,
                    return_value=[mentee],
                ),
                patch(
                    "src.services.survey_session.SurveySessionService.create_session",
                    new_callable=AsyncMock,
                    return_value=(session, False),
                ) as mock_create,
            ):
                await _send_mentor_survey_batch(**BATCH_KWARGS)

                mock_create.assert_called_once_with(
                    template_id=5,
                    respondent_id=300,
                    context_type="search_biweekly",
                    context_id="2026-W02:200",
                )
                bot_instance.send_message.assert_called_once()
                call_args = bot_instance.send_message.call_args
                assert call_args[0][0] == 300
                assert "Alice" in call_args[0][1]

    async def test_mentor_gets_separate_survey_per_mentee(self):
        mentee1 = _make_mentee(201, mentor_tid=300, student_name="Alice")
        mentee2 = _make_mentee(202, mentor_tid=300, student_name="Bob")
        template = _make_template(id=5)

        with (
            patch("src.tasks.weekly_survey.datetime") as mock_dt,
            patch("src.tasks.weekly_survey.celery_db") as mock_db,
            patch("src.tasks.weekly_survey.Bot") as MockBot,
        ):
            mock_dt.now.return_value = EVEN_WEEK
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            bot_instance = AsyncMock()
            bot_instance.session = MagicMock()
            bot_instance.session.close = AsyncMock()
            MockBot.return_value = bot_instance
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()

            with (
                patch(
                    "src.dao.survey_template.SurveyTemplateDAO.get_by_slug",
                    new_callable=AsyncMock,
                    return_value=template,
                ),
                patch(
                    "src.dao.cohort.CohortDAO.get_telegram_ids_in_cohort",
                    new_callable=AsyncMock,
                    return_value=[201, 202],
                ),
                patch(
                    "src.dao.mentee.MenteeDAO.get_by_telegram_ids",
                    new_callable=AsyncMock,
                    return_value=[mentee1, mentee2],
                ),
                patch(
                    "src.services.survey_session.SurveySessionService.create_session",
                    new_callable=AsyncMock,
                    return_value=(_make_session(), False),
                ) as mock_create,
            ):
                await _send_mentor_survey_batch(**BATCH_KWARGS)

                assert mock_create.call_count == 2
                context_ids = {
                    call.kwargs["context_id"] for call in mock_create.call_args_list
                }
                assert context_ids == {"2026-W02:201", "2026-W02:202"}
                assert bot_instance.send_message.call_count == 2

    async def test_mentee_without_mentor_skipped(self):
        mentee_no_mentor = SimpleNamespace(
            telegram_id=200,
            user=SimpleNamespace(name="Orphan"),
            mentor=None,
            doc_name="Orphan",
        )
        template = _make_template(id=5)

        with (
            patch("src.tasks.weekly_survey.datetime") as mock_dt,
            patch("src.tasks.weekly_survey.celery_db") as mock_db,
            patch("src.tasks.weekly_survey.Bot") as MockBot,
        ):
            mock_dt.now.return_value = EVEN_WEEK
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            bot_instance = AsyncMock()
            bot_instance.session = MagicMock()
            bot_instance.session.close = AsyncMock()
            MockBot.return_value = bot_instance
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()

            with (
                patch(
                    "src.dao.survey_template.SurveyTemplateDAO.get_by_slug",
                    new_callable=AsyncMock,
                    return_value=template,
                ),
                patch(
                    "src.dao.cohort.CohortDAO.get_telegram_ids_in_cohort",
                    new_callable=AsyncMock,
                    return_value=[200],
                ),
                patch(
                    "src.dao.mentee.MenteeDAO.get_by_telegram_ids",
                    new_callable=AsyncMock,
                    return_value=[mentee_no_mentor],
                ),
            ):
                await _send_mentor_survey_batch(**BATCH_KWARGS)
                bot_instance.send_message.assert_not_called()

    async def test_deduplication(self):
        mentee = _make_mentee(200, mentor_tid=300, student_name="Alice")
        template = _make_template(id=5)
        session = _make_session(id=42)

        with (
            patch("src.tasks.weekly_survey.datetime") as mock_dt,
            patch("src.tasks.weekly_survey.celery_db") as mock_db,
            patch("src.tasks.weekly_survey.Bot") as MockBot,
        ):
            mock_dt.now.return_value = EVEN_WEEK
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            bot_instance = AsyncMock()
            bot_instance.session = MagicMock()
            bot_instance.session.close = AsyncMock()
            MockBot.return_value = bot_instance
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()

            with (
                patch(
                    "src.dao.survey_template.SurveyTemplateDAO.get_by_slug",
                    new_callable=AsyncMock,
                    return_value=template,
                ),
                patch(
                    "src.dao.cohort.CohortDAO.get_telegram_ids_in_cohort",
                    new_callable=AsyncMock,
                    return_value=[200],
                ),
                patch(
                    "src.dao.mentee.MenteeDAO.get_by_telegram_ids",
                    new_callable=AsyncMock,
                    return_value=[mentee],
                ),
                patch(
                    "src.services.survey_session.SurveySessionService.create_session",
                    new_callable=AsyncMock,
                    return_value=(session, True),  # already_existed=True
                ),
            ):
                await _send_mentor_survey_batch(**BATCH_KWARGS)
                bot_instance.send_message.assert_not_called()
