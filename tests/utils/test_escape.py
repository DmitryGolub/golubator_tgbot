import pytest

from src.utils.escape import e


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, ""),
        ("", ""),
        ("hello", "hello"),
        ("<b>bold</b>", "&lt;b&gt;bold&lt;/b&gt;"),
        ("a & b", "a &amp; b"),
        ('quote "test"', "quote &quot;test&quot;"),
        (123, "123"),
        (0, "0"),
        (False, "False"),
    ],
)
def test_escape(value, expected):
    assert e(value) == expected
