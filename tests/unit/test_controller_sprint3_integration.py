"""
Integration Tests: DesktopController × Sprint 3 (thresholds + sorting)
----------------------------------------------------------------------
Proves the Sprint 3 engine logic is actually invoked by generation:
  - generate() drops schedules that violate enabled thresholds (spec 2.x)
  - generate() returns schedules ordered by the active SortingConfig (spec 3.x)
  - resort() re-ranks cached valid results WITHOUT regenerating

These fail before the controller wiring exists and pass after.
"""

from pathlib import Path

import pytest

from src.controller import DesktopController
from src.domain.settings import Settings
from src.domain.sorting import SortCriterion, SortingConfig, SortRule
from src.domain.threshold import Criterion, ThresholdEntry, ThresholdSettings


# Two mutually-conflicting mandatory courses (same program 83101, year 1),
# scheduled into a 3-day window: Mon 05 / Tue 06 / Wed 07 Jan 2026.
# 3 valid dates × 2 conflicting courses => 3 * 2 = 6 distinct schedules,
# with mandatory-gap values of either 1 or 2 days.
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
    path.write_text(
        "FALL, Aleph\n"
        "05-01-2026, 07-01-2026\n",
        encoding="utf-8",
    )


def _mandatory_gap(schedule) -> int:
    """Days between the two mandatory exams in a schedule."""
    d1 = schedule.assignments["11111"]
    d2 = schedule.assignments["22222"]
    return abs((d2 - d1).days)


def _make_controller(tmp_path: Path) -> DesktopController:
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"
    _write_two_mandatory_courses(cp)
    _write_three_day_period(dp)

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])
    return ctrl


def _all_schedules(schedules_by_period) -> list:
    period_key = next(iter(schedules_by_period))
    return schedules_by_period[period_key]


# ── threshold enforcement ─────────────────────────────────────────────────────

def test_generate_keeps_all_schedules_when_thresholds_off(tmp_path):
    ctrl = _make_controller(tmp_path)

    schedules_by_period, _, _ = ctrl.generate()

    assert len(_all_schedules(schedules_by_period)) == 6


def test_generate_rejects_schedules_violating_enabled_threshold(tmp_path):
    ctrl = _make_controller(tmp_path)
    ctrl.apply_settings(
        Settings(
            thresholds=ThresholdSettings(
                entries=(
                    ThresholdEntry(
                        Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS, enabled=True, k=2
                    ),
                )
            ),
            sorting=SortingConfig(),
        )
    )

    schedules_by_period, _, _ = ctrl.generate()
    surviving = _all_schedules(schedules_by_period)

    # Only the gap >= 2 schedules survive (2 of the original 6).
    assert len(surviving) == 2
    assert all(_mandatory_gap(s) >= 2 for s in surviving)


# ── sorting application ───────────────────────────────────────────────────────

def test_generate_sorts_descending_by_active_config(tmp_path):
    ctrl = _make_controller(tmp_path)
    ctrl.apply_settings(
        Settings(
            thresholds=ThresholdSettings(),
            sorting=SortingConfig(
                rules=(SortRule(priority=1, criterion=SortCriterion.SORT_MIN_DAYS_MANDATORY),)
            ),
        )
    )

    schedules_by_period, _, _ = ctrl.generate()
    gaps = [_mandatory_gap(s) for s in _all_schedules(schedules_by_period)]

    # Descending: each schedule's mandatory gap is >= the next one's.
    assert gaps == sorted(gaps, reverse=True)


# ── resort optimization (no regeneration) ─────────────────────────────────────

def test_resort_reorders_cached_results_without_regenerating(tmp_path):
    ctrl = _make_controller(tmp_path)

    # Initial generation with no sorting.
    schedules_by_period, _, _ = ctrl.generate()
    before = _all_schedules(schedules_by_period)

    # Re-sort only — must return the SAME schedules, re-ranked, no regeneration.
    resorted = ctrl.resort(
        SortingConfig(
            rules=(SortRule(priority=1, criterion=SortCriterion.SORT_MIN_DAYS_MANDATORY),)
        )
    )
    after = _all_schedules(resorted)

    assert len(after) == len(before)
    # Same Schedule objects re-ranked, proving no regeneration occurred.
    assert {id(s) for s in after} == {id(s) for s in before}
    gaps = [_mandatory_gap(s) for s in after]
    assert gaps == sorted(gaps, reverse=True)
    assert ctrl.results_stale is False  # re-sort does not invalidate results


def test_resort_raises_when_no_cached_results():
    ctrl = DesktopController()

    with pytest.raises(ValueError, match="[Nn]o.*results"):
        ctrl.resort(SortingConfig())
