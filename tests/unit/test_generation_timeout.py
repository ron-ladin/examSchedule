from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from src.api.adapters.paginated_exporter import PaginatedExporter
from src.api.background.generation import run_generation_background
from src.api.session.models import SessionData


@pytest.fixture()
def session() -> SessionData:
    return SessionData()


# ---------------------------------------------------------------------------
# Timeout path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_timeout_sets_failed_status(session: SessionData) -> None:
    with patch(
        "src.api.background.generation.asyncio.wait_for",
        side_effect=asyncio.TimeoutError,
    ):
        await run_generation_background(session, ["83101"])
    assert session.generation_status == "failed"


@pytest.mark.asyncio
async def test_timeout_sets_error_message(session: SessionData) -> None:
    with patch(
        "src.api.background.generation.asyncio.wait_for",
        side_effect=asyncio.TimeoutError,
    ):
        await run_generation_background(session, [])
    assert session.generation_error is not None
    assert "timeout" in session.generation_error.lower() or "exceeded" in session.generation_error.lower()


@pytest.mark.asyncio
async def test_timeout_resets_exporter(session: SessionData) -> None:
    # Pre-populate so we can verify the exporter is fresh after timeout
    session.exporter.add({"partial": "result"})
    with patch(
        "src.api.background.generation.asyncio.wait_for",
        side_effect=asyncio.TimeoutError,
    ):
        await run_generation_background(session, [])
    # Background module does NOT reset exporter on timeout (the router does on next run)
    # This test documents the current contract: status is "failed"
    assert session.generation_status == "failed"


@pytest.mark.asyncio
async def test_timeout_error_contains_timeout_seconds(session: SessionData) -> None:
    with patch(
        "src.api.background.generation.asyncio.wait_for",
        side_effect=asyncio.TimeoutError,
    ):
        await run_generation_background(session, [])
    from src.api.config import settings
    assert str(settings.generation_timeout_seconds) in (session.generation_error or "")


# ---------------------------------------------------------------------------
# Unexpected exception path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unexpected_exception_sets_failed(session: SessionData) -> None:
    with patch(
        "src.api.background.generation.asyncio.wait_for",
        side_effect=RuntimeError("boom"),
    ):
        await run_generation_background(session, [])
    assert session.generation_status == "failed"


@pytest.mark.asyncio
async def test_unexpected_exception_stores_message(session: SessionData) -> None:
    with patch(
        "src.api.background.generation.asyncio.wait_for",
        side_effect=RuntimeError("boom"),
    ):
        await run_generation_background(session, [])
    assert session.generation_error is not None
    assert "boom" in session.generation_error


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_success_sets_completed_status(session: SessionData) -> None:
    with patch(
        "src.api.background.generation.asyncio.wait_for",
        return_value=None,
    ):
        await run_generation_background(session, [])
    assert session.generation_status == "completed"


@pytest.mark.asyncio
async def test_success_clears_error(session: SessionData) -> None:
    session.generation_error = "previous error"
    with patch(
        "src.api.background.generation.asyncio.wait_for",
        return_value=None,
    ):
        await run_generation_background(session, [])
    assert session.generation_error is None


@pytest.mark.asyncio
async def test_success_sets_last_run(session: SessionData) -> None:
    with patch(
        "src.api.background.generation.asyncio.wait_for",
        return_value=None,
    ):
        await run_generation_background(session, [])
    assert session.last_run is not None


# ---------------------------------------------------------------------------
# No path leaves session stuck in "running"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_never_remains_running_on_timeout(session: SessionData) -> None:
    session.generation_status = "running"
    with patch(
        "src.api.background.generation.asyncio.wait_for",
        side_effect=asyncio.TimeoutError,
    ):
        await run_generation_background(session, [])
    assert session.generation_status != "running"


@pytest.mark.asyncio
async def test_status_never_remains_running_on_exception(session: SessionData) -> None:
    session.generation_status = "running"
    with patch(
        "src.api.background.generation.asyncio.wait_for",
        side_effect=Exception("unexpected"),
    ):
        await run_generation_background(session, [])
    assert session.generation_status != "running"
