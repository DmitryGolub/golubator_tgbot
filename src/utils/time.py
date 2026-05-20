from datetime import datetime, timezone


def is_past(scheduled_at: datetime | None) -> bool:
    """Return True when the datetime is on or before the current UTC moment."""
    if scheduled_at is None:
        return False
    return scheduled_at <= datetime.now(timezone.utc)
