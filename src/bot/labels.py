"""Human-readable labels for enums and internal field names.

Single source of truth for user-facing Russian strings that map from raw
enum values, SQL column names, or other technical identifiers.
"""

DELAY_MODE_LABELS = {
    "after_trigger": "после срабатывания",
    "before_scheduled": "до запланированного времени",
}

REGULARITY_LABELS = {
    "day": "ежедневно",
    "week": "еженедельно",
    "fortnight": "раз в 2 недели",
    "month": "ежемесячно",
}

QUESTION_TYPE_LABELS = {
    "text": "Текстовый",
    "rating": "Оценка",
    "single_choice": "Один из списка",
    "multiple_choice": "Несколько из списка",
}

TEMPLATE_KIND_LABELS = {
    "survey": "Опрос",
    "broadcast": "Рассылка",
}

SESSION_STATUS_LABELS = {
    "pending": "Ожидает",
    "in_progress": "В процессе",
    "completed": "Завершена",
}

MEETING_FIELD_LABELS = {
    "meeting_link": "Ссылка",
    "scheduled_at": "Дата/время",
    "description": "Описание",
    "event_type": "Тип встречи",
    "topic": "Тема",
    "mentee_telegram_tag": "Участники",
}

COHORT_STATUS_LABELS = {
    "Greetings": "Приветствие",
    "Hold": "Холд",
    "Studying": "Обучение",
    "Search": "Поиск",
    "Offer": "Оффер",
}


def label(mapping: dict[str, str], value) -> str:
    """Return the human label for ``value`` (enum or str), fallback to raw."""
    if value is None:
        return "—"
    raw = value.value if hasattr(value, "value") else str(value)
    return mapping.get(raw, raw)
