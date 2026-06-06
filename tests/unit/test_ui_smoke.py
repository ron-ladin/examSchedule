"""
Smoke Tests: PyQt6 Desktop App
------------------------------
These tests verify that the desktop UI can be constructed without crashing and
that the main ConfigScreen controls are rendered.

They do not run schedule generation and do not test business logic.
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

QApplication = QtWidgets.QApplication
QPushButton = QtWidgets.QPushButton
QListWidget = QtWidgets.QListWidget

from src.controller import DesktopController
from src.ui.app import ExamSchedulerApp
from src.ui.config_screen import ConfigScreen
from src.ui.input_screen import InputScreen, ResultsScreen


def _get_qapp() -> QApplication:
    """Return an existing QApplication or create one for UI smoke tests."""
    app = QApplication.instance()

    if app is None:
        app = QApplication(sys.argv)

    return app


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
    assert screen._programs_label.text() == "No file loaded"

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
    assert "Load a courses or programs file" in screen._prog_placeholder.text()

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
