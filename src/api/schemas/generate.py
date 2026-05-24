from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class GenerateRequestDTO(BaseModel):
    """Payload for POST /api/generate."""

    programs: list[str] = []


class GenerateResponseDTO(BaseModel):
    """Returned immediately when a generation job is accepted (202)."""

    message: str
    session_id: str


class GenerationStatusDTO(BaseModel):
    """Current state of the background schedule generation job."""

    status: Literal["idle", "running", "completed", "failed"]
    total_schedules: int = 0
    error: str | None = None
