from __future__ import annotations

# Integration tests for period mutation endpoints (SCRUM-73/74).
# Covers: exclusion toggle, date range update, 404 for unknown key,
# 400 for invalid date range.

from datetime import date
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.domain.exam_period import ExamPeriod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PERIOD_KEY = "FALL - Aleph"


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """Fresh app with one ExamPeriod already in session.periods."""
    app = create_app()
    with TestClient(app) as tc:
        session = app.state.session_store.get_or_create()
        session.periods = [
            ExamPeriod(
                semester="FALL",
                moed="Aleph",
                date_ranges=[(date(2025, 1, 5), date(2025, 1, 25))],
            )
        ]
        yield tc


# ---------------------------------------------------------------------------
# PATCH /{key}/exclusions — happy path
# ---------------------------------------------------------------------------

def test_exclude_returns_200(client: TestClient) -> None:
    response = client.patch(
        f"/api/periods/{_PERIOD_KEY}/exclusions",
        json={"excluded": True},
    )
    assert response.status_code == 200


def test_exclude_sets_excluded_true(client: TestClient) -> None:
    body = client.patch(
        f"/api/periods/{_PERIOD_KEY}/exclusions",
        json={"excluded": True},
    ).json()
    assert body["excluded"] is True


def test_include_sets_excluded_false(client: TestClient) -> None:
    # First exclude, then re-include
    client.patch(f"/api/periods/{_PERIOD_KEY}/exclusions", json={"excluded": True})
    body = client.patch(
        f"/api/periods/{_PERIOD_KEY}/exclusions",
        json={"excluded": False},
    ).json()
    assert body["excluded"] is False


def test_exclusion_response_contains_key(client: TestClient) -> None:
    body = client.patch(
        f"/api/periods/{_PERIOD_KEY}/exclusions",
        json={"excluded": True},
    ).json()
    assert body["key"] == _PERIOD_KEY


def test_exclusion_response_contains_valid_dates(client: TestClient) -> None:
    body = client.patch(
        f"/api/periods/{_PERIOD_KEY}/exclusions",
        json={"excluded": False},
    ).json()
    assert isinstance(body["valid_dates"], list)


# ---------------------------------------------------------------------------
# PATCH /{key}/exclusions — 404 for unknown key
# ---------------------------------------------------------------------------

def test_exclusion_unknown_key_returns_404(client: TestClient) -> None:
    response = client.patch(
        "/api/periods/UNKNOWN - Key/exclusions",
        json={"excluded": True},
    )
    assert response.status_code == 404


def test_exclusion_404_body_has_not_found_code(client: TestClient) -> None:
    body = client.patch(
        "/api/periods/NO - KEY/exclusions",
        json={"excluded": True},
    ).json()
    assert body["code"] == "NOT_FOUND"


def test_exclusion_404_detail_mentions_key(client: TestClient) -> None:
    body = client.patch(
        "/api/periods/MISSING - Key/exclusions",
        json={"excluded": True},
    ).json()
    assert "MISSING - Key" in body["detail"]


# ---------------------------------------------------------------------------
# PATCH /{key}/range — happy path
# ---------------------------------------------------------------------------

def test_range_update_returns_200(client: TestClient) -> None:
    response = client.patch(
        f"/api/periods/{_PERIOD_KEY}/range",
        json={"start": "2025-01-10", "end": "2025-01-20"},
    )
    assert response.status_code == 200


def test_range_update_reflects_new_start(client: TestClient) -> None:
    body = client.patch(
        f"/api/periods/{_PERIOD_KEY}/range",
        json={"start": "2025-01-10", "end": "2025-01-20"},
    ).json()
    assert body["start_date"] == "2025-01-10"


def test_range_update_reflects_new_end(client: TestClient) -> None:
    body = client.patch(
        f"/api/periods/{_PERIOD_KEY}/range",
        json={"start": "2025-01-10", "end": "2025-01-20"},
    ).json()
    assert body["end_date"] == "2025-01-20"


def test_range_update_recalculates_valid_dates(client: TestClient) -> None:
    body = client.patch(
        f"/api/periods/{_PERIOD_KEY}/range",
        json={"start": "2025-01-13", "end": "2025-01-14"},
    ).json()
    # 13 Jan 2025 is Monday, 14 Jan is Tuesday — both valid
    assert len(body["valid_dates"]) == 2


# ---------------------------------------------------------------------------
# PATCH /{key}/range — validation errors
# ---------------------------------------------------------------------------

def test_range_start_equal_end_returns_400(client: TestClient) -> None:
    response = client.patch(
        f"/api/periods/{_PERIOD_KEY}/range",
        json={"start": "2025-01-15", "end": "2025-01-15"},
    )
    assert response.status_code == 400


def test_range_start_after_end_returns_400(client: TestClient) -> None:
    response = client.patch(
        f"/api/periods/{_PERIOD_KEY}/range",
        json={"start": "2025-01-20", "end": "2025-01-10"},
    )
    assert response.status_code == 400


def test_range_400_body_has_validation_code(client: TestClient) -> None:
    body = client.patch(
        f"/api/periods/{_PERIOD_KEY}/range",
        json={"start": "2025-01-20", "end": "2025-01-10"},
    ).json()
    assert body["code"] == "VALIDATION_ERROR"


def test_range_400_detail_mentions_start(client: TestClient) -> None:
    body = client.patch(
        f"/api/periods/{_PERIOD_KEY}/range",
        json={"start": "2025-01-20", "end": "2025-01-10"},
    ).json()
    assert "start" in body["detail"].lower()


# ---------------------------------------------------------------------------
# PATCH /{key}/range — 404 for unknown key
# ---------------------------------------------------------------------------

def test_range_unknown_key_returns_404(client: TestClient) -> None:
    response = client.patch(
        "/api/periods/NO - KEY/range",
        json={"start": "2025-01-10", "end": "2025-01-20"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Excluded state preserved across requests
# ---------------------------------------------------------------------------

def test_excluded_state_persists_across_requests(client: TestClient) -> None:
    client.patch(f"/api/periods/{_PERIOD_KEY}/exclusions", json={"excluded": True})
    # Range update should preserve excluded state
    body = client.patch(
        f"/api/periods/{_PERIOD_KEY}/range",
        json={"start": "2025-01-10", "end": "2025-01-20"},
    ).json()
    assert body["excluded"] is True
