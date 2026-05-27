from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.config import settings
from src.api.exceptions.handlers import register_handlers
from src.api.routers import data, generate, health, periods
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

    # CPU-bound generation runs in a ProcessPoolExecutor to bypass the GIL.
    # Tests set USE_PROCESS_POOL=false to keep everything in-process so
    # unittest.mock.patch works across process boundaries.
    if settings.use_process_pool:
        app.state.executor = ProcessPoolExecutor(max_workers=1)
        logger.info("Generation executor: ProcessPoolExecutor (max_workers=1)")
    else:
        app.state.executor = ThreadPoolExecutor(max_workers=1)
        logger.info("Generation executor: ThreadPoolExecutor (use_process_pool=false)")

    yield

    app.state.executor.shutdown(wait=False)


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
        expose_headers=["X-Total-Count"],
    )

    app.include_router(health.router, tags=["health"])
    app.include_router(generate.router)
    app.include_router(data.router, prefix="/api/data", tags=["data"])
    app.include_router(periods.router, prefix="/api/periods", tags=["periods"])

    register_handlers(app)

    return app
