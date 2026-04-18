"""Unit tests for src.services.caldav.parser."""

from __future__ import annotations

from datetime import datetime, timezone

from src.services.caldav.parser import extract_meeting_id, parse_vevent


def _wrap(vevent_body: str) -> bytes:
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//test//test//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"{vevent_body}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    ).encode("utf-8")


def test_parse_minimal_event():
    ics = _wrap(
        "UID:golubator-meeting-42@example.com\r\n"
        "DTSTART:20260501T120000Z\r\n"
        "DTSTAMP:20260418T100000Z\r\n"
        "LAST-MODIFIED:20260418T120000Z\r\n"
        "SEQUENCE:3\r\n"
        "STATUS:CONFIRMED\r\n"
        "SUMMARY:Test"
    )
    parsed = parse_vevent(ics)
    assert parsed is not None
    assert parsed.uid == "golubator-meeting-42@example.com"
    assert parsed.dtstart == datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    assert parsed.last_modified == datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
    assert parsed.sequence == 3
    assert parsed.status == "CONFIRMED"
    assert parsed.has_rrule is False


def test_parse_status_cancelled():
    ics = _wrap(
        "UID:golubator-meeting-1@x\r\n"
        "DTSTART:20260501T120000Z\r\n"
        "DTSTAMP:20260418T100000Z\r\n"
        "STATUS:CANCELLED"
    )
    parsed = parse_vevent(ics)
    assert parsed is not None
    assert parsed.status == "CANCELLED"


def test_parse_with_rrule():
    ics = _wrap(
        "UID:golubator-meeting-1@x\r\n"
        "DTSTART:20260501T120000Z\r\n"
        "DTSTAMP:20260418T100000Z\r\n"
        "RRULE:FREQ=WEEKLY;COUNT=4"
    )
    parsed = parse_vevent(ics)
    assert parsed is not None
    assert parsed.has_rrule is True


def test_parse_dtstart_date_value_returns_none_dtstart():
    # All-day events use DATE, not DATE-TIME. We treat dtstart as None.
    ics = _wrap(
        "UID:golubator-meeting-1@x\r\n"
        "DTSTART;VALUE=DATE:20260501\r\n"
        "DTSTAMP:20260418T100000Z"
    )
    parsed = parse_vevent(ics)
    assert parsed is not None
    assert parsed.dtstart is None


def test_parse_naive_datetime_treated_as_utc(caplog):
    ics = _wrap(
        "UID:golubator-meeting-1@x\r\n"
        "DTSTART:20260501T120000\r\n"
        "DTSTAMP:20260418T100000Z"
    )
    with caplog.at_level("WARNING"):
        parsed = parse_vevent(ics)
    assert parsed is not None
    assert parsed.dtstart == datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    assert any("naive datetime" in rec.message for rec in caplog.records)


def test_parse_falls_back_to_dtstamp_when_no_last_modified():
    ics = _wrap(
        "UID:golubator-meeting-1@x\r\n"
        "DTSTART:20260501T120000Z\r\n"
        "DTSTAMP:20260418T100000Z"
    )
    parsed = parse_vevent(ics)
    assert parsed is not None
    assert parsed.last_modified == datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc)


def test_parse_empty_returns_none():
    assert parse_vevent(b"") is None


def test_parse_non_vevent_returns_none():
    ics = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//x//y//EN\r\n"
        "BEGIN:VTODO\r\nUID:t1\r\nEND:VTODO\r\nEND:VCALENDAR\r\n"
    ).encode("utf-8")
    assert parse_vevent(ics) is None


def test_extract_meeting_id():
    assert extract_meeting_id("golubator-meeting-42@example.com") == 42
    assert extract_meeting_id("golubator-meeting-7@x") == 7
    assert extract_meeting_id("foreign-uid@x") is None
    assert extract_meeting_id("") is None
    assert extract_meeting_id("golubator-meeting-abc@x") is None


def test_parse_vtimezone_msk_converted_to_utc():
    ics = (
        b"BEGIN:VCALENDAR\r\n"
        b"VERSION:2.0\r\n"
        b"PRODID:-//x//y//EN\r\n"
        b"BEGIN:VTIMEZONE\r\n"
        b"TZID:Europe/Moscow\r\n"
        b"BEGIN:STANDARD\r\n"
        b"DTSTART:19700101T000000\r\n"
        b"TZOFFSETFROM:+0300\r\n"
        b"TZOFFSETTO:+0300\r\n"
        b"TZNAME:MSK\r\n"
        b"END:STANDARD\r\n"
        b"END:VTIMEZONE\r\n"
        b"BEGIN:VEVENT\r\n"
        b"UID:golubator-meeting-1@x\r\n"
        b"DTSTART;TZID=Europe/Moscow:20260501T150000\r\n"
        b"DTSTAMP:20260418T100000Z\r\n"
        b"END:VEVENT\r\n"
        b"END:VCALENDAR\r\n"
    )
    parsed = parse_vevent(ics)
    assert parsed is not None
    assert parsed.dtstart == datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
