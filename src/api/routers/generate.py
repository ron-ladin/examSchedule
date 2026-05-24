from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.api.adapters.in_memory_data_provider import InMemoryDataProvider
from src.api.config import settings
from src.api.exceptions.domain import BusyError, DomainValidationError
from src.api.schemas.generate import (
    GenerateRequestDTO,
    GenerateResponseDTO,
    GenerationStatusDTO,
)
from src.api.session.models import SessionData
from src.api.session.store import get_session
from src.engine.app_controller import AppController
from src.engine.schedule_generator import ScheduleGenerator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generate"])

_SESSION_ID = "default"


def _sync_generate(session: SessionData, programs: list[str]) -> None:
    """Run AppController synchronously — called inside asyncio.to_thread."""
    courses = session.courses
    periods = session.periods

    data_provider = InMemoryDataProvider(
        courses=courses,
        periods=periods,
        selected_programs=programs,
    )
    generator = ScheduleGenerator(conflict_strategy=ExactConflictStrategy())
    controller = AppController(
        data_provider=data_provider,
        exporter=session.exporter,
        generator=generator,
        selected_programs=programs,
    )
    controller.run()


async def _run_generation(session: SessionData, programs: list[str]) -> None:
    """Background coroutine: run generation with a hard timeout (SCRUM-123).

    On TimeoutError: asyncio cancels this coroutine, but the underlying thread
    spawned by to_thread cannot be forcibly stopped — it will run to completion
    in the background. The exporter lock prevents corruption; stale add() calls
    after timeout are bounded by MAX_SCHEDULES and are discarded on next reset().
    """
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_sync_generate, session, programs),
            timeout=settings.generation_timeout_seconds,
        )
        session.generation_status = "completed"
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

    background_tasks.add_task(_run_generation, session, body.programs)

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
