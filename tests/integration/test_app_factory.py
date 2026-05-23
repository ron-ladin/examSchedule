from __future__ import annotations

# Integration tests for create_app() (SCRUM-59)
# HTTP-only tests use httpx.AsyncClient (ASGI transport, no lifespan).
# Tests that inspect app.state use starlette.testclient.TestClient, which
# sends the ASGI lifespan scope and therefore populates app.state correctly.

import pytest
import pytest_asyncio
from fastapi import Depends
from fastapi.routing import APIRouter
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from src.api.main import create_app
from src.api.session.models import SessionData
from src.api.session.store import SessionStore, get_session


# ---------------------------------------------------------------------------
# Shared async client fixture (HTTP-only — no lifespan required)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def client() -> AsyncClient:
    # Create a fresh app for each test so sessions never bleed across tests
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as ac:
        yield ac  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    # GET /health must return HTTP 200
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_returns_status_ok(client: AsyncClient) -> None:
    # GET /health response body must be {"status": "ok"}
    response = await client.get("/health")
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# CORS — allowed origin
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cors_default_origin_allowed(client: AsyncClient) -> None:
    # A request from the configured frontend origin gets the ACAO header back
    response = await client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


@pytest.mark.asyncio
async def test_cors_preflight_allowed_origin(client: AsyncClient) -> None:
    # OPTIONS preflight from the frontend origin must succeed with CORS headers
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers


@pytest.mark.asyncio
async def test_cors_unknown_origin_blocked(client: AsyncClient) -> None:
    # A request from an unlisted origin must NOT receive the ACAO header
    response = await client.get("/health", headers={"Origin": "http://evil.com"})
    acao = response.headers.get("access-control-allow-origin", "")
    # FastAPI/Starlette either omits the header or sets it to "null" for blocked origins
    assert acao not in ("http://evil.com", "*")


def test_cors_env_override_affects_allowed_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    # Overriding settings.cors_origins before create_app() must flow through to
    # the CORS middleware — proving the middleware reads config, not a hardcoded value
    monkeypatch.setattr("src.api.config.settings.cors_origins", ["http://overridden.test"])
    app = create_app()
    with TestClient(app) as tc:
        response = tc.get("/health", headers={"Origin": "http://overridden.test"})
        assert response.headers.get("access-control-allow-origin") == "http://overridden.test"


# ---------------------------------------------------------------------------
# Routing sanity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_route_returns_404(client: AsyncClient) -> None:
    # Any path not registered must return 404
    response = await client.get("/nonexistent")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Session store lifecycle — use TestClient so the lifespan fires
# ---------------------------------------------------------------------------

def test_session_store_attached_after_lifespan() -> None:
    # After the lifespan runs, app.state.session_store must be a SessionStore
    app = create_app()
    with TestClient(app) as tc:
        tc.get("/health")  # ensure lifespan has started
        assert isinstance(app.state.session_store, SessionStore)


def test_two_app_instances_have_independent_stores() -> None:
    # Two create_app() calls must produce two completely independent stores
    app_a = create_app()
    app_b = create_app()

    with TestClient(app_a) as tc_a, TestClient(app_b) as tc_b:
        tc_a.get("/health")
        tc_b.get("/health")

        store_a: SessionStore = app_a.state.session_store
        store_b: SessionStore = app_b.state.session_store

        # The two stores are different objects
        assert store_a is not store_b

        # Mutating one session must not affect the other
        store_a.get_or_create().courses.append("shared?")
        assert store_b.get_or_create().courses == []


# ---------------------------------------------------------------------------
# get_session dependency — use TestClient so the lifespan fires
# ---------------------------------------------------------------------------

def test_get_session_dep_returns_session_data() -> None:
    # A probe route using Depends(get_session) must receive the app's SessionData
    probe_router = APIRouter()
    captured: list[SessionData] = []

    @probe_router.get("/probe")
    def probe(session: SessionData = Depends(get_session)) -> dict[str, str]:
        captured.append(session)
        return {"got": "session"}

    app = create_app()
    app.include_router(probe_router)

    with TestClient(app) as tc:
        response = tc.get("/probe")
        assert response.status_code == 200
        assert len(captured) == 1
        assert captured[0] is app.state.session_store.get_or_create()
