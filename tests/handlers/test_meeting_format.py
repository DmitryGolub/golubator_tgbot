from tests.conftest import make_meeting, make_user
from src.bot.handlers.meeting import _format_meetings


MENTOR_ID = 100


def _mentor():
    return make_user(telegram_id=MENTOR_ID, name="Mentor", username="mentor")


class TestFormatMeetings:
    def test_single_participant(self):
        other = make_user(telegram_id=200, name="Student", username="student")
        meeting = make_meeting(
            participants=[_mentor(), other],
            mentor_telegram_id=MENTOR_ID,
        )
        result = _format_meetings([meeting], mentor_tg_ids={MENTOR_ID})
        assert "Организатор:" in result
        assert "Mentor" in result
        assert "Участники:" in result
        assert "Student" in result

    def test_multiple_participants(self):
        p1 = make_user(telegram_id=200, name="Alice", username="alice")
        p2 = make_user(telegram_id=300, name="Bob", username="bob")
        p3 = make_user(telegram_id=400, name="Charlie", username="charlie")
        meeting = make_meeting(
            participants=[_mentor(), p1, p2, p3],
            mentor_telegram_id=MENTOR_ID,
        )
        result = _format_meetings([meeting], mentor_tg_ids={MENTOR_ID})
        assert "Alice" in result
        assert "Bob" in result
        assert "Charlie" in result
        assert "Участники:" in result

    def test_no_participants(self):
        meeting = make_meeting(
            participants=[_mentor()],
            mentor_telegram_id=MENTOR_ID,
        )
        result = _format_meetings([meeting], mentor_tg_ids={MENTOR_ID})
        assert "Участники: —" in result

    def test_shows_creator(self):
        meeting = make_meeting(
            participants=[_mentor()],
            mentor_telegram_id=MENTOR_ID,
        )
        result = _format_meetings([meeting], mentor_tg_ids={MENTOR_ID})
        assert "Организатор:" in result
        assert "Mentor" in result

    def test_empty_list(self):
        result = _format_meetings([], mentor_tg_ids={MENTOR_ID})
        assert "пуст" in result
