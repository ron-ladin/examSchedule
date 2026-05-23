from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UploadResponseDTO(BaseModel):
    """Returned after a successful course or period file upload."""

    count: int
    mode: str  # "replace" | "append"


class DataStatusDTO(BaseModel):
    """Current state of uploaded data and cache freshness."""

    course_count: int
    period_count: int
    cache_fresh: bool
    last_run: datetime | None = None
