"""Shared button helpers for E2E tests."""

from __future__ import annotations


def find_button(msg, data_prefix: str):
    """Find inline button by callback_data prefix."""
    if msg.reply_markup and hasattr(msg.reply_markup, "rows"):
        for row in msg.reply_markup.rows:
            for btn in row.buttons:
                if btn.data and btn.data.decode().startswith(data_prefix):
                    return btn
    return None


def get_buttons(msg) -> list:
    """Get all inline buttons from message."""
    buttons = []
    if msg.reply_markup and hasattr(msg.reply_markup, "rows"):
        for row in msg.reply_markup.rows:
            buttons.extend(row.buttons)
    return buttons


def button_labels(msg) -> list[tuple[str, str]]:
    """Return [(text, callback_data), ...] for debugging."""
    return [(b.text, b.data.decode() if b.data else "") for b in get_buttons(msg)]


async def find_button_paginated(client, msg, data_prefix: str, menu: str):
    """Find inline button by callback_data prefix, navigating pages if needed.

    Args:
        client: TelegramTestClient instance.
        msg: Current message with inline keyboard.
        data_prefix: Callback data prefix to search for.
        menu: Pagination menu name (e.g. "users", "mentors") used in page:menu:N callbacks.

    Returns:
        Tuple (button, message) where button was found, or (None, msg) if not found.
    """
    visited_pages: set[int] = set()
    current_msg = msg

    while True:
        btn = find_button(current_msg, data_prefix)
        if btn is not None:
            return btn, current_msg

        # Look for next-page button (→)
        next_btn = None
        current_page = 0
        for b in get_buttons(current_msg):
            if b.data:
                data = b.data.decode()
                # page:menu:N format
                if data.startswith(f"page:{menu}:"):
                    page_num = int(data.split(":")[-1])
                    if page_num not in visited_pages:
                        next_btn = b
                        current_page = page_num

        if next_btn is None:
            return None, current_msg

        visited_pages.add(current_page)
        current_msg = await client.click_button(
            current_msg, data=next_btn.data.decode()
        )

    return None, current_msg
