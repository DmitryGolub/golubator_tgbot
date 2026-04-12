from collections.abc import Callable, Sequence
from typing import Any

# Each extractor returns a list of searchable string fields for an item.
SEARCH_EXTRACTORS: dict[str, Callable[[Any], list[str]]] = {
    "users": lambda u: [u.name or "", u.username or ""],
    "user_list": lambda u: [u.name or "", u.username or ""],
    "mentors": lambda u: [u.name or "", u.username or ""],
    "mentees": lambda m: [
        m.doc_name or "",
        (m.user.name if hasattr(m, "user") and m.user else "") or "",
        (m.user.username if hasattr(m, "user") and m.user else "") or "",
    ],
    "students": lambda s: [
        getattr(s, "doc_name", "") or "",
        (s.user.name if hasattr(s, "user") and s.user else "") or "",
        (s.user.username if hasattr(s, "user") and s.user else "") or "",
    ],
    "participants": lambda u: [
        getattr(u, "name", "") or "",
        getattr(u, "doc_name", "") or "",
        getattr(u, "username", "") or "",
        (u.user.name if hasattr(u, "user") and u.user else "") or "",
        (u.user.username if hasattr(u, "user") and u.user else "") or "",
    ],
    "mstats": lambda m: [
        m.name or "",
        (m.user.username if m.user and m.user.username else "") or "",
    ],
    "meetings": lambda m: [
        m.description or "",
        *[p.name or "" for p in (m.participants or [])],
    ],
    "past_meetings": lambda m: [
        m.description or "",
        *[p.name or "" for p in (m.participants or [])],
    ],
    "meeting_types": lambda item: [item[0] if isinstance(item, tuple) else str(item)],
    "cohorts": lambda item: [item[0] if isinstance(item, tuple) else str(item)],
    "channel_links": lambda link: [link.label or "", link.code or ""],
}


def filter_items(items: Sequence, query: str, menu: str) -> list:
    extractor = SEARCH_EXTRACTORS.get(menu)
    if not extractor or not query:
        return list(items)
    query_lower = query.lower()
    return [
        item
        for item in items
        if any(query_lower in field.lower() for field in extractor(item) if field)
    ]
