"""Unit tests for src.services.caldav.ical.build_vevent."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.services.caldav.ical import build_vevent


def _decode(ics: bytes) -> str:
    return ics.decode("utf-8")


UID = "golubator-meeting-42@caldav.example.com"
START = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
CREATED = datetime(2026, 4, 30, 10, 0, tzinfo=timezone.utc)
UPDATED = datetime(2026, 4, 30, 11, 0, tzinfo=timezone.utc)


def test_basic_fields_present():
    ics = _decode(
        build_vevent(
            uid=UID,
            summary="Созвон с Алексей",
            start=START,
            sequence=3,
            tentative=False,
            created_at=CREATED,
            updated_at=UPDATED,
        )
    )
    assert "BEGIN:VCALENDAR" in ics
    assert "BEGIN:VEVENT" in ics
    assert f"UID:{UID}" in ics
    assert "SUMMARY:Созвон с Алексей" in ics
    assert "DTSTART:20260501T120000Z" in ics
    assert "DTEND:20260501T123000Z" in ics  # +30m default
    assert "SEQUENCE:3" in ics
    assert "STATUS:CONFIRMED" in ics
    assert "TRANSP:OPAQUE" in ics


def test_tentative_status():
    ics = _decode(
        build_vevent(
            uid=UID,
            summary="Созвон",
            start=START,
            sequence=0,
            tentative=True,
            created_at=CREATED,
            updated_at=UPDATED,
        )
    )
    assert "STATUS:TENTATIVE" in ics
    assert "STATUS:CONFIRMED" not in ics


def test_custom_duration():
    ics = _decode(
        build_vevent(
            uid=UID,
            summary="Короткий",
            start=START,
            duration=timedelta(minutes=15),
            sequence=0,
            tentative=False,
            created_at=CREATED,
            updated_at=UPDATED,
        )
    )
    assert "DTSTART:20260501T120000Z" in ics
    assert "DTEND:20260501T121500Z" in ics


def test_summary_escapes_rfc_special_chars():
    # icalendar MUST escape `,` `;` `\\` per RFC 5545
    ics = _decode(
        build_vevent(
            uid=UID,
            summary="a, b; c\\d",
            start=START,
            sequence=0,
            tentative=False,
            created_at=CREATED,
            updated_at=UPDATED,
        )
    )
    # The escaped representation contains backslashes before `,` `;` `\`
    assert "SUMMARY:a\\, b\\; c\\\\d" in ics


def test_naive_datetime_treated_as_utc():
    naive = datetime(2026, 5, 1, 12, 0)
    ics = _decode(
        build_vevent(
            uid=UID,
            summary="x",
            start=naive,
            sequence=0,
            tentative=False,
            created_at=naive,
            updated_at=naive,
        )
    )
    assert "DTSTART:20260501T120000Z" in ics
