"""
Shared PyQt6 setup for desktop UI smoke tests.

Forces the offscreen platform, skips cleanly when PyQt6 is unavailable, and
exposes the Qt modules plus a QApplication accessor. Importing this module
performs the importorskip, so a test module that imports it is skipped whole
when the native GUI libraries are missing.
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
QtCore = pytest.importorskip("PyQt6.QtCore", exc_type=ImportError)
QtGui = pytest.importorskip("PyQt6.QtGui", exc_type=ImportError)
QtTest = pytest.importorskip("PyQt6.QtTest", exc_type=ImportError)


def _get_qapp() -> "QtWidgets.QApplication":
    """Return an existing QApplication or create one for UI smoke tests."""
    app = QtWidgets.QApplication.instance()

    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    return app
