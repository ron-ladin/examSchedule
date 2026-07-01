"""
Main Application Window
------------------------
ExamSchedulerApp — thin QMainWindow that owns the DesktopController and
sets InputScreen as its single central widget.

Usage (from main.py):
    app  = QApplication(sys.argv)
    win  = ExamSchedulerApp()
    win.show()
    sys.exit(app.exec())
"""

import logging
from pathlib import Path

from PyQt6.QtGui import QColor, QIcon, QPalette
from PyQt6.QtWidgets import QApplication, QMainWindow

from src.controller import DesktopController
from src.ui.input_screen import InputScreen
from src.ui.style import QSS

logger = logging.getLogger(__name__)


class ExamSchedulerApp(QMainWindow):
    """Main window — applies Organic Noir QSS and delegates all UI to InputScreen."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Syncacademic — Exam Schedule Portal")
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "logo.png")))
        self.setMinimumSize(1100, 720)
        style = QSS()
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(style)
            palette = app.palette()
            palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#F8FAFC"))
            palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#172033"))
            app.setPalette(palette)
        self.setStyleSheet(style)
        self._controller = DesktopController()
        self._input_screen = InputScreen(self._controller)
        self.setCentralWidget(self._input_screen)

    def shutdown_background_workers(self) -> None:
        """Stop generation and load-more workers before Qt tears widgets down."""
        self._input_screen.shutdown_background_workers()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override name
        self.shutdown_background_workers()
        super().closeEvent(event)
