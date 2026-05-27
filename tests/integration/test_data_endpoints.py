from __future__ import annotations

# Integration tests for the data upload and status endpoints (SCRUM-67/68/69).
# Covers: replace/append modes for courses and periods, status counts,
# cache freshness flag, duplicate period guard, and validation errors.

from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.adapters.json_cache_adapter import JsonCacheAdapter
from src.api.main import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    """Fresh app per test with an isolated cache so no disk side-effects."""
    app = create_app()
    cache = JsonCacheAdapter(tmp_path / ".cache.json")
    with patch("src.api.routers.data._cache", cache):
        with TestClient(app) as tc:
            yield tc


# Unique period definitions — (semester, moed, start, end)
_PERIOD_DEFS = [
    ("FALL", "Aleph", "05-01-2025", "25-01-2025"),
    ("FALL", "Bet",   "01-03-2025", "20-03-2025"),
    ("SPRI", "Aleph", "01-06-2025", "20-06-2025"),
    ("SPRI", "Bet",   "01-07-2025", "20-07-2025"),
]


def _course_payload(count: int = 1, start: int = 0) -> bytes:
    """Build a valid courses.txt payload ($$$$-delimited) with unique course IDs."""
    records = [
        f"$$$$\nCourse {i}\n1000{i}\nProf {i}\n83101, 1, FALL, Obligatory\nExam"
        for i in range(start, start + count)
    ]
    return ("\n".join(records) + "\n").encode()


def _period_payload(count: int = 1, start: int = 0) -> bytes:
    """Build a valid dates.txt payload ($$$$-delimited) with unique period keys."""
    records = [
        f"$$$$\n{sem}, {moed}\n{s}, {e}"
        for sem, moed, s, e in _PERIOD_DEFS[start : start + count]
    ]
    return ("\n".join(records) + "\n").encode()


# ---------------------------------------------------------------------------
# Courses upload — POST (replace)
# ---------------------------------------------------------------------------

def test_post_courses_returns_200(client: TestClient) -> None:
    response = client.post(
        "/api/data/courses/upload",
        files={"file": ("courses.txt", _course_payload(2), "text/plain")},
    )
    assert response.status_code == 200


def test_post_courses_count_matches_uploaded(client: TestClient) -> None:
    response = client.post(
        "/api/data/courses/upload",
        files={"file": ("courses.txt", _course_payload(3), "text/plain")},
    )
    assert response.json()["count"] == 3


def test_post_courses_mode_is_replace(client: TestClient) -> None:
    response = client.post(
        "/api/data/courses/upload",
        files={"file": ("courses.txt", _course_payload(1), "text/plain")},
    )
    assert response.json()["mode"] == "replace"


def test_post_courses_replaces_previous(client: TestClient) -> None:
    client.post(
        "/api/data/courses/upload",
        files={"file": ("courses.txt", _course_payload(5), "text/plain")},
    )
    response = client.post(
        "/api/data/courses/upload",
        files={"file": ("courses.txt", _course_payload(2), "text/plain")},
    )
    assert response.json()["count"] == 2


# ---------------------------------------------------------------------------
# Courses upload — PATCH (append)
# ---------------------------------------------------------------------------

def test_patch_courses_appends_to_existing(client: TestClient) -> None:
    client.post(
        "/api/data/courses/upload",
        files={"file": ("courses.txt", _course_payload(2), "text/plain")},
    )
    response = client.patch(
        "/api/data/courses/upload?mode=append",
        files={"file": ("courses.txt", _course_payload(3, start=2), "text/plain")},
    )
    assert response.json()["count"] == 5


def test_patch_courses_mode_is_append(client: TestClient) -> None:
    response = client.patch(
        "/api/data/courses/upload?mode=append",
        files={"file": ("courses.txt", _course_payload(1), "text/plain")},
    )
    assert response.json()["mode"] == "append"


# ---------------------------------------------------------------------------
# Periods upload — POST (replace)
# ---------------------------------------------------------------------------

def test_post_periods_returns_200(client: TestClient) -> None:
    response = client.post(
        "/api/data/periods/upload",
        files={"file": ("periods.txt", _period_payload(1), "text/plain")},
    )
    assert response.status_code == 200


def test_post_periods_count_matches_uploaded(client: TestClient) -> None:
    response = client.post(
        "/api/data/periods/upload",
        files={"file": ("periods.txt", _period_payload(2), "text/plain")},
    )
    assert response.json()["count"] == 2


