"""Helpers to decide who can confirm a meeting proposal.

A user can confirm only if they are a real, registered Telegram user:
`telegram_id > 0` (not a placeholder) and `registered_at IS NOT NULL`
(has run `/start`). Placeholder and unregistered users are auto-accepted
by DAO, so they never block a proposal.
"""

from __future__ import annotations

from typing import Any


def is_confirmable(user: Any) -> bool:
    telegram_id = getattr(user, "telegram_id", None)
    if telegram_id is None or telegram_id <= 0:
        return False
    return getattr(user, "registered_at", None) is not None
