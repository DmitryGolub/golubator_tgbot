"""Shared button helpers for E2E tests."""


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
