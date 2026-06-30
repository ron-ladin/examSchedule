"""
Smoke Tests: PyQt6 Desktop App
------------------------------
These tests verify that the desktop UI can be constructed without crashing and
that the main ConfigScreen controls are rendered.

They do not run schedule generation and do not test business logic.
"""

import os
import sys
from datetime import date, time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# CI installs system Qt libraries and runs these tests headless via
# QT_QPA_PLATFORM=offscreen (Python pinned to 3.11 for PyQt6 stability).
# The importorskip below only skips locally when PyQt6 is not installed.
QtWidgets = pytest.importorskip(
    "PyQt6.QtWidgets",
    reason="PyQt6 native GUI libraries are not available in this environment.",
    exc_type=ImportError,
)
QtCore = pytest.importorskip("PyQt6.QtCore", exc_type=ImportError)
QtGui = pytest.importorskip("PyQt6.QtGui", exc_type=ImportError)
QtTest = pytest.importorskip("PyQt6.QtTest", exc_type=ImportError)

QApplication = QtWidgets.QApplication
QPushButton = QtWidgets.QPushButton
QListWidget = QtWidgets.QListWidget

from src.controller import DesktopController
from src.adapters.sqlite_schedule_store import StoredScheduleList
from src.domain.classroom import Classroom
from src.domain.classroom_assignment import ClassroomAssignment
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.domain.settings import Settings
from src.domain.sorting import SortingConfig
from src.domain.threshold import Criterion, ThresholdSettings
from src.domain.time_slot import TimeSlot
from src.ui.app import ExamSchedulerApp
from src.ui.config_screen import ConfigScreen
from src.ui.exam_detail_dialog import ExamDetailDialog
from src.ui.results_panel import _ResultsPanel
from src.ui.settings_screen import SettingsScreen
from src.ui.input_screen import InputScreen, ResultsScreen
from src.ui.widgets.period_card_builder import CALENDAR_HOVER_TEXT_ROLE
from src.ui.favorite_schedules import FavoriteSchedule, schedule_fingerprint


def _get_qapp() -> QApplication:
    """Return an existing QApplication or create one for UI smoke tests."""
    app = QApplication.instance()

    if app is None:
        app = QApplication(sys.argv)

    return app


def test_app_uses_logo_png_as_window_icon():
    """Window icon should be set from logo.png, not app_icon.svg."""
    from pathlib import Path

    app = _get_qapp()
    window = ExamSchedulerApp()

    assert not window.windowIcon().isNull()
    logo_path = Path(__file__).parent.parent.parent / "src" / "ui" / "assets" / "logo.png"
    assert logo_path.exists(), "logo.png asset must exist"

    window.close()


def test_app_applies_tooltip_style_to_qapplication():
    """Qt tooltips are top-level widgets, so the app stylesheet must own them."""
    app = _get_qapp()
    window = ExamSchedulerApp()

    assert "QToolTip" in app.styleSheet()
    assert "background-color: #F8FAFC" in app.styleSheet()
    assert app.palette().toolTipBase().color().name().lower() == "#f8fafc"
    assert app.palette().toolTipText().color().name().lower() == "#172033"

    window.close()


def test_app_launches_and_uses_input_screen_as_central_widget():
    """
    The main desktop app should launch without crashing and should use
    InputScreen as the central widget.
    """
    app = _get_qapp()

    window = ExamSchedulerApp()
    window.show()
    app.processEvents()

    assert window.windowTitle() == "Syncacademic — Exam Schedule Portal"
    assert isinstance(window.centralWidget(), InputScreen)

    window.close()


def test_input_screen_starts_on_config_screen():
    """
    InputScreen should start on the configuration screen before generation.
    """
    app = _get_qapp()

    controller = DesktopController()
    screen = InputScreen(controller)
    screen.show()
    app.processEvents()

    assert screen._stacked.count() == 2
    assert screen._stacked.currentIndex() == 0
    assert isinstance(screen._config, ConfigScreen)
    assert isinstance(screen._results, ResultsScreen)

    screen.close()


def test_config_screen_initial_empty_state():
    """Full empty-state contract of a freshly built ConfigScreen: file-loading
    controls, programme-selection placeholder, optional Feature 4 controls (off
    and locked), the load-mode radio group, and the disabled Generate button.

    Consolidates several former single-widget render smoke tests; the populated
    and interactive flows are covered by tests/e2e/test_ui_engine_stress.py and
    tests/unit/test_ui_controller_integration.py.
    """
    app = _get_qapp()
    screen = ConfigScreen(DesktopController())
    screen.show()
    app.processEvents()

    # File-loading controls.
    assert isinstance(screen._files_card.courses_btn, QPushButton)
    assert screen._files_card.courses_btn.text() == "Load Courses"
    assert isinstance(screen._files_card.periods_btn, QPushButton)
    assert screen._files_card.periods_btn.text() == "Load Periods"
    assert screen._files_card.courses_label.text() == "No file loaded"
    assert screen._files_card.dates_label.text() == "No file loaded"

    # Programme-selection area (empty-state placeholder).
    assert isinstance(screen._prog_rows, dict)
    assert len(screen._prog_rows) == 0
    assert screen._prog_scroll.isVisible() is False
    assert screen._prog_placeholder.isVisible() is True
    assert "Load a courses file" in screen._prog_placeholder.text()
    assert screen._prog_count_lbl.text() == "0 / 5 selected"

    # Optional Feature 4 controls — Browse is gated on the toggle (spec §4.1);
    # slots and proctor are now QLineEdit text fields (spec §2.3.5, §2.4.4).
    from PyQt6.QtWidgets import QLineEdit
    assert screen._feature4_card._load_classrooms_btn.text() == "Browse"
    assert screen._feature4_card._load_classrooms_btn.isEnabled() is False
    assert isinstance(screen._feature4_card._slots_edit, QLineEdit)
    assert screen._feature4_card._slots_edit.isEnabled() is True
    assert isinstance(screen._feature4_card._proctors_edit, QLineEdit)
    assert screen._feature4_card._proctors_edit.isEnabled() is True
    assert screen._feature4_card._classrooms_label.text() == "Missing"
    assert screen._feature4_card._slots_label.text() == "Missing"
    assert screen._feature4_card._proctors_label.text() == "Missing"
    assert screen._feature4_card._toggle.isChecked() is False
    assert screen._feature4_card._status_lbl.text() == "DISABLED"

    # Load-mode radio group defaults to Replace.
    mode_labels = [button.text() for button in screen._mode_card.button_group.buttons()]
    assert mode_labels == ["Replace", "Update"]
    assert screen._mode_card.button_group.checkedButton().text() == "Replace"

    # Generate is visible but disabled before any data is loaded.
    assert isinstance(screen._gen_btn, QPushButton)
    assert screen._gen_btn.text() == "▶  Generate Schedule"
    assert screen._gen_btn.isEnabled() is False

    screen.close()


