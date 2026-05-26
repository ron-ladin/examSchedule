from __future__ import annotations

# Integration tests for the data upload and status endpoints (SCRUM-67/68/69).
# Covers: replace/append modes for courses and periods, status counts,
# cache freshness flag, and validation errors for bad payloads.

import json
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


def _course_payload(count: int = 1) -> bytes:
    """Build a minimal valid JSON courses payload."""
    courses = [
        {
            "id": f"1000{i}",
            "name": f"Course {i}",
            "instructor": f"Prof {i}",
            "evaluation_type": "Exam",
            "offerings": [
                {
                    "program_id": "83101",
                    "year": 1,
                    "semester": "FALL",
                    "requirement": "Obligatory",
                }
            ],
        }
        for i in range(count)
    ]
    return json.dumps(courses).encode()


def _period_payload(count: int = 1) -> bytes:
    """Build a minimal valid JSON periods payload."""
    periods = [
        {
            "semester": "FALL",
            "moed": "Aleph",
            "date_ranges": [["05-01-2025", "25-01-2025"]],
            "excluded_dates": [],
        }
        for _ in range(count)
    ]
    return json.dumps(periods).encode()


# ---------------------------------------------------------------------------
# Courses upload — POST (replace)
# ---------------------------------------------------------------------------

def test_post_courses_returns_200(client: TestClient) -> None:
    response = client.post(
        "/api/data/courses/upload",
        files={"file": ("courses.json", _course_payload(2), "application/json")},
    )
    assert response.status_code == 200


def test_post_courses_count_matches_uploaded(client: TestClient) -> None:
    response = client.post(
        "/api/data/courses/upload",
        files={"file": ("courses.json", _course_payload(3), "application/json")},
    )
    assert response.json()["count"] == 3


def test_post_courses_mode_is_replace(client: TestClient) -> None:
    response = client.post(
        "/api/data/courses/upload",
        files={"file": ("courses.json", _course_payload(1), "application/json")},
    )
    assert response.json()["mode"] == "replace"


def test_post_courses_replaces_previous(client: TestClient) -> None:
    client.post(
        "/api/data/courses/upload",
        files={"file": ("courses.json", _course_payload(5), "application/json")},
    )
    response = client.post(
        "/api/data/courses/upload",
        files={"file": ("courses.json", _course_payload(2), "application/json")},
    )
    assert response.json()["count"] == 2


# ---------------------------------------------------------------------------
# Courses upload — PATCH (append)
# ---------------------------------------------------------------------------

def test_patch_courses_appends_to_existing(client: TestClient) -> None:
    client.post(
        "/api/data/courses/upload",
        files={"file": ("courses.json", _course_payload(2), "application/json")},
    )
    response = client.patch(
        "/api/data/courses/upload?mode=append",
        files={"file": ("courses.json", _course_payload(3), "application/json")},
    )
    assert response.json()["count"] == 5


def test_patch_courses_mode_is_append(client: TestClient) -> None:
    response = client.patch(
        "/api/data/courses/upload?mode=append",
        files={"file": ("courses.json", _course_payload(1), "application/json")},
    )
    assert response.json()["mode"] == "append"


# ---------------------------------------------------------------------------
# Periods upload — POST (replace)
# ---------------------------------------------------------------------------

def test_post_periods_returns_200(client: TestClient) -> None:
    response = client.post(
        "/api/data/periods/upload",
        files={"file": ("periods.json", _period_payload(1), "application/json")},
    )
    assert response.status_code == 200


def test_post_periods_count_matches_uploaded(client: TestClient) -> None:
    response = client.post(
        "/api/data/periods/upload",
        files={"file": ("periods.json", _period_payload(2), "application/json")},
    )
    assert response.json()["count"] == 2


def test_post_periods_replaces_previous(client: TestClient) -> None:
    client.post(
        "/api/data/periods/upload",
        files={"file": ("periods.json", _period_payload(4), "application/json")},
    )
    response = client.post(
        "/api/data/periods/upload",
        files={"file": ("periods.json", _period_payload(1), "application/json")},
    )
    assert response.json()["count"] == 1


# ---------------------------------------------------------------------------
# Periods upload — PATCH (append)
# ---------------------------------------------------------------------------

def test_patch_periods_appends_to_existing(client: TestClient) -> None:
    client.post(
        "/api/data/periods/upload",
        files={"file": ("periods.json", _period_payload(1), "application/json")},
    )
    response = client.patch(
        "/api/data/periods/upload?mode=append",
        files={"file": ("periods.json", _period_payload(2), "application/json")},
    )
    assert response.json()["count"] == 3


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
        files={"file": ("c.json", _course_payload(4), "application/json")},
    )
    body = client.get("/api/data/status").json()
    assert body["course_count"] == 4


def test_status_reflects_uploaded_period_count(client: TestClient) -> None:
    client.post(
        "/api/data/periods/upload",
        files={"file": ("p.json", _period_payload(2), "application/json")},
    )
    body = client.get("/api/data/status").json()
    assert body["period_count"] == 2


def test_status_cache_fresh_after_upload(client: TestClient) -> None:
    client.post(
        "/api/data/courses/upload",
        files={"file": ("c.json", _course_payload(1), "application/json")},
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
        files={"file": ("c.json", _course_payload(1), "application/json")},
    )
    assert response.status_code == 422


def test_malformed_json_courses_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/data/courses/upload",
        files={"file": ("c.json", b"not json at all", "application/json")},
    )
    assert response.status_code == 400


def test_malformed_json_periods_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/data/periods/upload",
        files={"file": ("p.json", b"not json at all", "application/json")},
    )
    assert response.status_code == 400


def test_non_array_json_courses_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/data/courses/upload",
        files={"file": ("c.json", b'{"key": "value"}', "application/json")},
    )
    assert response.status_code == 400


def test_missing_required_course_field_returns_400(client: TestClient) -> None:
    payload = json.dumps([{"id": "10001", "name": "X"}]).encode()
    response = client.post(
        "/api/data/courses/upload",
        files={"file": ("c.json", payload, "application/json")},
    )
    assert response.status_code == 400


def test_error_response_has_detail_key(client: TestClient) -> None:
    response = client.post(
        "/api/data/courses/upload",
        files={"file": ("c.json", b"bad", "application/json")},
    )
    assert "detail" in response.json()
