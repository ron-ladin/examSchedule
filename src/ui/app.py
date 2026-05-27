"""
Main Application Window
------------------------
ExamSchedulerApp — QMainWindow that owns the DesktopController and
switches between InputScreen and OutputScreen via a QStackedWidget.

Usage (from main.py):
    app  = QApplication(sys.argv)
    win  = ExamSchedulerApp()
    win.show()
    sys.exit(app.exec())
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtWidgets import QMainWindow, QMessageBox, QStackedWidget

from src.controller import DesktopController
from src.ui.input_screen import InputScreen

logger = logging.getLogger(__name__)


class ExamSchedulerApp(QMainWindow):
    """Main window — manages screen transitions and owns the controller."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Syncademic — Exam Schedule Generator")
        self.setMinimumSize(1000, 720)

        self._controller = DesktopController()
        self._output_screen: Optional[object] = None

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._input_screen = InputScreen(self._controller)
        self._input_screen.schedule_ready.connect(self._on_schedule_ready)
        self._stack.addWidget(self._input_screen)

    def _on_schedule_ready(self, schedules_by_period: dict, courses_by_id: dict) -> None:
        """Switch to the output screen with freshly generated schedules."""
        # Import lazily to avoid circular imports at module load time
        from src.ui.output_screen import OutputScreen

        if self._output_screen is not None:
            self._stack.removeWidget(self._output_screen)
            self._output_screen.deleteLater()

        self._output_screen = OutputScreen(
            schedules_by_period=schedules_by_period,
            courses_by_id=courses_by_id,
            selected_programs=list(self._controller._selected_programs),
            on_back=self._show_input,
            on_save=self._on_save,
        )
        self._stack.addWidget(self._output_screen)
        self._stack.setCurrentWidget(self._output_screen)

    def _show_input(self) -> None:
        self._stack.setCurrentWidget(self._input_screen)

    def _on_save(self, schedules: dict, path: Path) -> None:
        try:
            self._controller.export(schedules, path)
            QMessageBox.information(self, "Saved", f"Schedule saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            logger.exception("Failed to save schedule")