def test_settings_rules_can_be_combined_and_numbers_accept_keyboard_input():
    app = _get_qapp()
    dialog = SettingsScreen(Settings(ThresholdSettings(), SortingConfig()))

    first_toggle, first_input = dialog._threshold_widgets[
        Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS
    ]
    second_toggle, second_input = dialog._threshold_widgets[
        Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS
    ]

    first_toggle.click()
    second_toggle.click()

    assert first_toggle.isChecked() is True
    assert second_toggle.isChecked() is True
    assert first_input.isEnabled() is True
    assert second_input.isEnabled() is True
    assert (
        first_input.buttonSymbols()
        == QtWidgets.QAbstractSpinBox.ButtonSymbols.UpDownArrows
    )

    first_input.setFocus()
    first_input.lineEdit().selectAll()
    QtCore.QCoreApplication.sendEvent(
        first_input.lineEdit(),
        QtGui.QKeyEvent(
            QtCore.QEvent.Type.KeyPress,
            QtCore.Qt.Key.Key_5,
            QtCore.Qt.KeyboardModifier.NoModifier,
            "5",
        ),
    )
    first_input.interpretText()

    assert first_input.value() == 5

    option = QtWidgets.QStyleOptionSpinBox()
    first_input.initStyleOption(option)
    up_rect = first_input.style().subControlRect(
        QtWidgets.QStyle.ComplexControl.CC_SpinBox,
        option,
        QtWidgets.QStyle.SubControl.SC_SpinBoxUp,
        first_input,
    )
    down_rect = first_input.style().subControlRect(
        QtWidgets.QStyle.ComplexControl.CC_SpinBox,
        option,
        QtWidgets.QStyle.SubControl.SC_SpinBoxDown,
        first_input,
    )
    QtTest.QTest.mouseClick(
        first_input, QtCore.Qt.MouseButton.LeftButton, pos=up_rect.center()
    )
    assert first_input.value() == 6
    QtTest.QTest.mouseClick(
        first_input, QtCore.Qt.MouseButton.LeftButton, pos=down_rect.center()
    )
    assert first_input.value() == 5
    dialog.close()


def test_settings_changes_are_committed_only_when_save_is_clicked():
    app = _get_qapp()
    dialog = SettingsScreen(Settings(ThresholdSettings(), SortingConfig()))
    settings_spy = QtTest.QSignalSpy(dialog.settings_changed)
    sort_spy = QtTest.QSignalSpy(dialog.sort_order_changed)

    toggle, spinbox = dialog._threshold_widgets[
        Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS
    ]
    toggle.click()
    spinbox.setValue(7)
    dialog._sort_list.item(0).setCheckState(QtCore.Qt.CheckState.Checked)

    dialog.reject()
    app.processEvents()

    assert len(settings_spy) == 0
    assert len(sort_spy) == 0
    assert toggle.isChecked() is False
    assert spinbox.value() == 1
    assert dialog._sort_list.item(0).checkState() == QtCore.Qt.CheckState.Unchecked

    toggle.click()
    spinbox.setValue(7)
    dialog._sort_list.item(0).setCheckState(QtCore.Qt.CheckState.Checked)
    dialog._on_accept()
    app.processEvents()

    # Both thresholds and sorting changed. A threshold edit invalidates cached
    # results, so only settings_changed fires (which marks state stale); a plain
    # sort_order_changed resort would be wrong here.
    assert len(settings_spy) == 1
    assert len(sort_spy) == 0
    saved = settings_spy[0][0]
    saved_entry = saved.thresholds.for_criterion(
        Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS
    )
    assert saved_entry.enabled is True
    assert saved_entry.k == 7
    assert len(saved.sorting.rules) == 1


