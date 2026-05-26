from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.api.adapters.in_memory_data_provider import InMemoryDataProvider
from src.api.config import settings
from src.api.session.models import SessionData
from src.engine.app_controller import AppController
from src.engine.schedule_generator import ScheduleGenerator

logger = logging.getLogger(__name__)


def _sync_generate(session: SessionData, programs: list[str]) -> None:
    """Run AppController synchronously — called inside asyncio.to_thread."""
    data_provider = InMemoryDataProvider(
        courses=session.courses,
        periods=session.periods,
        selected_programs=programs,
    )
    generator = ScheduleGenerator(
        conflict_strategy=ExactConflictStrategy(selected_programs=programs)
    )
    controller = AppController(
        data_provider=data_provider,
        exporter=session.exporter,
        generator=generator,
        selected_programs=programs,
    )
    controller.run()


async def run_generation_background(session: SessionData, programs: list[str]) -> None:
    """Background coroutine: run generation with a hard timeout (SCRUM-130).

    On TimeoutError: asyncio cancels this coroutine, but the underlying thread
    spawned by to_thread cannot be forcibly stopped — it will run to completion
    in the background. The exporter lock prevents corruption; stale add() calls
    after timeout are bounded by MAX_SCHEDULES and are discarded on next reset().
    """
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_sync_generate, session, programs),
            timeout=float(settings.generation_timeout_seconds),
        )
        session.generation_status = "completed"
        session.generation_error = None
        session.last_run = datetime.now(tz=timezone.utc)
        logger.info("Generation completed — %d schedules", session.exporter.total())
    except asyncio.TimeoutError:
        session.generation_status = "failed"
        session.generation_error = (
            f"Generation exceeded the {settings.generation_timeout_seconds}s timeout"
        )
        logger.warning(
            "Generation timed out after %ss", settings.generation_timeout_seconds
        )
    except Exception as exc:
        session.generation_status = "failed"
        session.generation_error = str(exc)
        logger.exception("Generation failed: %s", exc)
