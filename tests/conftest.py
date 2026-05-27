from __future__ import annotations

import os

# Force ThreadPoolExecutor in tests so unittest.mock.patch works across the
# boundary — ProcessPoolExecutor spawns a fresh process where patches are gone.
os.environ.setdefault("USE_PROCESS_POOL", "false")

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.main import create_app


@pytest.fixture()
def app() -> FastAPI:
    """
    Create a fresh FastAPI app instance for each test.

    This keeps API state isolated between tests and prevents session data
    from leaking from one test to another.
    """
    return create_app()


@pytest.fixture()
def test_client(app: FastAPI) -> Generator[TestClient, None, None]:
    """
    Provide a FastAPI TestClient with lifespan support.

    Using the TestClient as a context manager ensures startup/shutdown logic
    runs correctly for every test.
    """
    with TestClient(app) as client:
        yield client
