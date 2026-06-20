"""
Unit tests: DesktopController schedule import + live re-sort
------------------------------------------------------------
Covers the Sprint 3 "live sort after import" fixes:

  - import_schedule() caches imported results as read-only
  - resort() after import re-renders the IMPORTED schedule (not stale generated
    results) and uses imported course metadata
  - read_only_import stays True after sorting imported results
  - generate() then import_schedule() then resort() does not reuse the previous
    generated result
"""

from datetime import date
from pathlib import Path

import pytest

from src.adapters.readers.schedule_file_reader import EmptyScheduleImportError
from src.controller import DesktopController
from src.domain.sorting import SortCriterion, SortingConfig, SortRule


# An imported, exported schedules.txt with two distinct schedules in one period.
_IMPORT_SAMPLE = """\
Schedule #1:
  [FALL - Aleph]
  - Physics 1 | Course ID: 83102 | Date: 29-01-2026 | Instructor: Prof. A

Schedule #2:
  [FALL - Aleph]
  - Physics 1 | Course ID: 83102 | Date: 30-01-2026 | Instructor: Prof. A

"""


def _write_import_file(tmp_path: Path) -> Path:
    f = tmp_path / "imported_schedules.txt"
    f.write_text(_IMPORT_SAMPLE, encoding="utf-8")
    return f


def _write_two_mandatory_courses(path: Path) -> None:
    path.write_text(
        "Calculus\n"
        "11111\n"
        "Dr. Cohen\n"
        "83101, 1, FALL, Obligatory\n"
        "Exam\n"
        "$$$$\n"
        "Algebra\n"
        "22222\n"
        "Dr. Levi\n"
        "83101, 1, FALL, Obligatory\n"
        "Exam\n",
        encoding="utf-8",
    )


def _write_three_day_period(path: Path) -> None:
    path.write_text("FALL, Aleph\n05-01-2026, 07-01-2026\n", encoding="utf-8")


def _make_generating_controller(tmp_path: Path) -> DesktopController:
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"
    _write_two_mandatory_courses(cp)
    _write_three_day_period(dp)

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])
    return ctrl


def test_import_schedule_caches_read_only_results(tmp_path):
    ctrl = DesktopController()

    imported = ctrl.import_schedule(_write_import_file(tmp_path))

    assert ctrl.read_only_import is True
    assert "FALL - Aleph" in imported.schedules_by_period
    assert len(imported.schedules_by_period["FALL - Aleph"]) == 2
    # Imported, non-stale: exportable / sortable.
    assert ctrl.results_stale is False


def test_resort_after_import_rerenders_imported_schedule(tmp_path):
    ctrl = DesktopController()
    ctrl.import_schedule(_write_import_file(tmp_path))

    config = SortingConfig(
        rules=(SortRule(priority=1, criterion=SortCriterion.SORT_AVG_DAYS_ANY),)
    )
    resorted = ctrl.resort(config)

    # Re-renders the imported period schedules, not generated ones.
    assert set(resorted) == {"FALL - Aleph"}
    dates = {s.assignments["83102"] for s in resorted["FALL - Aleph"]}
    assert dates == {date(2026, 1, 29), date(2026, 1, 30)}


def test_read_only_import_stays_true_after_resort(tmp_path):
    ctrl = DesktopController()
    ctrl.import_schedule(_write_import_file(tmp_path))

    ctrl.resort(
        SortingConfig(
            rules=(SortRule(priority=1, criterion=SortCriterion.SORT_AVG_DAYS_ANY),)
        )
    )

    assert ctrl.read_only_import is True


def test_generate_then_import_then_resort_ignores_generated_results(tmp_path):
    ctrl = _make_generating_controller(tmp_path)

    generated_by_period, _, _ = ctrl.generate()
    assert generated_by_period  # sanity: generation produced results
    assert ctrl.read_only_import is False

    # Now import a schedule with a distinct set of courses.
    ctrl.import_schedule(_write_import_file(tmp_path))
    assert ctrl.read_only_import is True

    resorted = ctrl.resort(SortingConfig())

    # Re-sort must reflect the imported schedule, never the stale generated one.
    assert set(resorted) == {"FALL - Aleph"}
    assert "83102" in resorted["FALL - Aleph"][0].assignments
    # The generated courses (11111/22222) must not leak into the resorted output.
    for schedules in resorted.values():
        for schedule in schedules:
            assert "11111" not in schedule.assignments
            assert "22222" not in schedule.assignments


def test_import_empty_file_raises_and_leaves_state_untouched(tmp_path):
    # Start from a valid imported state so we can prove it is preserved.
    ctrl = DesktopController()
    ctrl.import_schedule(_write_import_file(tmp_path))

    before_results = ctrl.resort(SortingConfig())
    before_read_only = ctrl.read_only_import
    before_courses = dict(ctrl._imported_courses_by_id)

    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")

    with pytest.raises(EmptyScheduleImportError):
        ctrl.import_schedule(empty)

    # Atomic: nothing mutated by the failed import.
    assert ctrl.read_only_import is before_read_only is True
    assert ctrl._imported_courses_by_id == before_courses
    assert ctrl.resort(SortingConfig()) == before_results


def test_import_file_with_no_schedules_raises_empty_error(tmp_path):
    ctrl = DesktopController()
    no_schedules = tmp_path / "header_only.txt"
    no_schedules.write_text("No valid schedules found.\n", encoding="utf-8")

    with pytest.raises(EmptyScheduleImportError):
        ctrl.import_schedule(no_schedules)

    # A fresh controller importing an empty file must not enter read-only mode.
    assert ctrl.read_only_import is False
    assert ctrl._imported_courses_by_id == {}


def test_failed_import_after_generation_keeps_generated_results(tmp_path):
    ctrl = _make_generating_controller(tmp_path)
    generated_by_period, _, _ = ctrl.generate()
    assert generated_by_period
    assert ctrl.read_only_import is False

    before_results = ctrl.resort(SortingConfig())

    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")

    with pytest.raises(EmptyScheduleImportError):
        ctrl.import_schedule(empty)

    # Generated results survive; no accidental read-only flip.
    assert ctrl.read_only_import is False
    assert ctrl._imported_courses_by_id == {}
    assert ctrl.resort(SortingConfig()) == before_results
