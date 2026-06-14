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
from src.domain.time_slot import TimeSlot
from src.ui.app import ExamSchedulerApp
from src.ui.config_screen import ConfigScreen
from src.ui.exam_detail_dialog import ExamDetailDialog
from src.ui.results_panel import _ResultsPanel
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


def test_config_screen_renders_file_loading_controls():
    """
    ConfigScreen should render the file-loading controls required for the
    desktop flow: courses, exam periods, and programs.
    """
    app = _get_qapp()

    controller = DesktopController()
    screen = ConfigScreen(controller)
    screen.show()
    app.processEvents()

    assert isinstance(screen._load_courses_btn, QPushButton)
    assert screen._load_courses_btn.text() == "Load Courses"

    assert isinstance(screen._load_periods_btn, QPushButton)
    assert screen._load_periods_btn.text() == "Load Periods"

    assert screen._courses_label.text() == "No file loaded"
    assert screen._dates_label.text() == "No file loaded"

    screen.close()


def test_config_screen_renders_programme_selection_area():
    """
    ConfigScreen should render the programme-selection area and show the initial
    empty-state placeholder before files are loaded.
    """
    app = _get_qapp()

    controller = DesktopController()
    screen = ConfigScreen(controller)
    screen.show()
    app.processEvents()

    assert isinstance(screen._prog_rows, dict)
    assert len(screen._prog_rows) == 0
    assert screen._prog_scroll.isVisible() is False

    assert screen._prog_placeholder.isVisible() is True
    assert "Load a courses file" in screen._prog_placeholder.text()

    assert screen._prog_count_lbl.text() == "0 / 5 selected"

    screen.close()


def test_config_screen_renders_optional_feature4_controls():
    app = _get_qapp()
    screen = ConfigScreen(DesktopController())
    screen.show()
    app.processEvents()

    # Spec 4.1: Browse button for classrooms, text inputs for slots + ratio.
    assert screen._load_classrooms_btn.text() == "Load Classrooms"
    assert screen._slots_input.placeholderText().startswith("e.g.")
    assert screen._proctors_input.placeholderText().startswith("e.g.")
    assert screen._classrooms_label.text() == "Missing"
    assert screen._slots_label.text() == "Missing"
    assert screen._proctors_label.text() == "Missing"

    # Toggle starts off, so the feature is disabled and inputs are locked.
    assert screen._feature4_toggle.isChecked() is False
    assert screen._feature4_status.text() == "DISABLED"
    assert screen._slots_input.isEnabled() is False
    assert screen._proctors_input.isEnabled() is False

    screen.close()


def test_config_screen_renders_generate_button_disabled_initially():
    """
    Generate should be visible but disabled before courses, periods, and at
    least one programme are loaded/selected.
    """
    app = _get_qapp()

    controller = DesktopController()
    screen = ConfigScreen(controller)
    screen.show()
    app.processEvents()

    assert isinstance(screen._gen_btn, QPushButton)
    assert screen._gen_btn.text() == "▶  Generate Schedule"
    assert screen._gen_btn.isEnabled() is False

    screen.close()


def test_config_screen_renders_load_mode_controls():
    """
    ConfigScreen should expose the supported load modes and default to Replace.
    """
    app = _get_qapp()

    controller = DesktopController()
    screen = ConfigScreen(controller)
    screen.show()
    app.processEvents()

    mode_labels = [button.text() for button in screen._mode_group.buttons()]

    assert mode_labels == ["Replace", "Update"]
    assert screen._mode_group.checkedButton().text() == "Replace"

    screen.close()


def test_edit_exam_periods_dialog_adds_missing_standard_period_tabs():
    """Editing periods should show all required semester/moed tabs without changing dates.txt."""
    app = _get_qapp()

    controller = DesktopController()
    controller.update_exam_periods([
        ExamPeriod("FALL", "Aleph", [(date(2026, 1, 29), date(2026, 2, 5))]),
        ExamPeriod("FALL", "Bet", [(date(2026, 4, 10), date(2026, 4, 13))]),
        ExamPeriod("SPRI", "Aleph", [(date(2026, 7, 1), date(2026, 7, 10))]),
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

    dialog.close()


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

    prev_btn = panel._prev_btns["FALL - Aleph"]
    next_btn = panel._next_btns["FALL - Aleph"]

    assert prev_btn.autoRepeat() is True
    assert next_btn.autoRepeat() is True
    assert next_btn.autoRepeatDelay() == 450
    assert next_btn.autoRepeatInterval() == 120

    panel.close()


def test_results_panel_starts_truncated_period_loading_automatically(monkeypatch):
    app = _get_qapp()
    panel = _ResultsPanel(DesktopController())
    panel._truncated_periods = {"FALL - Aleph", "FALL - Bet"}
    started = []
    monkeypatch.setattr(panel, "_on_load_more", started.append)

    panel._start_automatic_loads()

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

    assert panel._load_more_btns["FALL - Aleph"].isVisible() is False
    panel.close()


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

    calendar_text = panel._cal_tables["FALL - Aleph"].item(0, 1).text()
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
    assert table.item(0, 2).text() == "09:00"
    assert table.item(0, 3).text() == "—"
    assert table.item(0, 4).text() == "Room 101"
    assert table.item(0, 5).text() == "30"
    assert table.item(0, 6).text() == "40"
    assert table.item(0, 7).text() == "AVAILABLE"
    assert table.item(0, 9).text().startswith("83101 -")
    assert dialog.windowFlags() & QtCore.Qt.WindowType.WindowMinMaxButtonsHint

    dialog.close()
    panel.close()


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

    calendar_text = panel._cal_tables["FALL - Aleph"].item(0, 1).text()
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
