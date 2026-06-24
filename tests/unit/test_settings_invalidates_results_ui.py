"""
Regression tests: threshold settings change updates the results UI immediately.

A threshold edit invalidates cached results (controller marks them stale).
ConfigScreen must emit ``results_invalidated`` so the results screen shows its
stale state right away — the user should not have to click Save/Report/Ranking
to discover the results are stale. A sorting-only change must NOT emit it.
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
QtTest = pytest.importorskip("PyQt6.QtTest", exc_type=ImportError)

from src.controller import DesktopController
from src.domain.settings import Settings
from src.domain.sorting import SortCriterion, SortingConfig
from src.domain.threshold import Criterion, ThresholdEntry, ThresholdSettings
from src.ui.config_screen import ConfigScreen
from src.ui.input_screen import InputScreen

QApplication = QtWidgets.QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _thresholds(*, k: int) -> ThresholdSettings:
    return ThresholdSettings(
        entries=(
            ThresholdEntry(criterion=Criterion.MAX_EXAMS_PER_DAY, enabled=True, k=k),
        )
    )


def _sorting(*criteria: SortCriterion) -> SortingConfig:
    return SortingConfig.from_ordered_criteria(list(criteria))


def _controller_with_results() -> DesktopController:
    ctrl = DesktopController()
    ctrl._settings = Settings(_thresholds(k=2), _sorting(SortCriterion.SORT_AVG_DAYS_ANY))
    ctrl._last_results = {"FALL_Aleph": []}
    ctrl.clear_results_stale()
    return ctrl


def test_threshold_change_emits_results_invalidated(qapp):
    ctrl = _controller_with_results()
    screen = ConfigScreen(ctrl)
    spy = QtTest.QSignalSpy(screen.results_invalidated)

    screen._on_settings_changed(
        Settings(_thresholds(k=5), _sorting(SortCriterion.SORT_AVG_DAYS_ANY))
    )

    assert ctrl.results_stale is True
    assert len(spy) == 1


def test_sorting_only_change_does_not_emit_results_invalidated(qapp):
    ctrl = _controller_with_results()
    screen = ConfigScreen(ctrl)
    spy = QtTest.QSignalSpy(screen.results_invalidated)

    screen._on_settings_changed(
        Settings(_thresholds(k=2), _sorting(SortCriterion.SORT_MIN_DAYS_MANDATORY))
    )

    assert ctrl.results_stale is False
    assert len(spy) == 0


def test_input_screen_shows_stale_state_immediately_on_threshold_change(qapp):
    ctrl = _controller_with_results()
    screen = InputScreen(ctrl)
    results = screen._results

    # Simulate a results screen showing freshly generated schedules.
    results._results_loaded = True
    results._results_panel.load({}, {}, {}, set())
    qapp.processEvents()
    assert results._results_panel._save_btn.isEnabled() is True

    # A threshold change flows: ConfigScreen -> controller (stale) -> signal ->
    # ResultsScreen.mark_stale(), with no further user action.
    screen._config._on_settings_changed(
        Settings(_thresholds(k=5), _sorting(SortCriterion.SORT_AVG_DAYS_ANY))
    )
    qapp.processEvents()

    panel = results._results_panel
    assert panel._has_stale_results is True
    # isVisibleTo reflects the widget's own shown flag without needing the
    # top-level window to be shown (offscreen tests never show it).
    assert panel._stale_banner.isVisibleTo(panel) is True
    assert panel._save_btn.isEnabled() is False
    assert panel._proctor_btn.isEnabled() is False
