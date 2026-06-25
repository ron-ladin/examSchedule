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
        "SPRING — Aleph",
        "SPRING — Bet",
        "SUMMER — Aleph",
        "SUMMER — Bet",
    ]

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
        "SPRING — Aleph",
        "SPRING — Bet",
        "SUMMER — Aleph",
        "SUMMER — Bet",
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
