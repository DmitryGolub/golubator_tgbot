from src.utils.escape import e


def truncate_button_text(text: str, max_len: int = 30) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def format_username_display(
    username: str | None, *, prefix: str = " @", short: bool = False
) -> str:
    if username:
        return f"{prefix}{e(username)}"
    return " [Нет ТГ]" if short else " [Нет телеграмма]"


def format_user_label(
    name: str, username: str | None, *, prefix: str = "", max_len: int = 30
) -> str:
    if username:
        full = f"{prefix}{name} @{username}"
        if len(full) <= max_len:
            return full
    name_only = f"{prefix}{name} [Нет ТГ]"
    return truncate_button_text(name_only, max_len)
