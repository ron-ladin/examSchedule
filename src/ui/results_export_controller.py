"""Shortlist export flow extracted from the Results panel."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QMessageBox

from src.domain.schedule import Schedule
from src.ui.results_shortlist_controller import ResultsShortlistController

logger = logging.getLogger(__name__)


class ResultsExportController:
    """Handle exporting shortlisted schedules from the Results panel."""

    def __init__(
        self,
        panel,
        shortlist: ResultsShortlistController,
    ) -> None:
        self._panel = panel
        self._shortlist = shortlist

    def export_shortlisted_schedules(self, close_dialog=None) -> bool:
        selected = self._shortlist.shortlisted_schedule_selection()
        if not selected:
            self._shortlist.show_missing_favorite_message()
            return False

        if self.export_schedule_selection(selected):
            if close_dialog is not None:
                close_dialog()
            return True
        return False

    def export_favorite_at(self, row: int, close_dialog=None) -> bool:
        """Backward-compatible wrapper: export all shortlisted options."""
        if row < 0 or row >= len(self._panel._favorite_schedules):
            self._shortlist.show_missing_favorite_message()
            return False

        return self.export_shortlisted_schedules(close_dialog=close_dialog)

    def export_schedule_selection(
        self,
        selected_by_period: dict[str, list[Schedule]],
    ) -> bool:
        panel = self._panel
        selected = {
            period_key: list(schedules)
            for period_key, schedules in selected_by_period.items()
            if schedules
        }
        if not selected:
            panel._show_message(
                "Nothing to Save",
                "No shortlisted schedules are currently available for export.",
                QMessageBox.Icon.Warning,
            )
            return False

        path, _ = QFileDialog.getSaveFileName(
            panel,
            "Export Shortlisted Schedules",
            "shortlisted_schedules.txt",
            "Text files (*.txt);;All files (*)",
        )

        if not path:
            return False

        try:
            panel._controller.export(
                selected,
                Path(path),
                courses_by_id=panel._courses_by_id,
            )
            panel._show_message(
                "Saved",
                f"Shortlisted schedules saved to:\n{path}",
                QMessageBox.Icon.Information,
            )
            return True
        except Exception:
            logger.exception("Save failed")
            panel._show_message(
                "Save Error",
                "Could not save the schedule file. Please check the selected path and try again.",
                QMessageBox.Icon.Critical,
            )
            return False

    def on_save(self) -> None:
        panel = self._panel
        if panel._is_stale():
            panel._show_message(
                "Stale Schedules",
                "Exam period dates have changed since the last generation.\n\n"
                "Please click  ▶  Generate again before exporting.",
                QMessageBox.Icon.Warning,
            )
            return

        if not panel._schedules_by_period:
            panel._show_message(
                "Nothing to Save",
                "No schedules have been generated or loaded.",
                QMessageBox.Icon.Warning,
            )
            return

        if not panel._favorite_schedules:
            panel._show_message(
                "Shortlist Required",
                "Add the current option to the Shortlist before exporting. "
                "This makes the final export an explicit selected schedule instead of an accidental visible option.",
                QMessageBox.Icon.Information,
            )
            return

        self.export_shortlisted_schedules()
