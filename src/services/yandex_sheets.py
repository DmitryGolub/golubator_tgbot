import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Sequence
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)

CellValue = str | int | float | bool | datetime | None


class YandexSheetsError(RuntimeError):
    pass


class YandexSheetsConfigurationError(YandexSheetsError):
    pass


class YandexSheetsUploadError(YandexSheetsError):
    pass


def _normalize_sheet_name(sheet_name: str) -> str:
    cleaned = "".join(ch for ch in sheet_name if ch not in "[]:*?/\\")
    cleaned = cleaned.strip("'") or "feedback_export"
    return cleaned[:31]


def _column_letter(index: int) -> str:
    result = ""
    value = index
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _cell_xml(column_index: int, row_index: int, value: CellValue) -> str:
    cell_ref = f"{_column_letter(column_index)}{row_index}"
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        raw_value = "1" if value else "0"
        return f'<c r="{cell_ref}" t="b"><v>{raw_value}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{cell_ref}"><v>{value}</v></c>'
    if isinstance(value, datetime):
        value = _format_datetime(value)
    text = escape(str(value))
    return f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def build_xlsx_bytes(
    *,
    sheet_name: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[CellValue]],
) -> bytes:
    normalized_sheet_name = _normalize_sheet_name(sheet_name)
    worksheet_rows = [headers, *rows]

    sheet_rows_xml: list[str] = []
    for row_index, row in enumerate(worksheet_rows, start=1):
        cells_xml = "".join(
            _cell_xml(column_index, row_index, value)
            for column_index, value in enumerate(row, start=1)
        )
        sheet_rows_xml.append(f'<row r="{row_index}">{cells_xml}</row>')

    worksheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        f"{''.join(sheet_rows_xml)}"
        "</sheetData>"
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        f'<sheet name="{escape(normalized_sheet_name)}" sheetId="1" r:id="rId1"/>'
        "</sheets>"
        "</workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        "</Relationships>"
    )
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
        'Target="docProps/app.xml"/>'
        "</Relationships>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        "<cp:coreProperties "
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:creator>golubator_tgbot</dc:creator>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created_at}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created_at}</dcterms:modified>'
        "</cp:coreProperties>"
    )
    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>golubator_tgbot</Application>"
        "</Properties>"
    )

    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", root_rels_xml)
        archive.writestr("docProps/app.xml", app_xml)
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        archive.writestr("xl/styles.xml", styles_xml)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
    return buffer.getvalue()


@dataclass(frozen=True, slots=True)
class YandexSheetTarget:
    file_path: str
    sheet_name: str


class YandexSheetsWriter:
    def __init__(
        self,
        *,
        token: str | None = None,
        file_path: str | None = None,
        sheet_name: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._token = token or settings.YANDEX_SHEETS_TOKEN
        self._file_path = file_path or settings.YANDEX_SHEETS_FILE_PATH
        self._sheet_name = _normalize_sheet_name(
            sheet_name or settings.YANDEX_SHEETS_SHEET_NAME
        )
        self._base_url = (base_url or settings.YANDEX_SHEETS_BASE_URL).rstrip("/")
        self._timeout_seconds = (
            timeout_seconds or settings.YANDEX_SHEETS_TIMEOUT_SECONDS
        )

        if not self._token:
            raise YandexSheetsConfigurationError(
                "YANDEX_SHEETS_TOKEN is not configured"
            )
        if not self._file_path:
            raise YandexSheetsConfigurationError(
                "YANDEX_SHEETS_FILE_PATH is not configured"
            )

    @property
    def target(self) -> YandexSheetTarget:
        return YandexSheetTarget(
            file_path=self._file_path,
            sheet_name=self._sheet_name,
        )

    async def replace_sheet(
        self,
        *,
        headers: Sequence[str],
        rows: Sequence[Sequence[CellValue]],
    ) -> YandexSheetTarget:
        workbook = build_xlsx_bytes(
            sheet_name=self._sheet_name,
            headers=headers,
            rows=rows,
        )
        upload_url = await self._get_upload_url()
        await self._upload_bytes(upload_url, workbook)
        logger.info(
            "Feedback export uploaded to Yandex Documents: file_path=%s sheet=%s rows=%s",
            self._file_path,
            self._sheet_name,
            len(rows),
        )
        return self.target

    async def _get_upload_url(self) -> str:
        headers = {"Authorization": f"OAuth {self._token}"}
        params = {"path": self._file_path, "overwrite": "true"}
        url = f"{self._base_url}/resources/upload"

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.get(url, headers=headers, params=params)

        if response.status_code >= 400:
            raise YandexSheetsUploadError(
                f"Failed to get upload URL from Yandex Disk: {response.status_code} {response.text}"
            )

        payload = response.json()
        href = payload.get("href")
        if not href:
            raise YandexSheetsUploadError(
                "Yandex Disk upload URL response does not contain href"
            )
        return str(href)

    async def _upload_bytes(self, upload_url: str, content: bytes) -> None:
        headers = {
            "Content-Type": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        }
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.put(upload_url, headers=headers, content=content)

        if response.status_code >= 400:
            raise YandexSheetsUploadError(
                f"Failed to upload workbook to Yandex Disk: {response.status_code} {response.text}"
            )
