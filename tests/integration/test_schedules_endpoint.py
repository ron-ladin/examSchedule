from __future__ import annotations

# Integration tests for GET /api/schedules (SCRUM-77).
#
# Test categories:
#   - Sanity      : happy-path, correct shape, header present
#   - Negative    : invalid query-param values → 422
#   - Boundary    : page/size edge values, last page, overflow
#   - Edge cases  : running generation, id continuity, defaults, large page

import pytest
from starlette.testclient import TestClient

from src.api.main import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Fresh app with an empty exporter."""
    app = create_app()
    with TestClient(app) as tc:
        yield tc, app


@pytest.fixture()
def client_with_schedules():
    """App whose exporter already holds 5 schedule items."""
    app = create_app()
    with TestClient(app) as tc:
        session = app.state.session_store.get_or_create()
        for i in range(5):
            session.exporter.add({"slot": f"item_{i}"})
        yield tc, app


@pytest.fixture()
def client_with_many_schedules():
    """App with 120 schedule items — enough to span multiple pages."""
    app = create_app()
    with TestClient(app) as tc:
        session = app.state.session_store.get_or_create()
        for i in range(120):
            session.exporter.add({"slot": f"item_{i}"})
        yield tc, app


# ===========================================================================
# SANITY — happy-path correctness
# ===========================================================================


def test_empty_exporter_returns_200(client) -> None:
    """GET /api/schedules must always return 200, even with no schedules."""
    tc, _ = client
    resp = tc.get("/api/schedules")
    assert resp.status_code == 200


def test_empty_exporter_returns_empty_items(client) -> None:
    tc, _ = client
    body = tc.get("/api/schedules").json()
    assert body["items"] == []


def test_empty_exporter_total_count_header_is_zero(client) -> None:
    """X-Total-Count must be 0 when the exporter is empty."""
    tc, _ = client
    resp = tc.get("/api/schedules")
    assert resp.headers["x-total-count"] == "0"


def test_response_shape_matches_paginated_dto(client_with_schedules) -> None:
    """Top-level keys page, size, items must all be present."""
    tc, _ = client_with_schedules
    body = tc.get("/api/schedules").json()
    assert "page" in body
    assert "size" in body
    assert "items" in body


def test_each_item_has_id_and_data(client_with_schedules) -> None:
    """Every ScheduleDTO must have id and data fields."""
    tc, _ = client_with_schedules
    items = tc.get("/api/schedules").json()["items"]
    for item in items:
        assert "id" in item
        assert "data" in item


def test_returns_correct_number_of_items(client_with_schedules) -> None:
    """5 stored schedules → 5 items on page 0 (size 50)."""
    tc, _ = client_with_schedules
    body = tc.get("/api/schedules").json()
    assert len(body["items"]) == 5


def test_x_total_count_header_equals_stored_count(client_with_schedules) -> None:
    """X-Total-Count must reflect the true total, not just the page size."""
    tc, _ = client_with_schedules
    resp = tc.get("/api/schedules")
    assert resp.headers["x-total-count"] == "5"


def test_page_echo_in_response(client_with_schedules) -> None:
    """Response body must echo back the requested page number."""
    tc, _ = client_with_schedules
    body = tc.get("/api/schedules?page=0").json()
    assert body["page"] == 0


def test_size_echo_in_response(client_with_schedules) -> None:
    """Response body must echo back the requested page size."""
    tc, _ = client_with_schedules
    body = tc.get("/api/schedules?size=10").json()
    assert body["size"] == 10


def test_item_data_matches_stored_content(client_with_schedules) -> None:
    """The data dict in each ScheduleDTO must reflect what was added to the exporter."""
    tc, _ = client_with_schedules
    items = tc.get("/api/schedules").json()["items"]
    for i, item in enumerate(items):
        assert item["data"] == {"slot": f"item_{i}"}


# ===========================================================================
# NEGATIVE — invalid query params → 422 Unprocessable Entity
# ===========================================================================


def test_negative_page_returns_422(client) -> None:
    """page must be >= 0."""
    tc, _ = client
    assert tc.get("/api/schedules?page=-1").status_code == 422


def test_size_zero_returns_422(client) -> None:
    """size must be >= 1."""
    tc, _ = client
    assert tc.get("/api/schedules?size=0").status_code == 422


def test_negative_size_returns_422(client) -> None:
    """size must be >= 1."""
    tc, _ = client
    assert tc.get("/api/schedules?size=-5").status_code == 422


def test_size_above_max_returns_422(client) -> None:
    """size must not exceed 200."""
    tc, _ = client
    assert tc.get("/api/schedules?size=201").status_code == 422


def test_non_integer_page_returns_422(client) -> None:
    """page must be an integer."""
    tc, _ = client
    assert tc.get("/api/schedules?page=abc").status_code == 422


def test_non_integer_size_returns_422(client) -> None:
    """size must be an integer."""
    tc, _ = client
    assert tc.get("/api/schedules?size=abc").status_code == 422


def test_float_page_returns_422(client) -> None:
    """Fractional page numbers are rejected."""
    tc, _ = client
    assert tc.get("/api/schedules?page=1.5").status_code == 422


# ===========================================================================
# BOUNDARY — edge values of page and size
# ===========================================================================


def test_page_zero_is_first_page(client_with_many_schedules) -> None:
    """page=0, size=50 must return the first 50 items."""
    tc, _ = client_with_many_schedules
    body = tc.get("/api/schedules?page=0&size=50").json()
    assert len(body["items"]) == 50


def test_page_one_returns_next_50(client_with_many_schedules) -> None:
    """page=1, size=50 must return items 50-99."""
    tc, _ = client_with_many_schedules
    body = tc.get("/api/schedules?page=1&size=50").json()
    assert len(body["items"]) == 50


def test_last_partial_page_returns_remaining_items(client_with_many_schedules) -> None:
    """120 items, size=50 → page 2 has 20 items (the remainder)."""
    tc, _ = client_with_many_schedules
    body = tc.get("/api/schedules?page=2&size=50").json()
    assert len(body["items"]) == 20


def test_page_beyond_last_returns_empty_not_404(client_with_many_schedules) -> None:
    """Requesting a page past the last item must return 200 with empty list."""
    tc, _ = client_with_many_schedules
    resp = tc.get("/api/schedules?page=999&size=50")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_size_1_returns_exactly_one_item(client_with_schedules) -> None:
    """Minimum page size must work: exactly one item returned."""
    tc, _ = client_with_schedules
    body = tc.get("/api/schedules?page=0&size=1").json()
    assert len(body["items"]) == 1


def test_size_200_is_accepted(client_with_schedules) -> None:
    """Maximum allowed size must not be rejected."""
    tc, _ = client_with_schedules
    assert tc.get("/api/schedules?size=200").status_code == 200


def test_size_larger_than_total_returns_all_items(client_with_schedules) -> None:
    """If size > total items, all items are returned on page 0."""
    tc, _ = client_with_schedules
    body = tc.get("/api/schedules?page=0&size=200").json()
    assert len(body["items"]) == 5  # only 5 stored


def test_x_total_count_is_total_not_page_size(client_with_many_schedules) -> None:
    """X-Total-Count must report 120 even when page only has 50 items."""
    tc, _ = client_with_many_schedules
    resp = tc.get("/api/schedules?page=0&size=50")
    assert resp.headers["x-total-count"] == "120"


def test_ids_are_sequential_within_page(client_with_many_schedules) -> None:
    """IDs on page 0 must be 0, 1, 2, ... (global sequential index)."""
    tc, _ = client_with_many_schedules
    items = tc.get("/api/schedules?page=0&size=50").json()["items"]
    for i, item in enumerate(items):
        assert item["id"] == i


def test_ids_continue_across_page_boundary(client_with_many_schedules) -> None:
    """IDs on page 1 (size=50) must start at 50, not restart at 0."""
    tc, _ = client_with_many_schedules
    items = tc.get("/api/schedules?page=1&size=50").json()["items"]
    for i, item in enumerate(items):
        assert item["id"] == 50 + i


# ===========================================================================
# EDGE CASES
# ===========================================================================


def test_default_params_work_without_query_string(client_with_schedules) -> None:
    """Calling /api/schedules with no params must use page=0 and size=50."""
    tc, _ = client_with_schedules
    resp = tc.get("/api/schedules")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 0
    assert body["size"] == 50


def test_x_total_count_header_present_even_when_empty(client) -> None:
    """X-Total-Count must always be present, even with zero schedules."""
    tc, _ = client
    resp = tc.get("/api/schedules")
    assert "x-total-count" in resp.headers


def test_very_large_page_number_returns_empty_list(client_with_schedules) -> None:
    """A very large page (e.g. 10^6) must return 200 + empty list, not crash."""
    tc, _ = client_with_schedules
    resp = tc.get("/api/schedules?page=1000000")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_schedules_readable_while_generation_running(client) -> None:
    """The endpoint must not block or fail if generation is still running."""
    tc, app = client
    session = app.state.session_store.get_or_create()
    # Simulate generation mid-run: status = "running", some items already stored
    session.generation_status = "running"
    session.exporter.add({"slot": "partial_item"})
    resp = tc.get("/api/schedules")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


def test_x_total_count_reflects_partial_results_during_generation(client) -> None:
    """X-Total-Count shows live count even before generation finishes."""
    tc, app = client
    session = app.state.session_store.get_or_create()
    session.generation_status = "running"
    for _ in range(7):
        session.exporter.add({"slot": "x"})
    resp = tc.get("/api/schedules")
    assert resp.headers["x-total-count"] == "7"


def test_exporter_reset_clears_results(client) -> None:
    """After exporter.reset(), GET /api/schedules must return empty."""
    tc, app = client
    session = app.state.session_store.get_or_create()
    for i in range(3):
        session.exporter.add({"slot": i})
    assert tc.get("/api/schedules").json()["items"] != []
    session.exporter.reset()
    body = tc.get("/api/schedules").json()
    assert body["items"] == []
    assert tc.get("/api/schedules").headers["x-total-count"] == "0"