def test_results_panel_includes_standard_period_tabs_even_when_empty():
    """Results tabs should include Spring Bet and Summer periods even if no schedules exist."""
    app = _get_qapp()

    controller = DesktopController()
    panel = _ResultsPanel(controller)
    panel.load({}, {}, {}, set())
    panel.show()
    app.processEvents()

    labels = [panel._period_tabs.tabText(i) for i in range(panel._period_tabs.count())]

    assert labels == [
        "FALL — Aleph",
        "FALL — Bet",
        "FALL — Gimel",
        "SPRING — Aleph",
        "SPRING — Bet",
        "SPRING — Gimel",
        "SUMMER — Aleph",
        "SUMMER — Bet",
        "SUMMER — Gimel",
    ]

    assert panel._period_tabs.tabBar().isHidden() is True
    assert panel._period_selector.isHidden() is False
    assert [
        panel._semester_combo.itemText(i)
        for i in range(panel._semester_combo.count())
    ] == ["FALL", "SPRING", "SUMMER"]
    assert [
        panel._moed_combo.itemText(i)
        for i in range(panel._moed_combo.count())
    ] == ["Aleph", "Bet", "Gimel"]

    panel._semester_combo.setCurrentIndex(1)
    panel._moed_combo.setCurrentIndex(1)
    app.processEvents()

    assert panel._current_period_key() == "SPRI - Bet"

    panel.close()


def test_results_panel_opens_first_period_that_has_schedules():
    app = _get_qapp()
    controller = DesktopController()
    panel = _ResultsPanel(controller)
    period = ExamPeriod(
        "SPRI",
        "Bet",
        [(date(2026, 4, 10), date(2026, 4, 10))],
    )
    schedule = Schedule(period, {"10001": date(2026, 4, 10)})

    panel.load({"SPRI - Bet": [schedule]}, {}, {}, set())
    panel.show()
    app.processEvents()

    assert panel._current_period_key() == "SPRI - Bet"
    assert panel._semester_combo.currentText() == "SPRING"
    assert panel._moed_combo.currentText() == "Bet"
    assert panel._semester_combo.count() == 3
    assert panel._moed_combo.count() == 3
    assert panel._cards["SPRI - Bet"].cal_table.isVisible() is True

    panel._moed_combo.setCurrentText("Aleph")
    app.processEvents()

    assert panel._current_period_key() == "SPRI - Aleph"
    assert panel._cards["SPRI - Aleph"].empty_label.isVisible() is True
    empty_text = panel._cards["SPRI - Aleph"].empty_label.text()
    assert "No schedules were generated" in empty_text
    assert "SPRING" in empty_text
    assert "Aleph" in empty_text

    panel.close()


def test_results_panel_can_add_current_schedule_to_shortlist():
    app = _get_qapp()
    controller = DesktopController()
    panel = _ResultsPanel(controller)
    period = ExamPeriod(
        "FALL",
        "Aleph",
        [(date(2026, 1, 29), date(2026, 2, 5))],
    )
    schedules = [
        Schedule(period, {"10001": date(2026, 1, 29)}),
        Schedule(period, {"10001": date(2026, 2, 5)}),
    ]

    panel.load({"FALL - Aleph": schedules}, {}, {}, set())
    panel.show()
    app.processEvents()

    assert panel._favorites_btn.text() == "Shortlist (0)"
    assert panel._favorites_btn.isEnabled() is False

    panel._period_indices["FALL - Aleph"] = 1
    panel._refresh_period_card("FALL - Aleph")
    panel._save_visible_favorite()
    app.processEvents()

    assert len(panel._favorite_schedules) == 1
    assert panel._favorite_schedules[0].period_key == "FALL - Aleph"
    assert panel._favorite_schedules[0].signature == schedule_fingerprint(schedules[1])
    assert "Classroom choice" not in panel._favorite_schedules[0].label
    assert "Variant" not in panel._favorite_schedules[0].label
    assert panel._favorites_btn.text() == "Shortlist (1)"
    assert panel._favorites_btn.isEnabled() is True
    assert panel._save_favorite_btn.text() == "Remove from Shortlist"
    assert "#DC2626" in panel._save_favorite_btn.styleSheet()

    panel._save_current_favorite("FALL - Aleph")
    assert len(panel._favorite_schedules) == 1
    assert panel._cards["FALL - Aleph"].auto_date_btn.text() == "Auto Dates"
    assert panel._cards["FALL - Aleph"].auto_variant_btn.text() == "Auto Variants"
    assert panel._cards["FALL - Aleph"].date_jump_input.toolTip() == ""
    assert panel._cards["FALL - Aleph"].variant_jump_input.toolTip() == ""

    panel._toggle_visible_favorite()
    assert len(panel._favorite_schedules) == 0
    assert panel._favorites_btn.text() == "Shortlist (0)"
    assert panel._favorites_btn.isEnabled() is False
    assert panel._save_favorite_btn.text() == "Add to Shortlist"

    panel.close()



def test_shortlist_label_includes_classroom_choice_only_for_feature4_options():
    app = _get_qapp()
    controller = DesktopController()
    panel = _ResultsPanel(controller)
    period = ExamPeriod(
        "FALL",
        "Aleph",
        [(date(2026, 1, 29), date(2026, 1, 29))],
    )
    offering = CourseOffering("83101", 1, "FALL", "Obligatory", 30)

    def _schedule(room_id: str, slot_time: time) -> Schedule:
        assignment = ClassroomAssignment(
            exam=offering,
            room=Classroom(room_id, 40),
            slot=TimeSlot(slot_time),
            date=date(2026, 1, 29),
            students_assigned=30,
            proctor_count=2,
        )
        return Schedule(
            period,
            {"10001": date(2026, 1, 29)},
            {"10001": [assignment]},
        )

    first = _schedule("Room 101", time(9, 0))
    second = _schedule("Room 102", time(13, 0))

    panel.load({"FALL - Aleph": [first, second]}, {}, {}, set())
    panel.show()
    app.processEvents()

    panel._period_indices["FALL - Aleph"] = 1
    panel._refresh_period_card("FALL - Aleph")
    panel._save_visible_favorite()

    assert len(panel._favorite_schedules) == 1
    assert panel._favorite_schedules[0].signature == schedule_fingerprint(second)
    assert "Classroom choice 2" in panel._favorite_schedules[0].label
    assert panel._save_favorite_btn.text() == "Remove from Shortlist"

    panel.close()


