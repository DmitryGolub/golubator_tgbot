from datetime import datetime, time, timezone

from src.models.enums import Regularity
from src.tasks.trigger import _match_cron, _match_regularity, _should_fire_now
from tests.conftest import make_trigger_rule


class TestMatchCron:
    def test_every_day_at_nine(self):
        # 09:00 MSK = 06:00 UTC — cron expressions are interpreted in MSK
        dt = datetime(2026, 3, 23, 6, 0, tzinfo=timezone.utc)
        assert _match_cron("0 9 * * *", dt) is True

    def test_every_day_at_nine_wrong_hour(self):
        dt = datetime(2026, 3, 23, 10, 0, tzinfo=timezone.utc)
        assert _match_cron("0 9 * * *", dt) is False

    def test_every_15_minutes(self):
        for minute in (0, 15, 30, 45):
            dt = datetime(2026, 3, 23, 12, minute, tzinfo=timezone.utc)
            assert _match_cron("*/15 * * * *", dt) is True

    def test_wrong_field_count(self):
        dt = datetime(2026, 3, 23, 9, 0, tzinfo=timezone.utc)
        assert _match_cron("0 9 * *", dt) is False

    def test_specific_day_of_week(self):
        # 2026-03-23 06:00 UTC = 09:00 MSK, still Monday (isoweekday=1, %7=1)
        dt = datetime(2026, 3, 23, 6, 0, tzinfo=timezone.utc)
        assert _match_cron("0 9 * * 1", dt) is True
        assert _match_cron("0 9 * * 2", dt) is False


class TestMatchRegularity:
    def _rule(self, regularity, time_of_day=None):
        return make_trigger_rule(regularity=regularity, time_of_day=time_of_day)

    def test_day_at_default_time(self):
        # Default MSK 09:00 = 06:00 UTC
        now = datetime(2026, 3, 23, 6, 0, tzinfo=timezone.utc)
        assert _match_regularity(self._rule(Regularity.day), now) is True

    def test_day_wrong_time(self):
        now = datetime(2026, 3, 23, 10, 0, tzinfo=timezone.utc)
        assert _match_regularity(self._rule(Regularity.day), now) is False

    def test_day_custom_time(self):
        # 14:30 MSK = 11:30 UTC
        now = datetime(2026, 3, 23, 11, 30, tzinfo=timezone.utc)
        rule = self._rule(Regularity.day, time_of_day=time(14, 30))
        assert _match_regularity(rule, now) is True

    def test_week_monday(self):
        # 2026-03-23 06:00 UTC = 09:00 MSK Monday
        now = datetime(2026, 3, 23, 6, 0, tzinfo=timezone.utc)
        assert _match_regularity(self._rule(Regularity.week), now) is True

    def test_week_tuesday(self):
        # 2026-03-24 is Tuesday
        now = datetime(2026, 3, 24, 9, 0, tzinfo=timezone.utc)
        assert _match_regularity(self._rule(Regularity.week), now) is False

    def test_month_first_day(self):
        # 06:00 UTC = 09:00 MSK, still day 1
        now = datetime(2026, 3, 1, 6, 0, tzinfo=timezone.utc)
        assert _match_regularity(self._rule(Regularity.month), now) is True

    def test_month_not_first_day(self):
        now = datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc)
        assert _match_regularity(self._rule(Regularity.month), now) is False

    def test_fortnight_even_week_monday(self):
        # 2026-01-05 06:00 UTC = 09:00 MSK Monday, ISO week 2 (even)
        now = datetime(2026, 1, 5, 6, 0, tzinfo=timezone.utc)
        assert now.weekday() == 0
        assert now.isocalendar()[1] % 2 == 0
        assert _match_regularity(self._rule(Regularity.fortnight), now) is True

    def test_fortnight_odd_week_monday(self):
        now = datetime(2026, 1, 12, 9, 0, tzinfo=timezone.utc)  # week 3 (odd), Monday
        assert now.weekday() == 0
        assert now.isocalendar()[1] % 2 == 1
        assert _match_regularity(self._rule(Regularity.fortnight), now) is False


class TestShouldFireNow:
    def test_cron_expression_delegates(self):
        rule = make_trigger_rule(cron_expression="0 9 * * *")
        # 06:00 UTC = 09:00 MSK
        now = datetime(2026, 3, 23, 6, 0, tzinfo=timezone.utc)
        assert _should_fire_now(rule, now) is True

    def test_regularity_delegates(self):
        rule = make_trigger_rule(regularity=Regularity.day)
        # 06:00 UTC = 09:00 MSK (default fire time)
        now = datetime(2026, 3, 23, 6, 0, tzinfo=timezone.utc)
        assert _should_fire_now(rule, now) is True

    def test_neither_returns_false(self):
        rule = make_trigger_rule(cron_expression=None, regularity=None)
        now = datetime(2026, 3, 23, 9, 0, tzinfo=timezone.utc)
        assert _should_fire_now(rule, now) is False
