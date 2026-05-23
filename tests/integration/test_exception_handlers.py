from __future__ import annotations

# Integration tests for the global exception handler (SCRUM-65).
# A minimal FastAPI app with probe routes is used to trigger each exception type
# and verify the correct HTTP status code, response body, and log output.

import logging

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from src.api.exceptions.domain import (
    BusyError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from src.api.exceptions.handlers import register_handlers


# ---------------------------------------------------------------------------
# Shared fixture: a minimal app with one probe route per exception type
# raise_server_exceptions=False makes TestClient return the HTTP response
# instead of re-raising the server-side exception in the test process.
# ---------------------------------------------------------------------------

@pytest.fixture()
def client() -> TestClient:
    # Build a minimal app that exposes probe routes for each exception type
    app = FastAPI()
    register_handlers(app)

    @app.get("/raise/not-found")
    def raise_not_found() -> None:
        raise NotFoundError("course 42 not found")

    @app.get("/raise/conflict")
    def raise_conflict() -> None:
        raise ConflictError("courses already uploaded")

    @app.get("/raise/validation")
    def raise_validation() -> None:
        raise DomainValidationError("program ID must be 5 digits")

    @app.get("/raise/busy")
    def raise_busy() -> None:
        raise BusyError("generation already running")

    @app.get("/raise/unhandled")
    def raise_unhandled() -> None:
        raise RuntimeError("something broke internally")

    @app.get("/raise/empty-message")
    def raise_empty() -> None:
        raise NotFoundError("")

    @app.get("/ok")
    def ok_route() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Sanity: each domain exception maps to the correct HTTP status code
# ---------------------------------------------------------------------------

def test_not_found_returns_404(client: TestClient) -> None:
    # NotFoundError must produce a 404 response
    response = client.get("/raise/not-found")
    assert response.status_code == 404


def test_conflict_returns_409(client: TestClient) -> None:
    # ConflictError must produce a 409 response
    response = client.get("/raise/conflict")
    assert response.status_code == 409


def test_validation_returns_400(client: TestClient) -> None:
    # DomainValidationError must produce a 400 response
    response = client.get("/raise/validation")
    assert response.status_code == 400


def test_busy_returns_409(client: TestClient) -> None:
    # BusyError must produce a 409 response
    response = client.get("/raise/busy")
    assert response.status_code == 409


def test_unhandled_returns_500(client: TestClient) -> None:
    # Any unregistered exception type must produce a 500 response
    response = client.get("/raise/unhandled")
    assert response.status_code == 500


# ---------------------------------------------------------------------------
# Sanity: response body contains 'detail' and correct 'code' field
# ---------------------------------------------------------------------------

def test_not_found_body_has_not_found_code(client: TestClient) -> None:
    # 404 response body must contain code="NOT_FOUND"
    body = client.get("/raise/not-found").json()
    assert body["code"] == "NOT_FOUND"


def test_conflict_body_has_conflict_code(client: TestClient) -> None:
    # 409 conflict response body must contain code="CONFLICT"
    body = client.get("/raise/conflict").json()
    assert body["code"] == "CONFLICT"


def test_validation_body_has_validation_error_code(client: TestClient) -> None:
    # 400 response body must contain code="VALIDATION_ERROR"
    body = client.get("/raise/validation").json()
    assert body["code"] == "VALIDATION_ERROR"


def test_busy_body_has_busy_code(client: TestClient) -> None:
    # 409 busy response body must contain code="BUSY"
    body = client.get("/raise/busy").json()
    assert body["code"] == "BUSY"


def test_unhandled_body_has_internal_error_code(client: TestClient) -> None:
    # 500 response body must contain code="INTERNAL_ERROR"
    body = client.get("/raise/unhandled").json()
    assert body["code"] == "INTERNAL_ERROR"


def test_response_body_contains_detail_key(client: TestClient) -> None:
    # Every error response must include a 'detail' key
    body = client.get("/raise/not-found").json()
    assert "detail" in body


# ---------------------------------------------------------------------------
# Sanity: 500 body says "Internal server error", never leaks internal message
# ---------------------------------------------------------------------------

def test_500_detail_is_generic_message(client: TestClient) -> None:
    # The 500 detail must be the safe generic string, not the exception's own message
    body = client.get("/raise/unhandled").json()
    assert body["detail"] == "Internal server error"


def test_500_does_not_leak_runtime_error_message(client: TestClient) -> None:
    # The word "broke" from the RuntimeError must NOT appear in the response body
    body = client.get("/raise/unhandled").json()
    assert "broke" not in body["detail"]


# ---------------------------------------------------------------------------
# Sanity: domain exception message appears verbatim in 'detail'
# ---------------------------------------------------------------------------

def test_not_found_detail_matches_exception_message(client: TestClient) -> None:
    # The exact exception message is forwarded as detail in the 404 response
    body = client.get("/raise/not-found").json()
    assert body["detail"] == "course 42 not found"


def test_conflict_detail_matches_exception_message(client: TestClient) -> None:
    # The exact ConflictError message is forwarded verbatim in the 409 response
    body = client.get("/raise/conflict").json()
    assert body["detail"] == "courses already uploaded"


def test_validation_detail_matches_exception_message(client: TestClient) -> None:
    # The exact DomainValidationError message is forwarded verbatim in the 400 response
    body = client.get("/raise/validation").json()
    assert body["detail"] == "program ID must be 5 digits"


def test_busy_detail_matches_exception_message(client: TestClient) -> None:
    # The exact BusyError message is forwarded verbatim in the 409 response
    body = client.get("/raise/busy").json()
    assert body["detail"] == "generation already running"


# ---------------------------------------------------------------------------
# Boundary: both ConflictError and BusyError map to HTTP 409
# ---------------------------------------------------------------------------

def test_conflict_and_busy_both_return_409(client: TestClient) -> None:
    # ConflictError and BusyError must both produce 409 (not a typo — verify both)
    assert client.get("/raise/conflict").status_code == 409
    assert client.get("/raise/busy").status_code == 409


# ---------------------------------------------------------------------------
# Boundary: empty string message does not crash — returns the right status
# ---------------------------------------------------------------------------

def test_empty_message_not_found_returns_404(client: TestClient) -> None:
    # NotFoundError("") must still produce 404, not 500
    response = client.get("/raise/empty-message")
    assert response.status_code == 404


def test_empty_message_not_found_detail_is_empty_string(client: TestClient) -> None:
    # NotFoundError("") must produce detail="" without crashing
    body = client.get("/raise/empty-message").json()
    assert body["detail"] == ""


# ---------------------------------------------------------------------------
# Edge: register_handlers smoke test — can be called on a fresh app without error
# ---------------------------------------------------------------------------

def test_register_handlers_smoke() -> None:
    # register_handlers() must not raise when called on a bare FastAPI instance
    app = FastAPI()
    register_handlers(app)  # should complete without error


# ---------------------------------------------------------------------------
# Edge: normal routes still work after handlers are registered
# ---------------------------------------------------------------------------

def test_happy_path_still_works(client: TestClient) -> None:
    # Registering exception handlers must not interfere with successful routes
    response = client.get("/ok")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Edge: unhandled exception is logged at ERROR level with traceback info
# ---------------------------------------------------------------------------

def test_unhandled_exception_is_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    # RuntimeError on /raise/unhandled must produce an ERROR-level log entry
    with caplog.at_level(logging.ERROR, logger="src.api.exceptions.handlers"):
        client.get("/raise/unhandled")
    assert any(record.levelno >= logging.ERROR for record in caplog.records)


def test_unhandled_exception_log_contains_path(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    # The error log entry must mention the request path so it is easy to diagnose
    with caplog.at_level(logging.ERROR, logger="src.api.exceptions.handlers"):
        client.get("/raise/unhandled")
    combined = " ".join(record.getMessage() for record in caplog.records)
    assert "/raise/unhandled" in combined
