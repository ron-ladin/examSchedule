from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ProgrammeSummaryDTO(BaseModel):
    """One programme entry returned by GET /api/programmes (SCRUM-70)."""

    id: str
    name: str


class CourseDetailDTO(BaseModel):
    """One course entry returned by GET /api/programmes/{id}/courses (SCRUM-71)."""

    id: str
    name: str
    instructor: str
    evaluation_type: str
    year: int
    semester: str
    requirement: Literal["Obligatory", "Elective"]
