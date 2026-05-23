from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.config import settings
from src.api.routers import health
from src.api.session.store import SessionStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Create shared state on startup; clean up on shutdown.

    Why lifespan instead of @app.on_event("startup"):
    @on_event is deprecated since FastAPI 0.93. Lifespan is the modern pattern
    and makes the startup/teardown lifecycle explicit and testable.

    v1.0 single-worker constraint:
    SessionStore lives in process memory. If you start uvicorn with multiple
    workers (--workers N or WEB_CONCURRENCY=N), each worker gets its own private
    SessionStore. Requests from the same user will be load-balanced across workers
    and see completely different state. Always run with a single worker until v2
    introduces a shared-state backend.
    Run: uvicorn src.api.main:create_app --factory --port 8000 --reload
    Do NOT add --workers > 1 until v2.
    """
    worker_count = int(os.environ.get("WEB_CONCURRENCY", "1"))
    if worker_count > 1:
        logger.warning(
            "v1.0 in-memory SessionStore is NOT safe with multiple workers "
            "(WEB_CONCURRENCY=%s). Each worker holds its own SessionData — "
            "requests will see inconsistent state. Set WEB_CONCURRENCY=1.",
            worker_count,
        )

    app.state.session_store = SessionStore()
    yield
    # Nothing to tear down in v1.0 — SessionStore holds only in-memory state


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Why a factory instead of a module-level app = FastAPI():
    The factory lets tests call create_app() and get a fresh, isolated app
    each time. A module-level instance would share state across tests.
    """
    app = FastAPI(
        title="Exam Schedule API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Allow the frontend dev server (and any origin in settings) to call the API.
    # allow_credentials, allow_methods, allow_headers are broad for v1.0 —
    # tighten when auth is added in v2.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, tags=["health"])

    return app
