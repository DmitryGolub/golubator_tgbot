from types import SimpleNamespace

from src.bot.keyboards.meeting import meeting_participants_multiselect_keyboard


def _make_user(tid, name="User", username="user"):
    return SimpleNamespace(
        telegram_id=tid,
        name=name,
        username=username,
        doc_name=None,
        user=None,
    )


def _get_button_texts(kb):
    return [btn.text for row in kb.inline_keyboard for btn in row]


def _get_callback_data(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row]


class TestMultiselectKeyboard:
    def test_none_selected(self):
        users = [_make_user(1, "Alice", "alice"), _make_user(2, "Bob", "bob")]
        kb = meeting_participants_multiselect_keyboard(
            users, selected_ids=set(), show_all_button=True
        )
        texts = _get_button_texts(kb)
        assert any("Alice" in t and not t.startswith("✓") for t in texts)
        assert not any("Готово" in t for t in texts)
        assert any("Показать всех" in t for t in texts)

    def test_some_selected(self):
        users = [_make_user(1, "Alice", "alice"), _make_user(2, "Bob", "bob")]
        kb = meeting_participants_multiselect_keyboard(
            users, selected_ids={1}, show_all_button=True
        )
        texts = _get_button_texts(kb)
        assert any("✓" in t and "Alice" in t for t in texts)
        assert any("Готово (1)" in t for t in texts)

    def test_show_all_button_absent(self):
        users = [_make_user(1, "Alice", "alice")]
        kb = meeting_participants_multiselect_keyboard(
            users, selected_ids=set(), show_all_button=False
        )
        texts = _get_button_texts(kb)
        assert not any("Показать всех" in t for t in texts)

    def test_pagination(self):
        users = [_make_user(i, f"User{i}", f"user{i}") for i in range(10)]
        kb = meeting_participants_multiselect_keyboard(
            users, selected_ids={3, 7}, page=0, show_all_button=False
        )
        texts = _get_button_texts(kb)
        # Page 0 should show first 6 users, selected state preserved
        assert any("✓" in t and "User3" in t for t in texts)
        assert any("Готово (2)" in t for t in texts)
