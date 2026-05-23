from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CourseDTO(BaseModel):
    """Represents a single course in a programme."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    instructor: str
    programme: str | None = None


class ProgrammeDTO(BaseModel):
    """Represents a study programme and its associated courses."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    courses: list[CourseDTO] = []
