from __future__ import annotations

from pydantic import BaseModel


class GenerateResponseDTO(BaseModel):
    """Returned immediately when a generation job is accepted (202)."""

    message: str
    session_id: str


class GenerationStatusDTO(BaseModel):
    """Current state of the background schedule generation job."""

    status: str  # "idle" | "running" | "done" | "failed"
    total_schedules: int = 0
    error: str | None = None
