"""
Regression tests: ResultsPanel honours controller stale state.

After a THRESHOLD settings change the controller marks results stale, but the
panel's own flag may not have been set. The panel must still treat the displayed
schedules as stale (via _is_stale) so Save, Proctor Report, and Result Ranking
are all blocked immediately — and a sorting-only change must NOT block them.
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

from src.controller import DesktopController
from src.domain.settings import Settings
from src.domain.sorting import SortCriterion, SortingConfig
from src.domain.threshold import Criterion, ThresholdEntry, ThresholdSettings
from src.ui.results_panel import _ResultsPanel

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


def _panel_with_results(ctrl: DesktopController, qapp) -> _ResultsPanel:
    panel = _ResultsPanel(ctrl)
    panel.load({}, {}, {}, set())
    qapp.processEvents()
    return panel


def _capture_messages(panel: _ResultsPanel) -> list[tuple]:
    messages: list[tuple] = []
    panel._show_message = lambda *args, **kwargs: messages.append(args)
    return messages


def _make_threshold_change(ctrl: DesktopController) -> None:
    ctrl.apply_settings(
        Settings(_thresholds(k=5), _sorting(SortCriterion.SORT_AVG_DAYS_ANY))
    )


def test_panel_is_stale_when_controller_stale(qapp):
    ctrl = _controller_with_results()
    panel = _panel_with_results(ctrl, qapp)
    try:
        assert panel._is_stale() is False

        _make_threshold_change(ctrl)

        assert ctrl.results_stale is True
        # Panel's own flag was never set, yet it still reports stale via the controller.
        assert panel._has_stale_results is False
        assert panel._is_stale() is True
    finally:
        panel.close()


def test_save_blocked_immediately_after_threshold_change(qapp):
    ctrl = _controller_with_results()
    panel = _panel_with_results(ctrl, qapp)
    original_dialog = QtWidgets.QFileDialog.getSaveFileName
    try:
        _make_threshold_change(ctrl)
        messages = _capture_messages(panel)

        called = []
        panel._controller.export = lambda *a, **k: called.append(True)
        monkey_dialog = lambda *a, **k: called.append("dialog")
        QtWidgets.QFileDialog.getSaveFileName = staticmethod(monkey_dialog)

        panel._on_save()

        assert called == []  # neither the save dialog nor export ran
        assert messages and messages[0][0] == "Stale Schedules"
    finally:
        QtWidgets.QFileDialog.getSaveFileName = original_dialog
        panel.close()


def test_proctor_report_blocked_when_only_controller_stale(qapp):
    ctrl = _controller_with_results()
    panel = _panel_with_results(ctrl, qapp)
    try:
        _make_threshold_change(ctrl)
        messages = _capture_messages(panel)
        assert panel._has_stale_results is False  # only the controller is stale

        panel._on_proctor_report()

        assert messages and messages[0][0] == "Stale Schedules"
    finally:
        panel.close()


def test_result_ranking_blocked_when_controller_stale(qapp):
    ctrl = _controller_with_results()
    panel = _panel_with_results(ctrl, qapp)
    try:
        _make_threshold_change(ctrl)
        messages = _capture_messages(panel)

        panel._on_result_ranking()

        assert messages and messages[0][0] == "Stale Schedules"
    finally:
        panel.close()


def test_sorting_only_change_does_not_mark_panel_stale(qapp):
    ctrl = _controller_with_results()
    panel = _panel_with_results(ctrl, qapp)
    try:
        ctrl.apply_settings(
            Settings(_thresholds(k=2), _sorting(SortCriterion.SORT_MIN_DAYS_MANDATORY))
        )

        assert ctrl.results_stale is False
        assert panel._is_stale() is False
    finally:
        panel.close()


def test_active_scheduling_limits_show_enabled_thresholds_only(qapp):
    ctrl = DesktopController()
    ctrl.apply_settings(
        Settings(
            ThresholdSettings(
                entries=(
                    ThresholdEntry(
                        criterion=Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS,
                        enabled=True,
                        k=3,
                    ),
                    ThresholdEntry(
                        criterion=Criterion.MAX_EXAMS_PER_DAY,
                        enabled=False,
                        k=2,
                    ),
                )
            ),
            _sorting(),
        )
    )
    panel = _ResultsPanel(ctrl)
    try:
        panel.load({}, {}, {}, set())
        qapp.processEvents()

        assert panel._limits_panel.isHidden() is False
        assert panel._limits_toggle.text() == "Active scheduling limits (1)"
        assert panel._limits_details.isHidden() is True
        assert "Any exam gap: at least 3 day(s)" in panel._limits_details.text()
        assert "Exams per day" not in panel._limits_details.text()

        panel._limits_toggle.setChecked(True)
        qapp.processEvents()

        assert panel._limits_details.isHidden() is False
    finally:
        panel.close()


def test_active_scheduling_limits_hidden_when_no_rules_enabled(qapp):
    ctrl = DesktopController()
    ctrl.apply_settings(
        Settings(
            ThresholdSettings(
                entries=(
                    ThresholdEntry(
                        criterion=Criterion.MAX_EXAMS_PER_DAY,
                        enabled=False,
                        k=2,
                    ),
                )
            ),
            _sorting(),
        )
    )
    panel = _ResultsPanel(ctrl)
    try:
        panel.load({}, {}, {}, set())
        qapp.processEvents()

        assert panel._limits_panel.isHidden() is True
    finally:
        panel.close()


def test_active_scheduling_limits_use_generation_snapshot(qapp):
    ctrl = DesktopController()
    ctrl.apply_settings(Settings(_thresholds(k=2), _sorting()))
    panel = _ResultsPanel(ctrl)
    try:
        panel.load({}, {}, {}, set())
        ctrl.apply_settings(Settings(_thresholds(k=5), _sorting()))
        panel._refresh_active_limits_panel()

        assert "at most 2 exam(s)" in panel._limits_details.text()
        assert "at most 5 exam(s)" not in panel._limits_details.text()
    finally:
        panel.close()
