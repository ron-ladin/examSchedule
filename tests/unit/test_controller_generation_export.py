"""
Unit Tests: DesktopController — generation, export, staleness, and caching.

Covers generate() precondition guards and happy paths, export gating on
stale results, _merge_by_key duplicate warnings, cache_generated_results /
resort behaviour, and engine-level §4.4 schedule rejection.
"""

import logging
import sqlite3
from datetime import date

import pytest

from src.adapters.sqlite_schedule_store import SQLiteScheduleStore
from src.controller import DesktopController
from src.domain.course import Course

from tests.unit._controller_helpers import _write_courses, _write_periods


# ── generate (precondition guards) ───────────────────────────────────────────

def test_generate_raises_when_no_programmes_selected():
    ctrl = DesktopController()

    with pytest.raises(ValueError, match="No programmes selected"):
        ctrl.generate()


def test_generate_raises_when_no_courses_loaded(tmp_path):
    ctrl = DesktopController()
    ctrl.set_selected_programs(["83101"])

    with pytest.raises(ValueError, match="No courses loaded"):
        ctrl.generate()


def test_generate_raises_when_no_periods_loaded(tmp_path):
    cp = tmp_path / "courses.txt"
    _write_courses(cp)

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.set_selected_programs(["83101"])

    with pytest.raises(ValueError, match="No exam periods loaded"):
        ctrl.generate()


# ── generate (happy path) ────────────────────────────────────────────────────

def test_generate_returns_schedules_and_courses(tmp_path):
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"

    _write_courses(cp)
    _write_periods(dp)

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])

    schedules_by_period, courses_by_id, truncated = ctrl.generate()

    assert isinstance(schedules_by_period, dict)
    assert isinstance(courses_by_id, dict)
    assert isinstance(truncated, set)
    assert "11111" in courses_by_id
    assert not truncated


def test_generate_records_sqlite_performance_metrics_without_changing_results(tmp_path):
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"

    _write_courses(cp)
    _write_periods(dp)

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])

    schedules_by_period, _courses_by_id, _truncated = ctrl.generate()
    snapshot = ctrl.performance_metrics.snapshot()

    produced = sum(len(schedules) for schedules in schedules_by_period.values())
    assert produced > 0
    assert snapshot.total_generated_schedules == produced
    assert snapshot.schedules_stored_sqlite == produced
    assert snapshot.sqlite_stored_row_count == produced


def test_generate_storage_failure_deletes_partial_sqlite_store(monkeypatch, tmp_path):
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"

    _write_courses(cp)
    _write_periods(dp)

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])
    paths = []

    def fail_append_many(self, *_args, **_kwargs):
        paths.append(self.path)
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(SQLiteScheduleStore, "append_many", fail_append_many)

    with pytest.raises(RuntimeError, match="Could not store generated schedules"):
        ctrl.generate()

    assert ctrl._schedule_store is None
    assert ctrl._last_results is None
    assert paths and not paths[0].exists()


def test_generate_returns_all_period_schedules_without_truncation(tmp_path):
    """
    Three obligatory courses in the same programme + a 4-week window produces
    10,626 valid schedules.

    The current domain logic includes Fridays and excludes Saturdays only.
    In the range 05-01-2026 to 31-01-2026 there are 27 calendar days,
    4 Saturdays, and therefore 23 valid exam dates.

    With 23 valid dates and 3 mutually-conflicting courses:
    23 * 22 * 21 = 10,626 schedules.

    Since desktop generation now computes all schedules up front, generate()
    should not return truncated periods and should return all schedules.
    """
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"

    cp.write_text(
        "Calculus\n"
        "11111\n"
        "Dr. Cohen\n"
        "83101, 1, FALL, Obligatory\n"
        "Exam\n"
        "$$$$\n"
        "Algorithms\n"
        "22222\n"
        "Dr. Levi\n"
        "83101, 1, FALL, Obligatory\n"
        "Exam\n"
        "$$$$\n"
        "Physics\n"
        "33333\n"
        "Dr. Bar\n"
        "83101, 1, FALL, Obligatory\n"
        "Exam\n",
        encoding="utf-8",
    )

    dp.write_text(
        "FALL, Aleph\n"
        "05-01-2026, 31-01-2026\n",
        encoding="utf-8",
    )

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])

    schedules_by_period, _, truncated = ctrl.generate()

    assert truncated == set(), "full generation should not truncate results"

    period = ctrl.get_exam_periods()[0]
    valid_dates_count = len(period.get_valid_dates())

    # Current business rule: Friday is allowed, Saturday is excluded.
    assert valid_dates_count == 23

    expected_count = (
        valid_dates_count
        * (valid_dates_count - 1)
        * (valid_dates_count - 2)
    )

    period_key = next(iter(schedules_by_period))
    assert len(schedules_by_period[period_key]) == expected_count


