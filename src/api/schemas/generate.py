from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, field_validator

_PROGRAM_ID_RE = re.compile(r"^\d{5}$")


class GenerateRequestDTO(BaseModel):
    """Payload for POST /api/generate."""

    programs: list[str] = []

    @field_validator("programs")
    @classmethod
    def validate_programs(cls, v: list[str]) -> list[str]:
        if len(v) > 5:
            raise ValueError("Maximum 5 programs allowed")
        if len(v) != len(set(v)):
            raise ValueError("Duplicate program IDs are not allowed")
        for prog in v:
            if not _PROGRAM_ID_RE.match(prog):
                raise ValueError(f"Program ID must be exactly 5 digits, got: {prog!r}")
        return v


class GenerateResponseDTO(BaseModel):
    """Returned immediately when a generation job is accepted (202)."""

    message: str
    session_id: str


class GenerationStatusDTO(BaseModel):
    """Current state of the background schedule generation job."""

    status: Literal["idle", "running", "completed", "failed"]
    total_schedules: int = 0
    error: str | None = None
