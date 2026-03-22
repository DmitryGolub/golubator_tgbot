from src.utils.telegram import split_message


def test_short_message_returns_single_chunk():
    assert split_message("hello", max_len=100) == ["hello"]


def test_empty_string():
    assert split_message("") == [""]


def test_exact_max_len():
    text = "a" * 100
    assert split_message(text, max_len=100) == [text]


def test_split_on_newline():
    text = "first line\nsecond line"
    result = split_message(text, max_len=15)
    assert result == ["first line", "second line"]


def test_forced_split_without_newline():
    text = "a" * 25
    result = split_message(text, max_len=10)
    assert result == ["a" * 10, "a" * 10, "a" * 5]


def test_multiple_chunks_with_newlines():
    text = "aaa\nbbb\nccc\nddd"
    result = split_message(text, max_len=8)
    assert len(result) >= 2
    # All original content is preserved across chunks
    for chunk in result:
        assert len(chunk) <= 8


def test_newline_stripped_between_chunks():
    text = "abc\ndef"
    result = split_message(text, max_len=4)
    assert result[0] == "abc"
    assert result[1] == "def"