def test_post_periods_replaces_previous(client: TestClient) -> None:
    client.post(
        "/api/data/periods/upload",
        files={"file": ("periods.txt", _period_payload(4), "text/plain")},
    )
    response = client.post(
        "/api/data/periods/upload",
        files={"file": ("periods.txt", _period_payload(1), "text/plain")},
    )
    assert response.json()["count"] == 1


# ---------------------------------------------------------------------------
# Periods upload — PATCH (append)
# ---------------------------------------------------------------------------

def test_patch_periods_appends_to_existing(client: TestClient) -> None:
    client.post(
        "/api/data/periods/upload",
        files={"file": ("periods.txt", _period_payload(1), "text/plain")},
    )
    response = client.patch(
        "/api/data/periods/upload?mode=append",
        files={"file": ("periods.txt", _period_payload(1, start=1), "text/plain")},
    )
    assert response.json()["count"] == 2


def test_patch_periods_duplicate_returns_400(client: TestClient) -> None:
    client.post(
        "/api/data/periods/upload",
        files={"file": ("periods.txt", _period_payload(1), "text/plain")},
    )
    response = client.patch(
        "/api/data/periods/upload?mode=append",
        files={"file": ("periods.txt", _period_payload(1), "text/plain")},
    )
    assert response.status_code == 400


def test_patch_periods_duplicate_detail_mentions_key(client: TestClient) -> None:
    client.post(
        "/api/data/periods/upload",
        files={"file": ("periods.txt", _period_payload(1), "text/plain")},
    )
    body = client.patch(
        "/api/data/periods/upload?mode=append",
        files={"file": ("periods.txt", _period_payload(1), "text/plain")},
    ).json()
    assert "FALL" in body["detail"]


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------

def test_status_returns_200(client: TestClient) -> None:
    assert client.get("/api/data/status").status_code == 200


def test_status_course_count_zero_initially(client: TestClient) -> None:
    body = client.get("/api/data/status").json()
    assert body["course_count"] == 0


def test_status_period_count_zero_initially(client: TestClient) -> None:
    body = client.get("/api/data/status").json()
    assert body["period_count"] == 0


def test_status_cache_not_fresh_initially(client: TestClient) -> None:
    body = client.get("/api/data/status").json()
    assert body["cache_fresh"] is False


def test_status_reflects_uploaded_course_count(client: TestClient) -> None:
    client.post(
        "/api/data/courses/upload",
        files={"file": ("c.txt", _course_payload(4), "text/plain")},
    )
    body = client.get("/api/data/status").json()
    assert body["course_count"] == 4


def test_status_reflects_uploaded_period_count(client: TestClient) -> None:
    client.post(
        "/api/data/periods/upload",
        files={"file": ("p.txt", _period_payload(2), "text/plain")},
    )
    body = client.get("/api/data/status").json()
    assert body["period_count"] == 2


def test_status_cache_fresh_after_upload(client: TestClient) -> None:
    client.post(
        "/api/data/courses/upload",
        files={"file": ("c.txt", _course_payload(1), "text/plain")},
    )
    body = client.get("/api/data/status").json()
    assert body["cache_fresh"] is True


def test_status_last_run_none_before_generation(client: TestClient) -> None:
    body = client.get("/api/data/status").json()
    assert body["last_run"] is None


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

def test_invalid_mode_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/data/courses/upload?mode=invalid",
        files={"file": ("c.txt", _course_payload(1), "text/plain")},
    )
    assert response.status_code == 422


def test_invalid_courses_file_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/data/courses/upload",
        files={"file": ("c.txt", b"not a valid courses file", "text/plain")},
    )
    assert response.status_code == 400


def test_invalid_periods_file_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/data/periods/upload",
        files={"file": ("p.txt", b"not a valid periods file", "text/plain")},
    )
    assert response.status_code == 400


def test_malformed_course_record_returns_400(client: TestClient) -> None:
    # Record with too few lines (needs at least 5)
    payload = b"$$$$\nCourse Name\n10001\n"
    response = client.post(
        "/api/data/courses/upload",
        files={"file": ("c.txt", payload, "text/plain")},
    )
    assert response.status_code == 400


def test_error_response_has_detail_key(client: TestClient) -> None:
    response = client.post(
        "/api/data/courses/upload",
        files={"file": ("c.txt", b"bad", "text/plain")},
    )
    assert "detail" in response.json()
