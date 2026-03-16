from typing import Any, Literal

from pydantic import BaseModel


class FeedbackExportResponse(BaseModel):
    status: Literal["dry_run", "exported"]
    rows_count: int
    headers: list[str] | None = None
    sample_rows: list[dict[str, Any]] | None = None
    target_file_path: str | None = None
    sheet_name: str | None = None
