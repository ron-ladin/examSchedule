from __future__ import annotations

# Integration tests for the generation router (SCRUM-127).
# Covers: double-trigger guard (409 BUSY), no-data guard (400),
# 202 acceptance, generation timeout path, and status polling.

from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from src.api.main import create_app


# ---------------------------------------------------------------------------
# Shared fixture: fresh app per test so sessions never bleed across tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app) as tc:
        yield tc, app


@pytest.fixture()
def client_with_data():
    """App whose session already has courses and periods loaded."""
    app = create_app()
    with TestClient(app) as tc:
        session = app.state.session_store.get_or_create()
        # Non-empty lists satisfy the guard; _sync_generate is always patched
        session.courses = ["course_stub"]   # type: ignore[list-item]
        session.periods = ["period_stub"]   # type: ignore[list-item]
        yield tc, app


# ---------------------------------------------------------------------------
# Status endpoint — idle on startup
# ---------------------------------------------------------------------------

def test_status_returns_idle_initially(client) -> None:
    tc, _ = client
    response = tc.get("/api/generate/status")
    assert response.status_code == 200
    assert response.json()["status"] == "idle"


def test_status_returns_zero_schedules_initially(client) -> None:
    tc, _ = client
    body = tc.get("/api/generate/status").json()
    assert body["total_schedules"] == 0


def test_status_returns_no_error_initially(client) -> None:
    tc, _ = client
    body = tc.get("/api/generate/status").json()
    assert body["error"] is None


# ---------------------------------------------------------------------------
# Guard: no data uploaded → 400
# ---------------------------------------------------------------------------

def test_generate_returns_400_when_no_courses_or_periods(client) -> None:
    tc, _ = client
    response = tc.post("/api/schedules/generate", json={"programs": []})
    assert response.status_code == 400


