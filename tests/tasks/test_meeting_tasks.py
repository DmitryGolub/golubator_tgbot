from tests.conftest import make_meeting, make_user
from src.tasks.meeting import _split_participants


CREATOR_ID = 100
OTHER1_ID = 200
OTHER2_ID = 300
OTHER3_ID = 400


def _creator():
    return make_user(telegram_id=CREATOR_ID, name="Creator")


def _other(tid, name="Other"):
    return make_user(telegram_id=tid, name=name)


class TestSplitParticipants:
    def test_single_other(self):
        meeting = make_meeting(
            participants=[_creator(), _other(OTHER1_ID)],
            mentor_telegram_id=CREATOR_ID,
        )
        creator, others = _split_participants(meeting)
        assert creator is not None
        assert creator.telegram_id == CREATOR_ID
        assert len(others) == 1
        assert others[0].telegram_id == OTHER1_ID

    def test_multiple_others(self):
        meeting = make_meeting(
            participants=[
                _creator(),
                _other(OTHER1_ID),
                _other(OTHER2_ID),
                _other(OTHER3_ID),
            ],
            mentor_telegram_id=CREATOR_ID,
        )
        creator, others = _split_participants(meeting)
        assert creator is not None
        assert len(others) == 3
        assert {p.telegram_id for p in others} == {OTHER1_ID, OTHER2_ID, OTHER3_ID}

    def test_no_creator(self):
        meeting = make_meeting(
            participants=[_other(OTHER1_ID), _other(OTHER2_ID)],
            mentor_telegram_id=999,
        )
        creator, others = _split_participants(meeting)
        assert creator is None
        assert len(others) == 2

    def test_empty_participants(self):
        meeting = make_meeting(participants=[], mentor_telegram_id=CREATOR_ID)
        creator, others = _split_participants(meeting)
        assert creator is None
        assert others == []
