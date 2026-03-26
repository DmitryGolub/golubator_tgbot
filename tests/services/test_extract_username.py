from __future__ import annotations

import pytest

from src.services.notion_sync_v2 import _extract_username


@pytest.mark.parametrize(
    "text, expected",
    [
        ("@bebic3", "bebic3"),
        ("!@krutoi_paren / analyst", "krutoi_paren"),
        ("@User_123", "User_123"),
        ("Алексей Колесников", None),
        ("some text @hidden_nick more text", "hidden_nick"),
        (None, None),
        ("", None),
        ("@ab", None),  # too short (< 3 chars)
        ("@abc", "abc"),  # exactly 3 chars — valid
        ("no at sign here", None),
        ("@@double", "double"),
        ("@first @second", "first"),  # returns first match
    ],
)
def test_extract_username(text: str | None, expected: str | None) -> None:
    assert _extract_username(text) == expected
