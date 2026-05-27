from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.exceptions.domain import DomainValidationError, NotFoundError
from src.api.schemas.period import ExamPeriodDTO, ExclusionDTO, PeriodRangeDTO
from src.api.session.models import SessionData
from src.api.session.store import get_session
from src.domain.exam_period import ExamPeriod

router = APIRouter()


@router.patch("/{key}/exclusions", response_model=ExamPeriodDTO)
async def toggle_exclusions(
    key: str,
    body: ExclusionDTO,
    session: SessionData = Depends(get_session),
) -> ExamPeriodDTO:
    """Toggle the excluded flag on an exam period (SCRUM-73).

    excluded=true removes the period from schedule generation.
    excluded=false re-enables it.
    Raises 404 if no period with the given key exists.

    Note: period keys contain spaces (e.g. "FALL - Aleph").  Callers must
    percent-encode them: ``/api/periods/FALL%20-%20Aleph/exclusions``.
    """
    period = _find_period(session, key)
    if body.excluded:
        session.excluded_periods.add(key)
    else:
        session.excluded_periods.discard(key)
    return ExamPeriodDTO.from_domain(period, excluded=key in session.excluded_periods)


@router.patch("/{key}/range", response_model=ExamPeriodDTO)
async def update_range(
    key: str,
    body: PeriodRangeDTO,
    session: SessionData = Depends(get_session),
) -> ExamPeriodDTO:
    """Update the date range of an exam period (SCRUM-74).

    Raises 400 if start >= end.
    Raises 404 if no period with the given key exists.
    """
    if body.start >= body.end:
        raise DomainValidationError("start date must be strictly before end date")
    period = _find_period(session, key)
    # v1.0: intentionally replaces ALL date_ranges with the single range from the
    # request body.  ExamPeriod supports multiple ranges internally, but the v1.0
    # UI exposes only one range per period, so a full replacement is correct here.
    # When multi-range editing is added (v2+), change this to a targeted update.
    period.date_ranges = [(body.start, body.end)]
    return ExamPeriodDTO.from_domain(period, excluded=key in session.excluded_periods)


def _find_period(session: SessionData, key: str) -> ExamPeriod:
    """Return the ExamPeriod matching key, or raise NotFoundError."""
    for p in session.periods:
        if p.get_key() == key:
            return p
    raise NotFoundError(f"Period '{key}' not found")
