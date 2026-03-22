from html import escape as _escape


def e(value) -> str:
    """Escape user-provided value for safe use in HTML messages."""
    return _escape(str(value)) if value is not None else ""
