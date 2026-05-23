from __future__ import annotations

# Tests for PaginatedExporter (SCRUM-63)
# Each test checks one specific behaviour of the exporter.

import threading

import pytest

from src.api.adapters.paginated_exporter import PAGE_SIZE, PaginatedExporter


def test_add_and_total() -> None:
    # Adding items should increase the total count
    exp = PaginatedExporter()
    assert exp.total() == 0
    exp.add("a")
    exp.add("b")
    assert exp.total() == 2


def test_get_page_first() -> None:
    # Page 0 should return the first 50 items
    exp = PaginatedExporter()
    for i in range(120):
        exp.add(i)
    page0 = exp.get_page(0, 50)
    assert page0 == list(range(50))


def test_get_page_second() -> None:
    # Page 1 should return items 50–99
    exp = PaginatedExporter()
    for i in range(120):
        exp.add(i)
    page1 = exp.get_page(1, 50)
    assert page1 == list(range(50, 100))


def test_get_page_partial_last() -> None:
    # The last page can have fewer items than the page size
    exp = PaginatedExporter()
    for i in range(120):
        exp.add(i)
    page2 = exp.get_page(2, 50)
    assert page2 == list(range(100, 120))


def test_get_page_beyond_end_returns_empty() -> None:
    # Asking for a page that doesn't exist returns an empty list, not an error
    exp = PaginatedExporter()
    exp.add("x")
    assert exp.get_page(5, 50) == []


def test_reset_clears_items() -> None:
    # After reset, total is 0 and no items can be fetched
    exp = PaginatedExporter()
    exp.add("a")
    exp.add("b")
    exp.reset()
    assert exp.total() == 0
    assert exp.get_page(0, 50) == []


def test_thread_safety() -> None:
    # 200 threads all calling add() at the same time — no item should be lost
    exp = PaginatedExporter()
    threads = [threading.Thread(target=lambda: exp.add(1)) for _ in range(200)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert exp.total() == 200


def test_default_page_size_constant() -> None:
    # The default page size should always be 50
    assert PAGE_SIZE == 50


def test_memory_cap_stops_accepting_items() -> None:
    # Once we hit MAX_SCHEDULES, extra items are silently dropped (no crash)
    from src.api.adapters.paginated_exporter import MAX_SCHEDULES
    exp = PaginatedExporter()
    for _ in range(MAX_SCHEDULES + 50):
        exp.add("x")
    assert exp.total() == MAX_SCHEDULES
