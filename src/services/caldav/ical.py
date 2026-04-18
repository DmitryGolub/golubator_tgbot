"""Build a VCALENDAR/VEVENT payload for CalDAV PUT.

Only the minimum set of fields is produced:
  - UID (deterministic, `golubator-meeting-{id}@{hostname}`)
  - SUMMARY (`"Созвон с <имя партнёра(ов)>"`)
  - DTSTART / DTEND (DTEND = DTSTART + 30m, UTC Z-form without VTIMEZONE)
  - DTSTAMP / CREATED / LAST-MODIFIED
  - SEQUENCE (server-incremented per-update)
  - STATUS: TENTATIVE (pending confirmation) or CONFIRMED
  - TRANSP: OPAQUE

`description`, meeting link and any other Meeting fields are intentionally
excluded per product requirement.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from icalendar import Calendar, Event

PRODID = "-//golubator//caldav//RU"
DEFAULT_DURATION = timedelta(minutes=30)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def build_vevent(
    *,
    uid: str,
    summary: str,
    start: datetime,
    duration: timedelta = DEFAULT_DURATION,
    sequence: int,
    tentative: bool,
    created_at: datetime,
    updated_at: datetime,
) -> bytes:
    """Return a serialized VCALENDAR (bytes, CRLF) containing a single VEVENT."""
    start_utc = _to_utc(start)
    end_utc = start_utc + duration
    created_utc = _to_utc(created_at)
    updated_utc = _to_utc(updated_at)
    now_utc = datetime.now(timezone.utc)

    cal = Calendar()
    cal.add("prodid", PRODID)
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")

    event = Event()
    event.add("uid", uid)
    event.add("summary", summary)
    event.add("dtstart", start_utc)
    event.add("dtend", end_utc)
    event.add("dtstamp", now_utc)
    event.add("created", created_utc)
    event.add("last-modified", updated_utc)
    event.add("sequence", int(sequence))
    event.add("status", "TENTATIVE" if tentative else "CONFIRMED")
    event.add("transp", "OPAQUE")
    cal.add_component(event)

    return cal.to_ical()
