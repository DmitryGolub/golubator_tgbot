import pytest
from datetime import datetime, timezone, timedelta

from src.bot.handlers.meeting import _parse_time, _parse_datetime, _to_utc_assuming_msk

MOSCOW_TZ = timezone(timedelta(hours=3))


class TestParseTime:
    @pytest.mark.parametrize(
        "value, expected",
        [
            ("1430", "14:30"),
            ("0900", "09:00"),
            ("0000", "00:00"),
            ("2359", "23:59"),
            ("14:30", "14:30"),
        ],
    )
    def test_valid(self, value, expected):
        assert _parse_time(value) == expected

    @pytest.mark.parametrize(
        "value",
        [
            "2500",
            "1460",
            "123",
            "12345",
            "",
            "abcd",
            None,
        ],
    )
    def test_invalid(self, value):
        assert _parse_time(value) is None


class TestParseDatetime:
    def test_iso_format(self):
        result = _parse_datetime("2026-03-23T14:30:00")
        assert result == datetime(2026, 3, 23, 14, 30, 0)

    def test_space_format(self):
        result = _parse_datetime("2026-03-23 14:30")
        assert result == datetime(2026, 3, 23, 14, 30)

    def test_compact_format(self):
        result = _parse_datetime("202603231430")
        assert result == datetime(2026, 3, 23, 14, 30)

    def test_iso_with_tz(self):
        result = _parse_datetime("2026-03-23T14:30:00+03:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_garbage_returns_none(self):
        assert _parse_datetime("not a date") is None

    def test_empty_string(self):
        assert _parse_datetime("") is None


class TestToUtcAssumingMsk:
    def test_none(self):
        assert _to_utc_assuming_msk(None) is None

    def test_naive_assumes_msk(self):
        naive = datetime(2026, 3, 23, 15, 0, 0)
        result = _to_utc_assuming_msk(naive)
        assert result.tzinfo == timezone.utc
        assert result.hour == 12  # 15:00 MSK = 12:00 UTC

    def test_aware_converts(self):
        aware = datetime(2026, 3, 23, 15, 0, 0, tzinfo=timezone.utc)
        result = _to_utc_assuming_msk(aware)
        assert result.tzinfo == timezone.utc
        assert result.hour == 15  # already UTC
