from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.api.exceptions.domain import DomainValidationError, NotFoundError
from src.api.schemas.programme import CourseDetailDTO, ProgrammeSummaryDTO
from src.api.session.models import SessionData
from src.api.session.store import get_session
from src.domain.semester import normalize_semester

router = APIRouter()

# Requirement strings as they come out of CourseFileReader normalisation.
_REQUIREMENT_MAP: dict[str, str] = {
    "obligatory": "Obligatory",
    "elective": "Elective",
}


def _normalize_requirement(raw: str) -> str:
    """Return canonical Obligatory/Elective regardless of source casing."""
    canonical = _REQUIREMENT_MAP.get(raw.strip().lower())
    if canonical is None:
        raise ValueError(f"Unknown requirement value: {raw!r}")
    return canonical


@router.get("", response_model=list[ProgrammeSummaryDTO])
async def list_programmes(
    session: SessionData = Depends(get_session),
) -> list[ProgrammeSummaryDTO]:
    """Return all unique programmes found in the uploaded courses (SCRUM-70).

    A programme appears once per unique program_id across all course offerings.
    The name is the program_id — no separate programme names file exists in v1.0.
    Returns an empty list if no courses have been uploaded yet.
    """
    seen: dict[str, ProgrammeSummaryDTO] = {}
    for course in session.courses:
        for offering in course.offerings:
            if offering.program_id not in seen:
                seen[offering.program_id] = ProgrammeSummaryDTO(
                    id=offering.program_id,
                    name=offering.program_id,
                )
    return sorted(seen.values(), key=lambda p: p.id)


@router.get("/{programme_id}/courses", response_model=list[CourseDetailDTO])
async def list_programme_courses(
    programme_id: str,
    session: SessionData = Depends(get_session),
    year: int | None = Query(default=None, description="Filter by study year (e.g. 1, 2, 3)"),
    semester: str | None = Query(default=None, description="Filter by semester (e.g. FALL, SPRI, SUMM)"),
) -> list[CourseDetailDTO]:
    """Return courses for a programme, optionally filtered by year and/or semester (SCRUM-71, §2.3.2).

    Semester values are normalised via normalize_semester() so 'SPRING' and 'SPRI' both work.
    Returns 400 if semester is not a recognised value.
    Returns 404 only if the programme_id is not found at all.
    Returns 200 [] if the programme exists but no offerings match the active filters.
    """
    # Validate and normalise the semester query param before touching session data.
    normalised_semester: str | None = None
    if semester is not None:
        try:
            normalised_semester = normalize_semester(semester)
        except ValueError:
            raise DomainValidationError(f"Invalid semester: {semester!r}. Use FALL, SPRI, or SUMM.")

    # Two-pass: first check the programme exists, then collect filtered results.
    programme_exists = any(
        offering.program_id == programme_id
        for course in session.courses
        for offering in course.offerings
    )
    if not programme_exists:
        raise NotFoundError(f"Programme '{programme_id}' not found")

    results: list[CourseDetailDTO] = []
    for course in session.courses:
        for offering in course.offerings:
            if offering.program_id != programme_id:
                continue
            if year is not None and offering.year != year:
                continue
            if normalised_semester is not None and normalize_semester(offering.semester) != normalised_semester:
                continue
            results.append(CourseDetailDTO(
                id=course.id,
                name=course.name,
                instructor=course.instructor,
                evaluation_type=course.evaluation_type,
                year=offering.year,
                semester=offering.semester,
                requirement=_normalize_requirement(offering.requirement),  # type: ignore[arg-type]
            ))

    results.sort(key=lambda c: (c.year, c.semester, c.id))
    return results