def test_generate_400_body_has_validation_error_code(client) -> None:
    tc, _ = client
    body = tc.post("/api/schedules/generate", json={"programs": []}).json()
    assert body["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Guard: already running → 409 BUSY (SCRUM-124/131)
# ---------------------------------------------------------------------------

def test_generate_returns_409_when_already_running(client_with_data) -> None:
    tc, app = client_with_data
    app.state.session_store.get_or_create().generation_status = "running"
    response = tc.post("/api/schedules/generate", json={"programs": []})
    assert response.status_code == 409


def test_generate_409_body_has_busy_code(client_with_data) -> None:
    tc, app = client_with_data
    app.state.session_store.get_or_create().generation_status = "running"
    body = tc.post("/api/schedules/generate", json={"programs": []}).json()
    assert body["code"] == "BUSY"


def test_generate_second_call_blocked_while_running(client_with_data) -> None:
    tc, app = client_with_data
    # Simulate mid-run state
    app.state.session_store.get_or_create().generation_status = "running"
    first = tc.post("/api/schedules/generate", json={})
    second = tc.post("/api/schedules/generate", json={})
    assert first.status_code == 409
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# Happy path: 202 acceptance (SCRUM-123)
# ---------------------------------------------------------------------------

def test_generate_returns_202_when_data_present(client_with_data) -> None:
    tc, _ = client_with_data
    with patch("src.api.routers.generate._sync_generate", return_value=[]):
        response = tc.post("/api/schedules/generate", json={"programs": []})
    assert response.status_code == 202


def test_generate_202_body_has_message(client_with_data) -> None:
    tc, _ = client_with_data
    with patch("src.api.routers.generate._sync_generate", return_value=[]):
        body = tc.post("/api/schedules/generate", json={"programs": []}).json()
    assert "message" in body


def test_generate_202_body_has_session_id(client_with_data) -> None:
    tc, _ = client_with_data
    with patch("src.api.routers.generate._sync_generate", return_value=[]):
        body = tc.post("/api/schedules/generate", json={"programs": []}).json()
    assert "session_id" in body


def test_generate_status_is_completed_after_successful_run(client_with_data) -> None:
    tc, _ = client_with_data
    with patch("src.api.routers.generate._sync_generate", return_value=[]):
        tc.post("/api/schedules/generate", json={"programs": []})
    status = tc.get("/api/generate/status").json()
    assert status["status"] == "completed"


# ---------------------------------------------------------------------------
# Timeout path (SCRUM-123): TimeoutError in background → status = "failed"
# Mock _run_generation directly to avoid unawaited-coroutine warnings from
# patching asyncio.wait_for while to_thread coroutine is already constructed.
# ---------------------------------------------------------------------------

def _make_timeout_mock(settings_timeout: int) -> AsyncMock:
    """Return an AsyncMock that simulates the timeout branch of _run_generation."""
    from src.api.config import settings

    async def _timeout_run(session, programs, executor):
        session.generation_status = "failed"
        session.generation_error = (
            f"Generation exceeded the {settings.generation_timeout_seconds}s timeout"
        )

    return AsyncMock(side_effect=_timeout_run)


def test_generate_status_is_failed_on_timeout(client_with_data) -> None:
    tc, _ = client_with_data
    with patch("src.api.routers.generate._run_generation", new=_make_timeout_mock(120)):
        tc.post("/api/schedules/generate", json={"programs": []})
    status = tc.get("/api/generate/status").json()
    assert status["status"] == "failed"


def test_generate_error_message_mentions_timeout(client_with_data) -> None:
    tc, _ = client_with_data
    with patch("src.api.routers.generate._run_generation", new=_make_timeout_mock(120)):
        tc.post("/api/schedules/generate", json={"programs": []})
    error = tc.get("/api/generate/status").json()["error"]
    assert error is not None
    assert "timeout" in error.lower()


def test_generate_can_restart_after_timeout(client_with_data) -> None:
    tc, _ = client_with_data
    # First call times out
    with patch("src.api.routers.generate._run_generation", new=_make_timeout_mock(120)):
        tc.post("/api/schedules/generate", json={})
    # Status is "failed", not "running" — a second call must be accepted
    with patch("src.api.routers.generate._sync_generate", return_value=[]):
        retry = tc.post("/api/schedules/generate", json={})
    assert retry.status_code == 202


# ---------------------------------------------------------------------------
# Unexpected error path: exception in sync thread → status = "failed"
# ---------------------------------------------------------------------------

def test_generate_status_is_failed_on_exception(client_with_data) -> None:
    tc, _ = client_with_data
    with patch(
        "src.api.routers.generate._sync_generate",
        side_effect=RuntimeError("boom"),
    ):
        tc.post("/api/schedules/generate", json={"programs": []})
    status = tc.get("/api/generate/status").json()
    assert status["status"] == "failed"


def test_generate_error_message_contains_exception_text(client_with_data) -> None:
    tc, _ = client_with_data
    with patch(
        "src.api.routers.generate._sync_generate",
        side_effect=RuntimeError("boom"),
    ):
        tc.post("/api/schedules/generate", json={"programs": []})
    error = tc.get("/api/generate/status").json()["error"]
    assert "boom" in error


# ---------------------------------------------------------------------------
# DTO validation (SCRUM-127 review feedback)
# ---------------------------------------------------------------------------

def test_generate_rejects_more_than_five_programs(client_with_data) -> None:
    tc, _ = client_with_data
    with patch("src.api.routers.generate._sync_generate", return_value=[]):
        response = tc.post(
            "/api/schedules/generate",
            json={"programs": ["11111", "22222", "33333", "44444", "55555", "66666"]},
        )
    assert response.status_code == 422


def test_generate_rejects_duplicate_programs(client_with_data) -> None:
    tc, _ = client_with_data
    with patch("src.api.routers.generate._sync_generate", return_value=[]):
        response = tc.post(
            "/api/schedules/generate",
            json={"programs": ["11111", "11111"]},
        )
    assert response.status_code == 422


def test_generate_rejects_non_five_digit_program_id(client_with_data) -> None:
    tc, _ = client_with_data
    with patch("src.api.routers.generate._sync_generate", return_value=[]):
        response = tc.post(
            "/api/schedules/generate",
            json={"programs": ["ABC", "1234"]},
        )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Real end-to-end: no mocking of _sync_generate — catches ExactConflictStrategy
# argument bugs and any wiring issues that mocked tests cannot detect.
# ---------------------------------------------------------------------------

def test_real_generation_end_to_end_produces_schedules(client) -> None:
    from datetime import date

    from src.domain.course import Course
    from src.domain.course_offering import CourseOffering
    from src.domain.exam_period import ExamPeriod

    tc, app = client
    program_id = "83101"

    session = app.state.session_store.get_or_create()
    session.courses = [
        Course(
            id="10001",
            name="Calculus",
            instructor="Prof. A",
            evaluation_type="Exam",
            offerings=[
                CourseOffering(
                    program_id=program_id,
                    year=1,
                    semester="SPRI",
                    requirement="Obligatory",
                )
            ],
        )
    ]
    session.periods = [
        ExamPeriod(
            semester="SPRI",
            moed="Aleph",
            date_ranges=[(date(2026, 1, 5), date(2026, 1, 9))],
        )
    ]

    tc.post("/api/schedules/generate", json={"programs": [program_id]})

    status = tc.get("/api/generate/status").json()
    assert status["status"] == "completed"
    assert status["total_schedules"] > 0
