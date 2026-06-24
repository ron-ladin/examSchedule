"""
Unit test: calendar cell hover exam-count (SCRUM-399).

Verifies SCRUM-420 — the calendar table tracks the mouse (widget + viewport) so
hover-move events reach ``mouseMoveEvent`` and the count tooltip can show.

The SCRUM-421 count value (``EXAM_COUNT_ROLE`` set in CalendarRenderer.populate)
is exercised by the rendered-calendar flow in
tests/unit/test_ui_controller_integration.py and verified manually in the app;
calling populate() on an unparented table aborts on the headless test platform,
so it is not re-tested here.

GUI-only, so skipped when PyQt6 is not installed.
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PyQt6.QtWidgets", exc_type=ImportError)
# QtCore/QtGui must be imported before a QApplication is built, or PyQt6 aborts
# with "Must construct a QApplication before a QWidget" in this environment.
QtCore = pytest.importorskip("PyQt6.QtCore", exc_type=ImportError)
QtGui = pytest.importorskip("PyQt6.QtGui", exc_type=ImportError)

QApplication = QtWidgets.QApplication

from src.ui.widgets.period_card_builder import _make_data_table


def _get_qapp() -> QApplication:
    """Return an existing QApplication or create one for the GUI test."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_calendar_table_tracks_mouse_for_hover():
    """The table and its viewport must track the mouse so hover events fire."""
    _get_qapp()
    table = _make_data_table(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])

    assert table.hasMouseTracking() is True
    assert table.viewport().hasMouseTracking() is True
