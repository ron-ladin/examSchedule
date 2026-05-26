from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile

from src.api.adapters.json_cache_adapter import JsonCacheAdapter
from src.api.exceptions.domain import DomainValidationError
from src.api.schemas.data import DataStatusDTO, UploadResponseDTO
from src.api.session.models import SessionData
from src.api.session.store import get_session
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod

router = APIRouter()
_cache = JsonCacheAdapter()


# ---------------------------------------------------------------------------
# Upload endpoints
# ---------------------------------------------------------------------------

@router.post("/courses/upload", response_model=UploadResponseDTO)
@router.patch("/courses/upload", response_model=UploadResponseDTO)
async def upload_courses(
    file: UploadFile = File(...),
    mode: str = Query(default="replace", pattern="^(replace|append)$"),
    session: SessionData = Depends(get_session),
) -> UploadResponseDTO:
    """Accept a JSON file of course objects.

    mode=replace clears session.courses then loads the new list.
    mode=append extends session.courses with the new list.
    """
    contents = await file.read()
    parsed = _parse_courses(contents, file.content_type or "")
    if mode == "replace":
        session.courses = parsed
    else:
        session.courses.extend(parsed)
    await asyncio.to_thread(_cache.save, session.courses, session.periods)
    return UploadResponseDTO(count=len(session.courses), mode=mode)


@router.post("/periods/upload", response_model=UploadResponseDTO)
@router.patch("/periods/upload", response_model=UploadResponseDTO)
async def upload_periods(
    file: UploadFile = File(...),
    mode: str = Query(default="replace", pattern="^(replace|append)$"),
    session: SessionData = Depends(get_session),
) -> UploadResponseDTO:
    """Accept a JSON file of exam period objects.

    mode=replace clears session.periods then loads the new list.
    mode=append extends session.periods with the new list.
    """
    contents = await file.read()
    parsed = _parse_periods(contents, file.content_type or "")
    if mode == "replace":
        session.periods = parsed
    else:
        session.periods.extend(parsed)
    await asyncio.to_thread(_cache.save, session.courses, session.periods)
    return UploadResponseDTO(count=len(session.periods), mode=mode)


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------

@router.get("/status", response_model=DataStatusDTO)
async def data_status(
    session: SessionData = Depends(get_session),
) -> DataStatusDTO:
    """Return counts and freshness state of the uploaded data (SCRUM-69)."""
    cached: dict[str, Any] = await asyncio.to_thread(_cache.load)
    return DataStatusDTO(
        course_count=len(session.courses),
        period_count=len(session.periods),
        cache_fresh=bool(cached),
        last_run=session.last_run,
    )


# ---------------------------------------------------------------------------
# Private parsers
# ---------------------------------------------------------------------------

def _parse_courses(contents: bytes, content_type: str) -> list[Course]:
    """Parse uploaded bytes into Course domain objects (JSON format)."""
    try:
        raw: Any = json.loads(contents.decode("utf-8"))
        if not isinstance(raw, list):
            raise DomainValidationError("Expected a JSON array of course objects")
        result: list[Course] = []
        for item in raw:
            offerings = [
                CourseOffering(
                    program_id=str(o["program_id"]),
                    year=int(o["year"]),
                    semester=str(o["semester"]),
                    requirement=str(o["requirement"]),
                )
                for o in item.get("offerings", [])
            ]
            result.append(
                Course(
                    id=str(item["id"]),
                    name=str(item["name"]),
                    instructor=str(item["instructor"]),
                    evaluation_type=str(item["evaluation_type"]),
                    offerings=offerings,
                )
            )
        return result
    except DomainValidationError:
        raise
    except Exception as exc:
        raise DomainValidationError(f"Invalid course data: {exc}") from exc


def _parse_periods(contents: bytes, content_type: str) -> list[ExamPeriod]:
    """Parse uploaded bytes into ExamPeriod domain objects (JSON format).

    Expected date format: DD-MM-YYYY (matches the project file format standard).
    """
    try:
        raw: Any = json.loads(contents.decode("utf-8"))
        if not isinstance(raw, list):
            raise DomainValidationError("Expected a JSON array of period objects")
        result: list[ExamPeriod] = []
        for item in raw:
            date_ranges = [
                (
                    datetime.strptime(str(r[0]), "%d-%m-%Y").date(),
                    datetime.strptime(str(r[1]), "%d-%m-%Y").date(),
                )
                for r in item.get("date_ranges", [])
            ]
            excluded_dates = {
                datetime.strptime(str(d), "%d-%m-%Y").date()
                for d in item.get("excluded_dates", [])
            }
            result.append(
                ExamPeriod(
                    semester=str(item["semester"]),
                    moed=str(item["moed"]),
                    date_ranges=date_ranges,
                    excluded_dates=excluded_dates,
                )
            )
        return result
    except DomainValidationError:
        raise
    except Exception as exc:
        raise DomainValidationError(f"Invalid period data: {exc}") from exc
