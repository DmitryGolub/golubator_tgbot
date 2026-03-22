import zipfile
from datetime import datetime, timezone
from io import BytesIO

import pytest

from src.services.yandex_sheets import (
    _cell_xml,
    _column_letter,
    _normalize_sheet_name,
    build_xlsx_bytes,
)


class TestNormalizeSheetName:
    def test_removes_special_chars(self):
        assert _normalize_sheet_name("My[Sheet]:1") == "MySheet1"

    def test_truncates_to_31(self):
        assert len(_normalize_sheet_name("a" * 50)) == 31

    def test_strips_quotes(self):
        assert _normalize_sheet_name("'test'") == "test"

    def test_fallback_on_empty(self):
        assert _normalize_sheet_name("") == "feedback_export"

    def test_fallback_on_only_special(self):
        assert _normalize_sheet_name("[]:*?/\\") == "feedback_export"


class TestColumnLetter:
    @pytest.mark.parametrize(
        "index, expected",
        [
            (1, "A"),
            (2, "B"),
            (26, "Z"),
            (27, "AA"),
            (28, "AB"),
            (52, "AZ"),
            (53, "BA"),
            (702, "ZZ"),
            (703, "AAA"),
        ],
    )
    def test_column_letter(self, index, expected):
        assert _column_letter(index) == expected


class TestCellXml:
    def test_none_returns_empty(self):
        assert _cell_xml(1, 1, None) == ""

    def test_empty_string_returns_empty(self):
        assert _cell_xml(1, 1, "") == ""

    def test_integer(self):
        result = _cell_xml(1, 1, 42)
        assert '<c r="A1"><v>42</v></c>' == result

    def test_float(self):
        result = _cell_xml(1, 1, 3.14)
        assert '<c r="A1"><v>3.14</v></c>' == result

    def test_bool_true(self):
        result = _cell_xml(1, 1, True)
        assert '<c r="A1" t="b"><v>1</v></c>' == result

    def test_bool_false(self):
        result = _cell_xml(1, 1, False)
        assert '<c r="A1" t="b"><v>0</v></c>' == result

    def test_string(self):
        result = _cell_xml(1, 1, "hello")
        assert 't="inlineStr"' in result
        assert "<t>hello</t>" in result

    def test_string_with_html(self):
        result = _cell_xml(1, 1, "<b>test</b>")
        assert "&lt;b&gt;test&lt;/b&gt;" in result

    def test_datetime(self):
        dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _cell_xml(1, 1, dt)
        assert "2026-01-15" in result
        assert 't="inlineStr"' in result


class TestBuildXlsxBytes:
    def test_returns_valid_zip(self):
        data = build_xlsx_bytes(
            sheet_name="test",
            headers=["Name", "Age"],
            rows=[["Alice", 30], ["Bob", 25]],
        )
        assert isinstance(data, bytes)
        zf = zipfile.ZipFile(BytesIO(data))
        names = zf.namelist()
        assert "xl/worksheets/sheet1.xml" in names
        assert "xl/workbook.xml" in names

    def test_sheet_contains_data(self):
        data = build_xlsx_bytes(
            sheet_name="test",
            headers=["Col1"],
            rows=[["value1"]],
        )
        zf = zipfile.ZipFile(BytesIO(data))
        sheet_xml = zf.read("xl/worksheets/sheet1.xml").decode()
        assert "Col1" in sheet_xml
        assert "value1" in sheet_xml

    def test_empty_rows(self):
        data = build_xlsx_bytes(
            sheet_name="test",
            headers=["A", "B"],
            rows=[],
        )
        zf = zipfile.ZipFile(BytesIO(data))
        assert "xl/worksheets/sheet1.xml" in zf.namelist()
