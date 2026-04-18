"""Parse VEVENT bytes returned by CalDAV servers into a flat dataclass.

Handles only the fields needed for pull (UID, DTSTART, STATUS, LAST-MODIFIED,
SEQUENCE, RRULE detection). Anything else is intentionally ignored.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from icalendar import Calendar

logger = logging.getLogger(__name__)

_UID_RE = re.compile(r"^golubator-meeting-(\d+)@")


@dataclass(frozen=True)
class ParsedEvent:
    uid: str
    dtstart: Optional[datetime]
    status: Optional[str]
    last_modified: Optional[datetime]
    sequence: Optional[int]
    has_rrule: bool


def _to_utc(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        # All-day event — DTSTART is a DATE, not a datetime. Not ours.
        return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        logger.warning(
            "caldav.parser: naive datetime, assuming UTC",
            extra={"value": value.isoformat()},
        )
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_vevent(ics: bytes) -> Optional[ParsedEvent]:
    if not ics:
        return None
    try:
        cal = Calendar.from_ical(ics)
    except Exception as exc:
        logger.warning("caldav.parser: failed to parse iCalendar: %s", exc)
        return None

    for component in cal.walk("VEVENT"):
        uid_raw = component.get("uid")
        if uid_raw is None:
            continue
        uid = str(uid_raw).strip()
        if not uid:
            continue

        dtstart_prop = component.get("dtstart")
        dtstart = _to_utc(dtstart_prop.dt) if dtstart_prop is not None else None

        status_prop = component.get("status")
        status = str(status_prop).strip().upper() if status_prop is not None else None

        last_mod_prop = component.get("last-modified") or component.get("dtstamp")
        last_modified = _to_utc(last_mod_prop.dt) if last_mod_prop is not None else None

        sequence_prop = component.get("sequence")
        sequence = None
        if sequence_prop is not None:
            try:
                sequence = int(sequence_prop)
            except (TypeError, ValueError):
                sequence = None

        has_rrule = (
            component.get("rrule") is not None or component.get("rdate") is not None
        )

        return ParsedEvent(
            uid=uid,
            dtstart=dtstart,
            status=status,
            last_modified=last_modified,
            sequence=sequence,
            has_rrule=has_rrule,
        )

    return None


def extract_meeting_id(uid: str) -> Optional[int]:
    if not uid:
        return None
    match = _UID_RE.match(uid)
    if match is None:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None