def test_favorite_opens_same_schedule_after_result_ranking():
    app = _get_qapp()
    controller = DesktopController()
    panel = _ResultsPanel(controller)
    period = ExamPeriod("FALL", "Aleph", [(date(2026, 1, 1), date(2026, 1, 3))])
    first = Schedule(period, {"10001": date(2026, 1, 1)})
    favorite_schedule = Schedule(period, {"10001": date(2026, 1, 2)})
    third = Schedule(period, {"10001": date(2026, 1, 3)})

    panel.load({"FALL - Aleph": [first, favorite_schedule, third]}, {}, {}, set())
    panel._period_indices["FALL - Aleph"] = 1
    panel._save_current_favorite("FALL - Aleph")

    panel._schedules_by_period["FALL - Aleph"] = [third, first, favorite_schedule]
    panel._period_indices["FALL - Aleph"] = 0
    panel._rebuild_navigation_cache("FALL - Aleph")

    assert panel._open_favorite_at(0) is True
    assert panel._period_indices["FALL - Aleph"] == 2
    assert panel._schedules_by_period["FALL - Aleph"][2] is favorite_schedule

    panel.close()


def test_favorite_does_not_open_wrong_schedule_when_order_changes():
    app = _get_qapp()
    controller = DesktopController()
    panel = _ResultsPanel(controller)
    period = ExamPeriod("FALL", "Aleph", [(date(2026, 1, 1), date(2026, 1, 3))])
    saved = Schedule(period, {"10001": date(2026, 1, 2)})
    replacement = Schedule(period, {"10001": date(2026, 1, 3)})

    panel.load({"FALL - Aleph": [Schedule(period, {"10001": date(2026, 1, 1)}), saved]}, {}, {}, set())
    panel._period_indices["FALL - Aleph"] = 1
    panel._save_current_favorite("FALL - Aleph")

    messages = []
    panel._show_message = lambda title, text, icon: messages.append((title, text, icon))
    panel._schedules_by_period["FALL - Aleph"] = [replacement]
    panel._period_indices["FALL - Aleph"] = 0
    panel._rebuild_navigation_cache("FALL - Aleph")

    assert panel._open_favorite_at(0) is False
    assert panel._period_indices["FALL - Aleph"] == 0
    assert panel._schedules_by_period["FALL - Aleph"][0] is replacement
    assert messages and messages[0][0] == "Shortlist Option Unavailable"

    panel.close()


def test_missing_favorite_signature_shows_clear_feedback():
    app = _get_qapp()
    controller = DesktopController()
    panel = _ResultsPanel(controller)
    period = ExamPeriod("FALL", "Aleph", [(date(2026, 1, 1), date(2026, 1, 2))])
    missing = Schedule(period, {"10001": date(2026, 1, 2)})

    panel.load({"FALL - Aleph": [Schedule(period, {"10001": date(2026, 1, 1)})]}, {}, {}, set())
    panel._favorite_schedules.append(
        FavoriteSchedule(
            period_key="FALL - Aleph",
            signature=schedule_fingerprint(missing),
            label="Missing schedule",
        )
    )
    messages = []
    panel._show_message = lambda title, text, icon: messages.append((title, text, icon))

    assert panel._open_favorite_at(0) is False
    assert messages
    assert messages[0][0] == "Shortlist Option Unavailable"
    assert "no longer available" in messages[0][1]

    panel.close()
    app.processEvents()


def _panel_with_two_shortlisted_options():
    app = _get_qapp()
    controller = DesktopController()
    panel = _ResultsPanel(controller)
    period = ExamPeriod("FALL", "Aleph", [(date(2026, 1, 1), date(2026, 1, 2))])
    first = Schedule(period, {"10001": date(2026, 1, 1)})
    second = Schedule(period, {"10001": date(2026, 1, 2)})

    panel.load({"FALL - Aleph": [first, second]}, {}, {}, set())
    panel._period_indices["FALL - Aleph"] = 0
    panel._save_current_favorite("FALL - Aleph")
    panel._period_indices["FALL - Aleph"] = 1
    panel._save_current_favorite("FALL - Aleph")

    assert len(panel._favorite_schedules) == 2
    return app, controller, panel, first, second


def _capture_shortlist_export(monkeypatch, tmp_path, controller, panel):
    exported: list[dict[str, list[Schedule]]] = []
    messages = []

    monkeypatch.setattr(
        "src.ui.results_export_controller.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(tmp_path / "shortlist.txt"), "Text files (*.txt)"),
    )

    def fake_export(selected_by_period, path, courses_by_id=None):
        exported.append(selected_by_period)

    monkeypatch.setattr(controller, "export", fake_export)
    panel._show_message = lambda title, text, icon: messages.append((title, text, icon))
    return exported


def _exported_schedule_count(selected_by_period: dict[str, list[Schedule]]) -> int:
    return sum(len(schedules) for schedules in selected_by_period.values())


