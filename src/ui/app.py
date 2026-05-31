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

from PyQt6.QtWidgets import QMainWindow

from src.controller import DesktopController
from src.ui.input_screen import InputScreen
from src.ui.style import QSS

logger = logging.getLogger(__name__)


class ExamSchedulerApp(QMainWindow):
    """Main window — applies Organic Noir QSS and delegates all UI to InputScreen."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Syncademic — Exam Schedule Generator")
        self.setMinimumSize(1100, 720)
        self.setStyleSheet(QSS())
        controller = DesktopController()
        self.setCentralWidget(InputScreen(controller))
