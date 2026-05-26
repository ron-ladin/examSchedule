from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends

# Re-exported so existing patches on src.api.routers.generate._run_generation still work.
# Tests that patch _sync_generate should target src.api.background.generation._sync_generate.
from src.api.background.generation import run_generation_background as _run_generation
from src.api.exceptions.domain import BusyError, DomainValidationError
from src.api.schemas.generate import (
    GenerateRequestDTO,
    GenerateResponseDTO,
    GenerationStatusDTO,
)
from src.api.session.models import SessionData
from src.api.session.store import get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generate"])

_SESSION_ID = "default"


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
