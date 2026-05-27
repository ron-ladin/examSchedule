from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from src.api.adapters.paginated_exporter import PaginatedExporter
from src.domain.course import Course
from src.domain.exam_period import ExamPeriod

# The four states a generation job can be in
GenerationStatus = Literal["idle", "running", "completed", "failed"]


@dataclass
class SessionData:
    """All mutable state for one user session.

    v1.0 has no auth — the whole server shares one SessionData.

    Contract for data-upload endpoints (SCRUM-67/68):
    Store parsed domain objects here — NOT raw dicts.
    The generate endpoint (SCRUM-75) passes these directly to AppController
    via InMemoryDataProvider, which expects typed Course/ExamPeriod objects.
    """

    # Populated by POST /api/data/courses/upload (SCRUM-67)
    courses: list[Course] = field(default_factory=list)
    # Populated by POST /api/data/periods/upload (SCRUM-68)
    periods: list[ExamPeriod] = field(default_factory=list)

    # Results store — filled by the background generator (SCRUM-75)
    exporter: PaginatedExporter = field(default_factory=PaginatedExporter)

    # Generation job state — read by GET /api/generate/status (SCRUM-76)
    generation_status: GenerationStatus = "idle"
    generation_error: str | None = None

    # Set on successful generation completion; surfaced by GET /api/data/status
    last_run: datetime | None = None

    # Period keys excluded from generation; managed by PATCH /api/periods/{key}/exclusions
    excluded_periods: set[str] = field(default_factory=set)