def test_external_export_shortlist_button_exports_all_shortlisted_options(
    monkeypatch,
    tmp_path,
):
    app, controller, panel, first, second = _panel_with_two_shortlisted_options()
    exported = _capture_shortlist_export(monkeypatch, tmp_path, controller, panel)

    panel._on_save()

    assert len(exported) == 1
    assert _exported_schedule_count(exported[0]) == 2
    exported_assignments = [
        schedule.assignments
        for schedules in exported[0].values()
        for schedule in schedules
    ]
    assert first.assignments in exported_assignments
    assert second.assignments in exported_assignments

    panel.close()
    app.processEvents()


def test_shortlist_dialog_export_button_exports_all_shortlisted_options(
    monkeypatch,
    tmp_path,
):
    app, controller, panel, first, second = _panel_with_two_shortlisted_options()
    exported = _capture_shortlist_export(monkeypatch, tmp_path, controller, panel)

    class _Signal:
        def __init__(self) -> None:
            self._callbacks = []

        def connect(self, callback) -> None:
            self._callbacks.append(callback)

        def emit(self, row: int) -> None:
            for callback in self._callbacks:
                callback(row)

    class _FavoritesList:
        def currentRow(self) -> int:
            return 0

    class _FakeFavoritesDialog:
        instance = None

        def __init__(self, favorites, parent=None) -> None:
            self.favorites = favorites
            self.parent = parent
            self.favorites_list = _FavoritesList()
            self.openRequested = _Signal()
            self.exportRequested = _Signal()
            self.deleteRequested = _Signal()
            self.accepted = False
            _FakeFavoritesDialog.instance = self

        def accept(self) -> None:
            self.accepted = True

        def exec(self) -> None:
            self.exportRequested.emit(1)

    monkeypatch.setattr(
        "src.ui.results_shortlist_controller.FavoritesDialog",
        _FakeFavoritesDialog,
    )

    panel._show_favorites_dialog()

    assert len(exported) == 1
    assert _exported_schedule_count(exported[0]) == 2
    exported_assignments = [
        schedule.assignments
        for schedules in exported[0].values()
        for schedule in schedules
    ]
    assert first.assignments in exported_assignments
    assert second.assignments in exported_assignments
    assert _FakeFavoritesDialog.instance is not None
    assert _FakeFavoritesDialog.instance.accepted is True

    panel.close()
    app.processEvents()


def test_legacy_shortlist_export_wrapper_exports_all_shortlisted_options(
    monkeypatch,
    tmp_path,
):
    app, controller, panel, first, second = _panel_with_two_shortlisted_options()
    exported = _capture_shortlist_export(monkeypatch, tmp_path, controller, panel)

    assert panel._export_favorite_at(0) is True

    assert len(exported) == 1
    assert _exported_schedule_count(exported[0]) == 2
    exported_assignments = [
        schedule.assignments
        for schedules in exported[0].values()
        for schedule in schedules
    ]
    assert first.assignments in exported_assignments
    assert second.assignments in exported_assignments

    panel.close()
    app.processEvents()


def test_legacy_shortlist_export_invalid_row_shows_missing_message(monkeypatch):
    app, controller, panel, _first, _second = _panel_with_two_shortlisted_options()
    messages = []

    monkeypatch.setattr(
        controller,
        "export",
        lambda *args, **kwargs: pytest.fail("invalid row must not export"),
    )
    panel._show_message = lambda title, text, icon: messages.append((title, text, icon))

    assert panel._export_favorite_at(-1) is False
    assert messages
    assert messages[0][0] == "Shortlist Option Unavailable"

    panel.close()
    app.processEvents()


def test_shortlist_export_rejects_positive_out_of_range_row(monkeypatch):
    app, controller, panel, _first, _second = _panel_with_two_shortlisted_options()
    messages = []

    monkeypatch.setattr(
        controller,
        "export",
        lambda *args, **kwargs: pytest.fail("out-of-range row must not export"),
    )
    panel._show_message = lambda title, text, icon: messages.append((title, text, icon))

    assert panel._export_favorite_at(10) is False
    assert messages
    assert messages[-1][0] == "Shortlist Option Unavailable"

    panel.close()
    app.processEvents()


def test_streaming_results_switch_selector_to_ready_period():
    app = _get_qapp()
    controller = DesktopController()
    panel = _ResultsPanel(controller)
    period = ExamPeriod(
        "SUMMER",
        "Gimel",
        [(date(2026, 8, 1), date(2026, 8, 1))],
    )
    schedule = Schedule(period, {"10001": date(2026, 8, 1)})

    panel.begin_streaming()
    panel.append_period({"SUMMER - Gimel": [schedule]}, {}, {}, set())
    panel.show()
    app.processEvents()

    assert isinstance(panel.get_schedules("SUMMER - Gimel"), StoredScheduleList)
    assert panel._current_period_key() == "SUMMER - Gimel"
    assert panel._semester_combo.currentText() == "SUMMER"
    assert panel._moed_combo.currentText() == "Gimel"

    panel.close()


def test_results_panel_disables_all_exports_when_stale():
    app = _get_qapp()
    panel = _ResultsPanel(DesktopController())
    panel.load({}, {}, {}, set())

    panel.mark_stale()
    app.processEvents()

    assert panel._save_btn.isEnabled() is False
    assert panel._proctor_btn.isEnabled() is False

    panel.clear_stale()

    assert panel._save_btn.isEnabled() is True
    assert panel._proctor_btn.isEnabled() is True
    panel.close()


