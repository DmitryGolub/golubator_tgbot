from src.bot.handlers.dynamic_survey import (
    _normalize_minutes_answer,
    _text_question_keyboard,
)


DURATION_CONFIG = {
    "input_type": "positive_int_minutes",
    "min": 1,
    "max": 1440,
    "quick_options": [
        {"value": "15", "label": "15 мин"},
        {"value": "30", "label": "30 мин"},
        {"value": "45", "label": "45 мин"},
        {"value": "60", "label": "60 мин"},
    ],
}


def test_text_question_with_quick_options_builds_buttons():
    keyboard = _text_question_keyboard(
        {
            "question_type": "text",
            "config": DURATION_CONFIG,
        }
    )

    rows = keyboard.inline_keyboard
    labels = [button.text for row in rows for button in row]

    assert labels[:4] == ["15 мин", "30 мин", "45 мин", "60 мин"]
    assert labels[-1] == "❌ Отмена"


def test_manual_minutes_answer_valid():
    assert _normalize_minutes_answer("73", DURATION_CONFIG) == "73"


def test_manual_minutes_answer_invalid():
    assert _normalize_minutes_answer("0", DURATION_CONFIG) is None
    assert _normalize_minutes_answer("-1", DURATION_CONFIG) is None
    assert _normalize_minutes_answer("abc", DURATION_CONFIG) is None
    assert _normalize_minutes_answer("1441", DURATION_CONFIG) is None