# ── export ────────────────────────────────────────────────────────────────────

def test_export_writes_output_file(tmp_path):
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"
    out = tmp_path / "out.txt"

    _write_courses(cp)
    _write_periods(dp)

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])

    schedules_by_period, _, _trunc = ctrl.generate()
    ctrl.export(schedules_by_period, out)

    assert out.exists()
    assert out.stat().st_size > 0


def test_export_uses_canonical_period_order(monkeypatch, tmp_path):
    captured: dict[str, list[str]] = {}

    class _FakeTextFileExporter:
        def __init__(self, output_path, max_combinations=None):
            self.output_path = output_path
            self.max_combinations = max_combinations

        def export_schedules(self, schedules_by_period, courses_by_id):
            captured["keys"] = list(schedules_by_period)

    monkeypatch.setattr(
        "src.controller.TextFileExporter",
        _FakeTextFileExporter,
    )

    ctrl = DesktopController()
    ctrl.export(
        {
            "SUMM - Bet": [],
            "FALL - Gimel": [],
            "FALL - Aleph": [],
        },
        tmp_path / "out.txt",
        courses_by_id={},
    )

    assert captured["keys"] == [
        "FALL - Aleph",
        "FALL - Gimel",
        "SUMM - Bet",
    ]


# ── duplicate-key warning ─────────────────────────────────────────────────────

def test_merge_by_key_update_warns_on_duplicate_key(caplog):
    """
    _merge_by_key 'update' mode must log a WARNING when new_items contains
    two entries with the same key, and keep only the last occurrence.
    """
    ctrl = DesktopController()

    item1 = Course(
        id="11111",
        name="Calculus",
        instructor="Dr. Cohen",
        evaluation_type="Exam",
    )
    item2 = Course(
        id="11111",
        name="Calculus v2",
        instructor="Dr. Smith",
        evaluation_type="Exam",
    )
    existing: list = []

    with caplog.at_level(logging.WARNING, logger="src.controller"):
        ctrl._merge_by_key(
            existing,
            [item1, item2],
            mode="update",
            key_fn=lambda c: c.id,
        )

    assert any(
        "duplicate key" in record.message.lower() and "11111" in record.message
        for record in caplog.records
    )
    assert len(existing) == 1
    assert existing[0].name == "Calculus v2"  # last occurrence wins


# ── stale results / failed regeneration ───────────────────────────────────────

def test_export_is_blocked_after_dates_change_even_if_regeneration_fails(tmp_path):
    """
    Old schedules must not be exportable after exam dates changed,
    even if the next generation attempt fails.

    This is a logic test, not a UI test:
    it verifies that DesktopController keeps stale state and blocks export.
    """
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"
    out = tmp_path / "out.txt"

    _write_courses(cp)
    _write_periods(dp)

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])

    schedules_by_period, _, _ = ctrl.generate()
    assert schedules_by_period

    ctrl.mark_results_stale()
    assert ctrl.results_stale is True

    # Simulate a failed generation attempt after the date change.
    ctrl.set_selected_programs([])

    with pytest.raises(ValueError, match="No programmes selected"):
        ctrl.generate()

    # Failed generation must NOT clear stale state.
    assert ctrl.results_stale is True

    with pytest.raises(ValueError, match="Cannot export stale schedules"):
        ctrl.export(schedules_by_period, out)

    assert not out.exists()