def test_results_navigation_buttons_repeat_while_held():
    app = _get_qapp()
    period = ExamPeriod(
        "FALL",
        "Aleph",
        [(date(2026, 1, 5), date(2026, 1, 5))],
    )
    schedules = [
        Schedule(period, {"11111": date(2026, 1, 5)})
        for _ in range(3)
    ]
    panel = _ResultsPanel(DesktopController())
    panel.load({"FALL - Aleph": schedules}, {}, {}, set())
    panel.show()
    app.processEvents()

    prev_btn = panel._cards["FALL - Aleph"].prev_btn
    next_btn = panel._cards["FALL - Aleph"].next_btn

    assert prev_btn.autoRepeat() is True
    assert next_btn.autoRepeat() is True
    assert next_btn.autoRepeatDelay() == 450
    assert next_btn.autoRepeatInterval() == 120

    panel.close()


def test_results_hide_classroom_and_proctor_ui_when_feature4_was_not_used():
    app = _get_qapp()
    period = ExamPeriod(
        "FALL",
        "Aleph",
        [(date(2026, 1, 5), date(2026, 1, 5))],
    )
    offering = CourseOffering("83101", 1, "FALL", "Obligatory", 30)
    course = Course("11111", "Calculus", "Dr. Cohen", "Exam", [offering])
    schedule = Schedule(period, {"11111": date(2026, 1, 5)})

    panel = _ResultsPanel(DesktopController())
    panel.load(
        {"FALL - Aleph": [schedule]},
        {"11111": course},
        {"83101": "#7C3AED"},
        set(),
    )
    panel.show()
    app.processEvents()

    card = panel._cards["FALL - Aleph"]
    assert panel._proctor_btn.isVisible() is False
    assert card.variant_navigation.isVisible() is False
    assert card.auto_variant_btn.isVisible() is False

    dialog = ExamDetailDialog(
        date(2026, 1, 5),
        ["11111"],
        {"11111": course},
        {"83101": "#7C3AED"},
        {"11111": []},
        all_classroom_assignments={"11111": []},
    )
    table = dialog.findChild(QtWidgets.QTableWidget)
    assert table.columnCount() == 4
    assert [
        table.horizontalHeaderItem(column).text()
        for column in range(table.columnCount())
    ] == ["Course #", "Course Name", "Requirement", "Degree"]
    assert table.item(0, 0).text() == "11111"
    assert table.item(0, 1).text() == "Calculus"
    assert table.item(0, 2).text() == "Obligatory"
    assert table.item(0, 3).text().startswith("83101 -")

    dialog.close()
    panel.close()


def test_results_panel_starts_truncated_period_loading_automatically(monkeypatch):
    app = _get_qapp()
    panel = _ResultsPanel(DesktopController())
    panel._truncated_periods = {"FALL - Aleph", "FALL - Bet"}
    started = []
    monkeypatch.setattr(panel._lm, "on_load_more", started.append)

    panel._lm.start_automatic_loads()

    assert set(started) == {"FALL - Aleph", "FALL - Bet"}
    app.processEvents()
    panel.close()


def test_background_loading_control_is_hidden():
    app = _get_qapp()
    period = ExamPeriod(
        "FALL",
        "Aleph",
        [(date(2026, 1, 5), date(2026, 1, 5))],
    )
    panel = _ResultsPanel(DesktopController())
    panel._auto_load_results = False
    panel.load(
        {"FALL - Aleph": [Schedule(period, {})]},
        {},
        {},
        {"FALL - Aleph"},
    )
    panel._auto_load_results = True
    panel._refresh_period_card("FALL - Aleph")
    panel.show()
    app.processEvents()

    assert panel._cards["FALL - Aleph"].load_more_btn.isVisible() is False
    assert panel._cards["FALL - Aleph"].auto_date_btn.toolTip() == ""
    assert panel._cards["FALL - Aleph"].auto_variant_btn.toolTip() == ""
    assert hasattr(panel._cards["FALL - Aleph"].auto_date_btn, "_light_hover_help")
    assert hasattr(panel._cards["FALL - Aleph"].auto_variant_btn, "_light_hover_help")
    panel.close()


def test_group_exams_by_slot_orders_slots_and_flags_collapse():
    """Spec §4.5: same-date exams group by slot, chronological, >3 collapse."""
    from datetime import time as _time

    from src.ui.calendar_cell_delegate import _slot_group_heading
    from src.ui.results_panel import _group_exams_by_slot

    def _assign(t):
        offering = CourseOffering("83101", 1, "FALL", "Obligatory", 10)
        return ClassroomAssignment(
            exam=offering,
            room=Classroom("R", 50),
            slot=TimeSlot(t),
            date=date(2026, 1, 5),
            students_assigned=10,
            proctor_count=1,
        )

    # 13:00 has 4 exams (collapses); 09:00 has 1 exam.
    assignments = {
        "A": [_assign(_time(13, 0))],
        "B": [_assign(_time(13, 0))],
        "C": [_assign(_time(13, 0))],
        "D": [_assign(_time(13, 0))],
        "E": [_assign(_time(9, 0))],
    }
    schedule = Schedule(
        ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 5))]),
        {cid: date(2026, 1, 5) for cid in assignments},
        assignments,
    )
    courses = {
        cid: Course(
            cid,
            f"Course {cid}",
            "Dr. Test",
            "Exam",
            [CourseOffering("83101", 1, "FALL", "Obligatory", 10)],
        )
        for cid in assignments
    }

    groups = _group_exams_by_slot(list(assignments), schedule, courses)

    assert [g["slot"] for g in groups] == ["09:00", "13:00"]
    assert groups[0]["collapsed"] is False
    assert groups[1]["collapsed"] is True
    assert len(groups[1]["course_ids"]) == 4
    assert _slot_group_heading(groups[0]) == "09:00 · 1 exam"
    assert _slot_group_heading(groups[1]) == "13:00 · 4 exams"


