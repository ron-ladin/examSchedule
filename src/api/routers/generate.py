from __future__ import annotations

import asyncio
import logging
from concurrent.futures import Executor
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.api.adapters.in_memory_data_provider import InMemoryDataProvider
from src.api.adapters.paginated_exporter import PaginatedExporter
from src.api.config import settings
from src.api.exceptions.domain import BusyError, DomainValidationError
from src.api.schemas.generate import (
    GenerateRequestDTO,
    GenerateResponseDTO,
    GenerationStatusDTO,
)
from src.api.session.models import SessionData
from src.api.session.store import get_session
from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.engine.app_controller import AppController
from src.engine.schedule_generator import ScheduleGenerator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generate"])

_SESSION_ID = "default"


def get_executor(request: Request) -> Executor:
    """FastAPI dependency — inject the process/thread executor from app state."""
    return request.app.state.executor


def _sync_generate(
    courses: list[Course],
    periods: list[ExamPeriod],
    excluded_periods: set[str],
    programs: list[str],
) -> list[Any]:
    """Run AppController in a worker (process or thread) and return all results.

    Pure function — no shared state, no side effects on the caller's objects.
    Must be a module-level function so ProcessPoolExecutor can pickle it.

    Returns a plain list[dict] so the result crosses the process boundary cleanly.
    """
    active_periods = [p for p in periods if p.get_key() not in excluded_periods]
    exporter = PaginatedExporter()
    data_provider = InMemoryDataProvider(
        courses=courses,
        periods=active_periods,
        selected_programs=programs,
    )
    generator = ScheduleGenerator(conflict_strategy=ExactConflictStrategy(selected_programs=programs))
    controller = AppController(
        data_provider=data_provider,
        exporter=exporter,
        generator=generator,
        selected_programs=programs,
    )
    controller.run()
    return exporter.get_all()


async def _run_generation(
    session: SessionData,
    programs: list[str],
    executor: Executor,
) -> None:
    """Background coroutine: run generation in a worker and load results back (SCRUM-123).

    Uses run_in_executor so the event loop stays responsive during generation.
    With ProcessPoolExecutor the heavy backtracking runs on a separate CPU core,
    bypassing the GIL. With ThreadPoolExecutor (tests) it runs in a thread.

    On TimeoutError: the worker cannot be forcibly stopped — it runs to completion
    in the background. Results that arrive after timeout are discarded because
    session.exporter.reset() is called before the next run.
    """
    loop = asyncio.get_running_loop()

    try:
        results: list[Any] = await asyncio.wait_for(
            loop.run_in_executor(
                executor,
                _sync_generate,
                session.courses,
                session.periods,
                session.excluded_periods,
                programs,
            ),
            timeout=settings.generation_timeout_seconds,
        )
        for item in results:
            session.exporter.add(item)
        session.generation_status = "completed"
        session.last_run = datetime.now(tz=timezone.utc)
        logger.info("Generation completed — %d schedules", session.exporter.total())
    except asyncio.TimeoutError:
        session.generation_status = "failed"
        session.generation_error = (
            f"Generation exceeded the {settings.generation_timeout_seconds}s timeout"
        )
        logger.warning("Generation timed out after %ss", settings.generation_timeout_seconds)
    except Exception as exc:
        session.generation_status = "failed"
        session.generation_error = str(exc)
        logger.exception("Generation failed: %s", exc)


@router.post("/api/schedules/generate", status_code=202, response_model=GenerateResponseDTO)
async def trigger_generation(
    body: GenerateRequestDTO,
    background_tasks: BackgroundTasks,
    session: SessionData = Depends(get_session),
    executor: Executor = Depends(get_executor),
) -> GenerateResponseDTO:
    """Start a background schedule generation job (SCRUM-75).

    Returns 409 if a job is already running — atomic guard (SCRUM-124/131).
    No await between the status check and the status write, so no event-loop
    context switch can slip a second request through.
    Returns 400 if no course or period data has been uploaded yet.
    Returns 202 immediately; poll GET /api/generate/status for progress.
    """
    if session.generation_status == "running":
        raise BusyError("A generation job is already running. Wait for it to finish.")

    if not session.courses or not session.periods:
        raise DomainValidationError(
            "No data loaded. Upload courses and periods before generating."
        )

    session.generation_status = "running"
    session.generation_error = None
    session.exporter.reset()

    background_tasks.add_task(_run_generation, session, body.programs, executor)

    return GenerateResponseDTO(
        message="Generation started",
        session_id=_SESSION_ID,
    )


@router.get("/api/generate/status", response_model=GenerationStatusDTO)
def get_status(session: SessionData = Depends(get_session)) -> GenerationStatusDTO:
    """Return current state of the generation job (SCRUM-76)."""
    return GenerationStatusDTO(
        status=session.generation_status,
        total_schedules=session.exporter.total(),
        error=session.generation_error,
    )
