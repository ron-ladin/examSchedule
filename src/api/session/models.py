from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.api.adapters.paginated_exporter import PaginatedExporter

# The four states a generation job can be in
GenerationStatus = Literal["idle", "running", "completed", "failed"]


@dataclass
class SessionData:
    """All mutable state for one user session.

    v1.0 has no auth — the whole server shares one SessionData.
    Fields are intentionally coarse (list[Any]) because the typed DTOs
    are only built at generation time, not stored here.
    """

    # Raw uploaded data — populated by the data-upload endpoints (SCRUM-67/68)
    courses: list[Any] = field(default_factory=list)
    periods: list[Any] = field(default_factory=list)

    # Results store — filled by the background generator (SCRUM-75)
    exporter: PaginatedExporter = field(default_factory=PaginatedExporter)

    # Generation job state — read by GET /api/generate/status (SCRUM-76)
    generation_status: GenerationStatus = "idle"
    generation_error: str | None = None