def test_calendar_cell_clicks_can_open_full_day_slot_or_single_exam():
    from src.ui.calendar_cell_delegate import _course_ids_for_click_position

    groups = [
        {
            "slot": "09:00",
            "has_slot": True,
            "course_ids": ["11111", "22222"],
            "names": ["Calculus", "Database Systems"],
            "collapsed": False,
        }
    ]
    rect = QtCore.QRect(0, 0, 150, 120)

    assert _course_ids_for_click_position(groups, rect, QtCore.QPoint(10, 10)) is None
    assert _course_ids_for_click_position(groups, rect, QtCore.QPoint(10, 30)) == [
        "11111",
        "22222",
    ]
    assert _course_ids_for_click_position(groups, rect, QtCore.QPoint(10, 42)) == [
        "11111"
    ]
    assert _course_ids_for_click_position(groups, rect, QtCore.QPoint(10, 55)) == [
        "22222"
    ]


def test_feature4_room_and_slot_are_visible_in_calendar_and_detail_dialog():
    app = _get_qapp()
    period = ExamPeriod(
        "FALL",
        "Aleph",
        [(date(2026, 1, 5), date(2026, 1, 5))],
    )
    offering = CourseOffering("83101", 1, "FALL", "Obligatory", 30)
    course = Course("11111", "Calculus", "Dr. Cohen", "Exam", [offering])
    room_assignment = ClassroomAssignment(
        exam=offering,
        room=Classroom("Room 101", 40),
        slot=TimeSlot(time(9, 0)),
        date=date(2026, 1, 5),
        students_assigned=30,
        proctor_count=2,
    )
    schedule = Schedule(
        period,
        {"11111": date(2026, 1, 5)},
        {"11111": [room_assignment]},
    )
    controller = DesktopController()
    controller.update_exam_periods([period])
    panel = _ResultsPanel(controller)
    panel.load(
        {"FALL - Aleph": [schedule]},
        {"11111": course},
        {"83101": "#7C3AED"},
        set(),
    )
    panel.show()
    app.processEvents()

    assert panel._proctor_btn.isVisible() is True
    assert panel._cards["FALL - Aleph"].variant_navigation.isVisible() is True
    calendar_text = panel._cards["FALL - Aleph"].cal_table.item(0, 1).text()
    assert "09:00" in calendar_text
    assert "Room 101 (30/40)" in calendar_text
    assert "Degree: 83101 -" in calendar_text

    dialog = ExamDetailDialog(
        date(2026, 1, 5),
        ["11111"],
        {"11111": course},
        {"83101": "#7C3AED"},
        {"11111": [room_assignment]},
    )
    table = dialog.findChild(QtWidgets.QTableWidget)
    assert table.horizontalHeaderItem(2).text() == "Time Slot"
    assert table.horizontalHeaderItem(3).text() == "Building"
    assert table.horizontalHeaderItem(4).text() == "Room"
    assert table.horizontalHeaderItem(5).text() == "Students"
    assert table.horizontalHeaderItem(6).text() == "Room Capacity"
    assert table.horizontalHeaderItem(7).text() == "Status"
    assert table.horizontalHeaderItem(10).text() == "Proctors"
    assert table.columnCount() == 11
    assert table.item(0, 2).text() == "09:00"
    assert table.item(0, 3).text() == "—"
    assert table.item(0, 4).text() == "Room 101"
    assert table.item(0, 5).text() == "30"
    assert table.item(0, 6).text() == "40"
    assert table.item(0, 7).text() == "FULL"
    assert table.item(0, 9).text().startswith("83101 -")
    assert table.item(0, 10).text() == "2"
    assert dialog.windowFlags() & QtCore.Qt.WindowType.WindowMinMaxButtonsHint

    dialog.close()
    panel.close()


def test_exam_detail_dialog_can_expand_from_selected_exam_to_all_date_exams():
    app = _get_qapp()
    courses = {
        course_id: Course(
            course_id,
            name,
            "Dr. Test",
            "Exam",
            [CourseOffering("83101", 1, "FALL", "Obligatory", 30)],
        )
        for course_id, name in [
            ("11111", "Calculus"),
            ("22222", "Physics"),
        ]
    }
    dialog = ExamDetailDialog(
        date(2026, 1, 5),
        ["11111"],
        courses,
        {"83101": "#7C3AED"},
        all_course_ids=["11111", "22222"],
    )
    table = dialog.findChild(QtWidgets.QTableWidget)
    show_all_btn = dialog.findChild(
        QtWidgets.QPushButton, "showAllExamsButton"
    )

    assert table.rowCount() == 1
    assert show_all_btn is not None

    show_all_btn.click()
    app.processEvents()

    assert table.rowCount() == 2
    assert dialog._count_lbl.text() == "2 exams scheduled"
    assert show_all_btn.isHidden() is True
    dialog.close()


