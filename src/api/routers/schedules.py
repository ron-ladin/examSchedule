from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from src.api.schemas.schedule import PaginatedScheduleDTO, ScheduleDTO
from src.api.session.models import SessionData
from src.api.session.store import get_session

router = APIRouter()

# Maximum page size the client may request in a single call.
# Matches PaginatedExporter.PAGE_SIZE default (50) but lets callers
# request up to 200 at once without risking unbounded memory reads.
_MAX_PAGE_SIZE: int = 200


@router.get("/api/schedules", response_model=PaginatedScheduleDTO, tags=["schedules"])
def get_schedules(
    response: Response,
    page: int = Query(default=0, ge=0, description="0-indexed page number"),
    size: int = Query(
        default=50,
        ge=1,
        le=_MAX_PAGE_SIZE,
        description="Number of schedules per page (1–200)",
    ),
    session: SessionData = Depends(get_session),
) -> PaginatedScheduleDTO:
    """Return one page of generated schedules (SCRUM-77).

    Pagination is 0-indexed: page=0 is the first page, page=1 is the second, etc.
    The response always carries an ``X-Total-Count`` header with the total number
    of schedules currently stored, allowing the frontend to render pagination controls
    without a separate request.

    An out-of-range page (beyond the last item) returns 200 with an empty items list —
    this is the standard pagination convention and avoids spurious 404 errors when the
    frontend overshoots during rapid polling.

    The ``id`` field on each ScheduleDTO is the global index of that schedule
    (``page * size + position``), so it is stable and unique across pages.
    """
    total = session.exporter.total()
    raw_items = session.exporter.get_page(page, size)

    items = [
        ScheduleDTO(id=page * size + i, data=item)
        for i, item in enumerate(raw_items)
    ]

    # X-Total-Count is already exposed in CORS (see main.py expose_headers).
    # The frontend uses it to compute total pages and render pagination controls.
    response.headers["X-Total-Count"] = str(total)

    return PaginatedScheduleDTO(page=page, size=size, items=items)