def test_export_is_blocked_after_courses_reload(tmp_path):
    """
    Old schedules must not be exportable after courses are reloaded.

    Course data changes can change relevant offerings, course names, requirements,
    or conflicts. Therefore loading courses after a successful generation must
    mark existing results as stale and block export until regeneration succeeds.
    """
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"
    out = tmp_path / "out.txt"

    _write_courses(cp)
    _write_periods(dp)

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])

    schedules_by_period, _, _ = ctrl.generate()
    assert schedules_by_period
    assert ctrl.results_stale is False

    ctrl.load_courses(cp, mode="replace")

    assert ctrl.results_stale is True

    with pytest.raises(ValueError, match="Cannot export stale schedules"):
        ctrl.export(schedules_by_period, out)

    assert not out.exists()


def test_successful_generation_clears_stale_state(tmp_path):
    """
    If the user generates schedules successfully after dates changed,
    the new schedules are valid again and stale state should be cleared.
    """
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"

    _write_courses(cp)
    _write_periods(dp)

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])

    ctrl.mark_results_stale()
    assert ctrl.results_stale is True

    schedules_by_period, _, _ = ctrl.generate()

    assert schedules_by_period
    assert ctrl.results_stale is False


def test_export_allowed_when_results_are_not_stale(tmp_path):
    """
    Normal export should still work after a successful generation.
    This makes sure the stale guard does not break valid exports.
    """
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"
    out = tmp_path / "out.txt"

    _write_courses(cp)
    _write_periods(dp)

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])

    schedules_by_period, _, _ = ctrl.generate()

    assert ctrl.results_stale is False

    ctrl.export(schedules_by_period, out)

    assert out.exists()
    assert out.stat().st_size > 0


def test_rapid_generate_back_generate_again_does_not_corrupt_state(tmp_path):
    """
    Simulates the important state flow without PyQt UI tests:

    1. User loads data and generates schedules.
    2. User goes back and changes exam-period data.
    3. Old schedules become stale and export is blocked.
    4. User generates again.
    5. New schedules are fresh and export works.

    This protects the Config -> Generate -> Results -> Back -> Generate again
    scenario from stale-state corruption.
    """
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"
    out_old = tmp_path / "old.txt"
    out_new = tmp_path / "new.txt"

    _write_courses(cp)
    _write_periods(dp)

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])

    first_schedules, _, first_truncated = ctrl.generate()

    assert first_schedules
    assert first_truncated == set()
    assert ctrl.results_stale is False

    # Simulate user going back to the exam-period editor and changing dates.
    current_periods = ctrl.get_exam_periods()
    ctrl.update_exam_periods(current_periods)

    assert ctrl.results_stale is True

    with pytest.raises(ValueError, match="Cannot export stale schedules"):
        ctrl.export(first_schedules, out_old)

    assert not out_old.exists()

    # User generates again after returning from the results screen.
    second_schedules, _, second_truncated = ctrl.generate()

    assert second_schedules
    assert second_truncated == set()
    assert ctrl.results_stale is False

    ctrl.export(second_schedules, out_new)

    assert out_new.exists()
    assert out_new.stat().st_size > 0


# NOTE: threshold-filter-via-generate and descending-sort-via-generate (using
# the file-loaded controller path) are covered with equal/stronger assertions by
# tests/unit/test_controller_sprint3_integration.py
# ::test_generate_rejects_schedules_violating_enabled_threshold and
# ::test_generate_sorts_descending_by_active_config. The end-to-end UI-driven
# variants live in tests/e2e/test_ui_engine_stress.py.
#
# cache_generated_results / resort (C2) and the engine-level §4.4 rejection path
# (M4) live in tests/unit/test_controller_caching.py.
def test_controller_shutdown_deletes_owned_sqlite_store_and_is_idempotent(tmp_path):
    ctrl = DesktopController()
    store = SQLiteScheduleStore(tmp_path / "owned.sqlite3", delete_on_close=False)
    store.append_many("FALL - Aleph", [])
    ctrl._schedule_store = store
    ctrl._last_results = {"FALL - Aleph": store.as_sequence("FALL - Aleph")}
    db_path = store.path
    wal_path = db_path.with_name(db_path.name + "-wal")
    shm_path = db_path.with_name(db_path.name + "-shm")
    store.close(delete=False)
    wal_path.write_bytes(b"wal")
    shm_path.write_bytes(b"shm")

    ctrl.shutdown()
    ctrl.shutdown()

    assert ctrl._schedule_store is None
    assert ctrl._last_results is None
    assert not db_path.exists()
    assert not wal_path.exists()
    assert not shm_path.exists()
