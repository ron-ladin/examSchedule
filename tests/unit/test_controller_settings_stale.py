"""
Regression tests: threshold changes invalidate generated results.

When the user edits THRESHOLD rules after generating schedules, the cached
results may no longer satisfy the new rules. DesktopController.apply_settings()
must mark those results stale (and drop them) so they cannot be exported as if
still valid. A sorting-only change must NOT invalidate results — they are simply
re-ranked in place.
"""

from pathlib import Path

import pytest

from src.controller import DesktopController
from src.domain.settings import Settings
from src.domain.sorting import SortCriterion, SortingConfig
from src.domain.threshold import (
    Criterion,
    ThresholdEntry,
    ThresholdSettings,
)


def _thresholds(*, k: int) -> ThresholdSettings:
    return ThresholdSettings(
        entries=(
            ThresholdEntry(criterion=Criterion.MAX_EXAMS_PER_DAY, enabled=True, k=k),
        )
    )


def _sorting(*criteria: SortCriterion) -> SortingConfig:
    return SortingConfig.from_ordered_criteria(list(criteria))


def _controller_with_results() -> DesktopController:
    """A controller holding fresh (non-stale) generated results."""
    ctrl = DesktopController()
    ctrl._settings = Settings(
        _thresholds(k=2), _sorting(SortCriterion.SORT_AVG_DAYS_ANY)
    )
    ctrl._last_results = {"FALL_Aleph": []}
    ctrl.clear_results_stale()
    return ctrl


def test_threshold_change_marks_results_stale():
    ctrl = _controller_with_results()
    assert ctrl.results_stale is False

    ctrl.apply_settings(
        Settings(_thresholds(k=5), _sorting(SortCriterion.SORT_AVG_DAYS_ANY))
    )

    assert ctrl.results_stale is True
    # Stale results are dropped so nothing downstream can re-rank or export them.
    assert ctrl._last_results is None


def test_threshold_change_blocks_export():
    ctrl = _controller_with_results()
    ctrl.apply_settings(
        Settings(_thresholds(k=5), _sorting(SortCriterion.SORT_AVG_DAYS_ANY))
    )

    with pytest.raises(ValueError, match="stale"):
        ctrl.export({"FALL_Aleph": []}, Path("/tmp/should_not_write.txt"))


def test_threshold_change_blocks_resort_until_regeneration():
    ctrl = _controller_with_results()
    ctrl.apply_settings(
        Settings(_thresholds(k=5), _sorting(SortCriterion.SORT_AVG_DAYS_ANY))
    )

    # Cached results were dropped, so an in-place resort is no longer possible.
    with pytest.raises(ValueError, match="No results to re-sort"):
        ctrl.resort(_sorting(SortCriterion.SORT_MIN_DAYS_MANDATORY))


def test_sorting_only_change_does_not_invalidate_results():
    ctrl = _controller_with_results()

    ctrl.apply_settings(
        Settings(_thresholds(k=2), _sorting(SortCriterion.SORT_MIN_DAYS_MANDATORY))
    )

    assert ctrl.results_stale is False
    assert ctrl._last_results is not None


def test_sorting_only_change_still_resorts_without_regeneration():
    ctrl = _controller_with_results()
    ctrl._last_results = {"FALL_Aleph": []}
    ctrl.clear_results_stale()

    resorted = ctrl.resort(_sorting(SortCriterion.SORT_MIN_DAYS_MANDATORY))

    # Resort succeeds in place (no exception, results not stale) — proving a
    # sorting change never forces regeneration.
    assert ctrl.results_stale is False
    assert resorted == {"FALL_Aleph": []}


def test_unchanged_settings_keep_results_fresh():
    ctrl = _controller_with_results()
    same = Settings(_thresholds(k=2), _sorting(SortCriterion.SORT_AVG_DAYS_ANY))

    ctrl.apply_settings(same)

    assert ctrl.results_stale is False
    assert ctrl._last_results is not None
