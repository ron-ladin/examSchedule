from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ScheduleDTO(BaseModel):
    """A single generated schedule entry."""

    id: int
    data: dict[str, Any]


class PaginatedScheduleDTO(BaseModel):
    """One page of generated schedules."""

    page: int
    size: int
    items: list[ScheduleDTO]
