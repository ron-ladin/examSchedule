from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from src.api.adapters.paginated_exporter import PAGE_SIZE
from src.api.schemas.schedule import PaginatedScheduleDTO, ScheduleDTO
from src.api.session.models import SessionData
from src.api.session.store import get_session

router = APIRouter()

# Maximum page size the client may request in a single call.
# Expressed as a multiple of PAGE_SIZE so that changing the default page size
# automatically adjusts the cap — the two constants stay in sync.
_MAX_PAGE_SIZE: int = PAGE_SIZE * 4  # 200 when PAGE_SIZE = 50


@router.get("/api/schedules", response_model=PaginatedScheduleDTO, tags=["schedules"])
async def get_schedules(
    response: Response,
    page: int = Query(default=0, ge=0, description="0-indexed page number"),
    size: int = Query(
        default=PAGE_SIZE,
        ge=1,
        le=_MAX_PAGE_SIZE,
        description=f"Number of schedules per page (1–{_MAX_PAGE_SIZE})",
    ),
    session: SessionData = Depends(get_session),
) -> PaginatedScheduleDTO:
    """Return one page of generated schedules (SCRUM-77).

    Pagination is 0-indexed: page=0 is the first page, page=1 is the second, etc.
    The response always carries an ``X-Total-Count`` header with the total number
    of schedules currently stored, allowing the frontend to render pagination
    controls without a separate request.

    The ``total`` and the ``items`` list are read in a single atomic lock
    acquisition (via ``get_page_with_total``), so the header and the body are
    always consistent — even when a new generation job calls ``reset()``
    concurrently.

    An out-of-range page (beyond the last item) returns 200 with an empty items
    list — this is the standard pagination convention and avoids spurious 404
    errors when the frontend overshoots during rapid polling.

    The ``id`` field on each ScheduleDTO is the item's absolute position in the
    exporter's storage list (``page * size + i``).  It is stable across different
    page sizes within the same generation, but resets to zero after each new
    ``/api/schedules/generate`` call — do not persist or cache it across runs.
    """
    raw_items, total = session.exporter.get_page_with_total(page, size)

    start = page * size
    items = [
        ScheduleDTO(id=start + i, data=item)
        for i, item in enumerate(raw_items)
    ]

    # X-Total-Count is already exposed in CORS (see main.py expose_headers).
    # The frontend uses it to compute total pages and render pagination controls.
    response.headers["X-Total-Count"] = str(total)

    return PaginatedScheduleDTO(page=page, size=size, items=items)
