"""
Unit Tests: SettingsScreen signal emission policy
-------------------------------------------------
The dialog must emit the narrowest signal for what actually changed:
  * nothing changed       -> no signal (avoids a redundant resort),
  * non-sorting changed   -> ``settings_changed`` only (results go stale),
  * only sorting changed   -> ``sort_order_changed`` only (resort in place).
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip(
    "PyQt6.QtWidgets",
    reason="PyQt6 native GUI libraries are not available in this environment.",
    exc_type=ImportError,
)

from src.domain.settings import Settings
from src.domain.sorting import SortCriterion, SortingConfig
from src.domain.threshold import (
    Criterion,
    ThresholdEntry,
    ThresholdSettings,
)
from src.ui.settings_screen import SettingsScreen

QApplication = QtWidgets.QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _thresholds(*, enabled: bool) -> ThresholdSettings:
    return ThresholdSettings(
        entries=(
            ThresholdEntry(
                criterion=Criterion.MAX_EXAMS_PER_DAY, enabled=enabled, k=2
            ),
        )
    )


def _sorting(*criteria: SortCriterion) -> SortingConfig:
    return SortingConfig.from_ordered_criteria(list(criteria))


def _record(dialog: SettingsScreen):
    settings_emits: list[Settings] = []
    sort_emits: list[SortingConfig] = []
    dialog.settings_changed.connect(settings_emits.append)
    dialog.sort_order_changed.connect(sort_emits.append)
    return settings_emits, sort_emits


def test_no_change_emits_nothing(qapp):
    current = Settings(_thresholds(enabled=True), _sorting(SortCriterion.SORT_AVG_DAYS_ANY))
    dialog = SettingsScreen(current)
    settings_emits, sort_emits = _record(dialog)

    dialog._emit_changes(current, current)

    assert settings_emits == []
    assert sort_emits == []


def test_threshold_change_emits_settings_only(qapp):
    current = Settings(_thresholds(enabled=True), _sorting(SortCriterion.SORT_AVG_DAYS_ANY))
    new = Settings(_thresholds(enabled=False), _sorting(SortCriterion.SORT_AVG_DAYS_ANY))
    dialog = SettingsScreen(current)
    settings_emits, sort_emits = _record(dialog)

    dialog._emit_changes(current, new)

    assert settings_emits == [new]
    assert sort_emits == []


def test_threshold_and_sorting_change_emits_settings_only(qapp):
    # Threshold edits invalidate cached results, so a plain resort is wrong even
    # when sorting also changed — only settings_changed must fire.
    current = Settings(_thresholds(enabled=True), _sorting(SortCriterion.SORT_AVG_DAYS_ANY))
    new = Settings(
        _thresholds(enabled=False),
        _sorting(SortCriterion.SORT_MIN_DAYS_MANDATORY),
    )
    dialog = SettingsScreen(current)
    settings_emits, sort_emits = _record(dialog)

    dialog._emit_changes(current, new)

    assert settings_emits == [new]
    assert sort_emits == []


def test_sorting_only_change_emits_sort_order_only(qapp):
    current = Settings(_thresholds(enabled=True), _sorting(SortCriterion.SORT_AVG_DAYS_ANY))
    new = Settings(
        _thresholds(enabled=True),
        _sorting(SortCriterion.SORT_MIN_DAYS_MANDATORY),
    )
    dialog = SettingsScreen(current)
    settings_emits, sort_emits = _record(dialog)

    dialog._emit_changes(current, new)

    assert settings_emits == []
    assert sort_emits == [new.sorting]
