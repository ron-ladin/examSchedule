from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile

from src.adapters.readers.course_file_reader import CourseFileReader
from src.adapters.readers.exam_period_file_reader import ExamPeriodFileReader
from src.api.adapters.json_cache_adapter import JsonCacheAdapter
from src.api.exceptions.domain import DomainValidationError
from src.api.schemas.data import DataStatusDTO, UploadResponseDTO
from src.api.session.models import SessionData
from src.api.session.store import get_session
from src.domain.course import Course
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
    mode: Literal["replace", "append"] = Query(default="replace"),
    session: SessionData = Depends(get_session),
) -> UploadResponseDTO:
    """Accept a courses.txt file ($$$$-delimited format).

    mode=replace clears session.courses then loads the new list.
    mode=append extends session.courses with the new list.
    """
    contents = await file.read()
    parsed = _parse_courses(contents)
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
    mode: Literal["replace", "append"] = Query(default="replace"),
    session: SessionData = Depends(get_session),
) -> UploadResponseDTO:
    """Accept a dates.txt file ($$$$-delimited format).

    mode=replace clears session.periods then loads the new list.
    mode=append extends session.periods with the new list.
    Raises 400 if any period key in the upload already exists in the session.
    """
    contents = await file.read()
    parsed = _parse_periods(contents)
    if mode == "replace":
        session.periods = parsed
    else:
        existing_keys = {p.get_key() for p in session.periods}
        for p in parsed:
            if p.get_key() in existing_keys:
                raise DomainValidationError(
                    f"Period '{p.get_key()}' already exists in the session"
                )
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

def _parse_courses(contents: bytes) -> list[Course]:
    """Parse uploaded bytes into Course domain objects using CourseFileReader."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(contents)
        tmp = Path(f.name)
    try:
        return CourseFileReader(tmp).read()
    except ValueError as exc:
        raise DomainValidationError(str(exc)) from exc
    except Exception as exc:
        raise DomainValidationError(f"Invalid course data: {exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)


def _parse_periods(contents: bytes) -> list[ExamPeriod]:
    """Parse uploaded bytes into ExamPeriod domain objects using ExamPeriodFileReader."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(contents)
        tmp = Path(f.name)
    try:
        return ExamPeriodFileReader(tmp).read()
    except ValueError as exc:
        raise DomainValidationError(str(exc)) from exc
    except Exception as exc:
        raise DomainValidationError(f"Invalid period data: {exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)