def test_unassigned_feature4_exam_is_visible_in_calendar_and_detail_dialog():
    app = _get_qapp()
    period = ExamPeriod(
        "FALL",
        "Aleph",
        [(date(2026, 1, 5), date(2026, 1, 5))],
    )
    offering = CourseOffering("83101", 1, "FALL", "Obligatory", 50)
    course = Course("11111", "Calculus", "Dr. Cohen", "Exam", [offering])
    schedule = Schedule(
        period,
        {"11111": date(2026, 1, 5)},
        {"11111": []},
        {"11111": 50},
    )
    controller = DesktopController()
    controller.update_exam_periods([period])
    panel = _ResultsPanel(controller)
    panel.load(
        {"FALL - Aleph": [schedule]},
        {"11111": course},
        {"83101": "#7C3AED"},
        set(),
    )
    panel.show()
    app.processEvents()

    calendar_text = panel._cards["FALL - Aleph"].cal_table.item(0, 1).text()
    assert "NO CLASSROOM" in calendar_text
    assert "50 students" in calendar_text

    dialog = ExamDetailDialog(
        date(2026, 1, 5),
        ["11111"],
        {"11111": course},
        {"83101": "#7C3AED"},
        {"11111": []},
        {"11111": 50},
    )
    table = dialog.findChild(QtWidgets.QTableWidget)
    assert table.item(0, 4).text() == "NO CLASSROOM"
    assert table.item(0, 5).text() == "50"
    assert table.item(0, 6).text() == "0"
    assert table.item(0, 7).text() == "UNASSIGNED"

    dialog.close()
    panel.close()


def test_calendar_program_backgrounds_are_soft_enough_for_warm_colours():
    app = _get_qapp()
    period = ExamPeriod(
        "FALL",
        "Aleph",
        [(date(2026, 1, 5), date(2026, 1, 5))],
    )
    offering = CourseOffering("83109", 1, "FALL", "Obligatory", 50)
    course = Course("10004", "Advanced Materials", "Dr. Cohen", "Exam", [offering])
    schedule = Schedule(period, {"10004": date(2026, 1, 5)})
    controller = DesktopController()
    controller.update_exam_periods([period])
    panel = _ResultsPanel(controller)

    panel.load(
        {"FALL - Aleph": [schedule]},
        {"10004": course},
        {"83109": "#F59E0B"},
        set(),
    )
    panel.show()
    app.processEvents()

    item = panel._cards["FALL - Aleph"].cal_table.item(0, 1)
    assert item.background().color().alpha() == 32
    assert item.toolTip() == ""
    assert "click to view details" in item.data(CALENDAR_HOVER_TEXT_ROLE)

    panel.close()

def test_edit_exam_periods_dialog_does_not_add_missing_periods_to_controller_until_edited():
    """
    Missing standard periods should be displayed in the Edit Exam Periods dialog
    as UI-only tabs.

    Opening the dialog alone must not add synthetic periods into the controller.
    """
    app = _get_qapp()

    controller = DesktopController()
    controller.update_exam_periods([
        ExamPeriod("FALL", "Aleph", [(date(2026, 1, 29), date(2026, 2, 5))]),
    ])

    from src.ui.config_screen import ExamPeriodsEditorDialog

    dialog = ExamPeriodsEditorDialog(controller)
    dialog.show()
    app.processEvents()

    tabs = dialog.findChild(QtWidgets.QTabWidget)
    labels = [tabs.tabText(i) for i in range(tabs.count())]

    assert labels == [
        "FALL — Aleph",
        "FALL — Bet",
        "FALL — Gimel",
        "SPRING — Aleph",
        "SPRING — Bet",
        "SPRING — Gimel",
        "SUMMER — Aleph",
        "SUMMER — Bet",
        "SUMMER — Gimel",
    ]

    # Important logic assertion:
    # opening the UI must not pollute controller state.
    assert [period.get_key() for period in controller.get_exam_periods()] == [
        "FALL - Aleph"
    ]

    dialog.close()


def test_editing_synthetic_exam_period_tab_adds_it_to_controller():
    """
    A missing standard period should be added to the controller only after the
    user defines dates for that synthetic tab and edits it.
    """
    app = _get_qapp()

    controller = DesktopController()
    controller.update_exam_periods([
        ExamPeriod("FALL", "Aleph", [(date(2026, 1, 29), date(2026, 2, 5))]),
    ])

    from src.ui.config_screen import ExamPeriodsEditorDialog
    from src.ui.date_editor import DateEditorWidget

    dialog = ExamPeriodsEditorDialog(controller)
    dialog.show()
    app.processEvents()

    tabs = dialog.findChild(QtWidgets.QTabWidget)
    labels = [tabs.tabText(i) for i in range(tabs.count())]

    spring_bet_index = labels.index("SPRING — Bet")
    missing_tab = tabs.widget(spring_bet_index)

    # Missing periods are first shown as a wrapper with a Define button.
    define_btn = None
    for btn in missing_tab.findChildren(QtWidgets.QPushButton):
        if "Define exam period dates" in btn.text():
            define_btn = btn
            break

    assert define_btn is not None

    # Simulate the user defining dates for the missing period.
    define_btn.click()
    app.processEvents()

    editor = tabs.widget(spring_bet_index)

    assert isinstance(editor, DateEditorWidget)

    # Simulate a user edit on the newly activated real editor.
    editor._on_day_toggled(date.today())
    app.processEvents()

    period_keys = [period.get_key() for period in controller.get_exam_periods()]

    assert "FALL - Aleph" in period_keys
    assert "SPRI - Bet" in period_keys
    assert len(period_keys) == 2

    dialog.close()
