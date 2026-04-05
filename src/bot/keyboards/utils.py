def truncate_button_text(text: str, max_len: int = 30) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def format_user_label(
    name: str, username: str | None, *, prefix: str = "", max_len: int = 30
) -> str:
    if username:
        full = f"{prefix}{name} @{username}"
        if len(full) <= max_len:
            return full
    name_only = f"{prefix}{name}"
    return truncate_button_text(name_only, max_len)
