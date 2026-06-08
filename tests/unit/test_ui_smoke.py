"""
Smoke Tests: PyQt6 Desktop App
------------------------------
These tests verify that the desktop UI can be constructed without crashing and
that the main ConfigScreen controls are rendered.

They do not run schedule generation and do not test business logic.
"""

import os
import sys
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip(
    "PyQt6.QtWidgets",
    reason="PyQt6 native GUI libraries are not available in this environment.",
    exc_type=ImportError,
)

QApplication = QtWidgets.QApplication
QPushButton = QtWidgets.QPushButton
QListWidget = QtWidgets.QListWidget

from src.controller import DesktopController
from src.domain.exam_period import ExamPeriod
from src.ui.app import ExamSchedulerApp
from src.ui.config_screen import ConfigScreen
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

    assert isinstance(screen._prog_list, QListWidget)
    assert screen._prog_list.count() == 0
    assert screen._prog_list.isVisible() is False

    assert screen._prog_placeholder.isVisible() is True
    assert "Load a courses file" in screen._prog_placeholder.text()

    assert screen._prog_count_lbl.text() == "0 / 5 selected"

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
