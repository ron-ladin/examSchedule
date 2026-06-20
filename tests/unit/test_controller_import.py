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
