from __future__ import annotations

# Tests for SessionStore and SessionData (SCRUM-59)
# Each test checks one specific behaviour of the session layer. No HTTP involved.

import threading

from src.api.adapters.paginated_exporter import PaginatedExporter
from src.api.session.models import SessionData
from src.api.session.store import SessionStore


# ---------------------------------------------------------------------------
# SessionData defaults
# ---------------------------------------------------------------------------

def test_session_data_default_courses_empty() -> None:
    # courses list must start empty
    session = SessionData()
    assert session.courses == []


def test_session_data_default_periods_empty() -> None:
    # periods list must start empty
    session = SessionData()
    assert session.periods == []


def test_session_data_default_generation_status_idle() -> None:
    # generation_status must default to "idle"
    session = SessionData()
    assert session.generation_status == "idle"


def test_session_data_default_generation_error_none() -> None:
    # generation_error must default to None (no error)
    session = SessionData()
    assert session.generation_error is None


def test_session_data_default_exporter_is_paginated_exporter() -> None:
    # exporter field must be a PaginatedExporter instance by default
    session = SessionData()
    assert isinstance(session.exporter, PaginatedExporter)


# ---------------------------------------------------------------------------
# SessionStore basic contract
# ---------------------------------------------------------------------------

def test_get_or_create_returns_session_data() -> None:
    # get_or_create() must return a SessionData
    store = SessionStore()
    result = store.get_or_create()
    assert isinstance(result, SessionData)


def test_get_or_create_same_object_twice() -> None:
    # Two consecutive calls must return the exact same object (identity, not equality)
    store = SessionStore()
    first = store.get_or_create()
    second = store.get_or_create()
    assert first is second


# ---------------------------------------------------------------------------
# reset() behaviour
# ---------------------------------------------------------------------------

def test_reset_returns_different_object() -> None:
    # After reset(), get_or_create() must return a NEW SessionData, not the old one
    store = SessionStore()
    old = store.get_or_create()
    store.reset()
    new = store.get_or_create()
    assert old is not new


def test_reset_clears_exporter_contents() -> None:
    # Schedules stored in the exporter before reset must not appear in the new session
    store = SessionStore()
    store.get_or_create().exporter.add({"dummy": "data"})
    store.reset()
    assert store.get_or_create().exporter.total() == 0


def test_reset_clears_generation_status() -> None:
    # generation_status that was "running" must go back to "idle" after reset
    store = SessionStore()
    store.get_or_create().generation_status = "running"
    store.reset()
    assert store.get_or_create().generation_status == "idle"


def test_reset_clears_generation_error() -> None:
    # A non-None generation_error must disappear after reset
    store = SessionStore()
    store.get_or_create().generation_error = "something went wrong"
    store.reset()
    assert store.get_or_create().generation_error is None


def test_reset_clears_courses_list() -> None:
    # Courses accumulated before reset must not appear in the new session
    store = SessionStore()
    store.get_or_create().courses.append("course_a")
    store.reset()
    assert store.get_or_create().courses == []


def test_reset_clears_periods_list() -> None:
    # Periods accumulated before reset must not appear in the new session
    store = SessionStore()
    store.get_or_create().periods.append("period_a")
    store.reset()
    assert store.get_or_create().periods == []


# ---------------------------------------------------------------------------
# Mutation on SessionData fields
# ---------------------------------------------------------------------------

def test_courses_list_is_mutable() -> None:
    # courses must be a plain list that callers can append to
    session = SessionData()
    session.courses.append("math101")
    assert "math101" in session.courses


def test_periods_list_is_mutable() -> None:
    # periods must be a plain list that callers can append to
    session = SessionData()
    session.periods.append("FALL-Aleph")
    assert "FALL-Aleph" in session.periods


def test_generation_error_can_be_set_and_reset() -> None:
    # generation_error must accept a non-None string and later be set back to None
    session = SessionData()
    session.generation_error = "timeout"
    assert session.generation_error == "timeout"
    session.generation_error = None
    assert session.generation_error is None


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

def test_get_or_create_thread_safety() -> None:
    # 50 threads calling get_or_create() simultaneously must all get the same object
    store = SessionStore()
    results: list[SessionData] = []
    lock = threading.Lock()

    def grab() -> None:
        session = store.get_or_create()
        with lock:
            results.append(session)

    threads = [threading.Thread(target=grab) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 50
    # Every thread must have received the exact same object
    first = results[0]
    assert all(s is first for s in results)
