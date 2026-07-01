"""Proctor report flow extracted from the Results panel."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QMessageBox

if TYPE_CHECKING:  # pragma: no cover - imported only for type checkers.
    from src.ui.results_panel import _ResultsPanel


class ResultsProctorReportController:
    """Build and display the spec 4.6 proctor report."""

    def __init__(
        self,
        panel: "_ResultsPanel",
        *,
        display_period_key: Callable[[str], str],
    ) -> None:
        self._panel = panel
        self._display_period_key = display_period_key

    def on_proctor_report(self) -> None:
        panel = self._panel
        if panel._is_stale():
            panel._show_message(
                "Stale Schedules",
                "Exam period dates have changed since the last generation.\n\n"
                "Please click  ▶  Generate again before viewing/exporting the proctor report.",
                QMessageBox.Icon.Warning,
            )
            return

        selected = panel._selected_schedules()
        if not selected:
            panel._show_message(
                "No Schedules",
                "Generate or load schedules before viewing the proctor report.",
                QMessageBox.Icon.Warning,
            )
            return

        sections: list[str] = []
        for period_key, schedule in selected.items():
            body = panel._controller.proctor_report_text(schedule)
            sections.append(f"=== {self._display_period_key(period_key)} ===\n{body}")

        report_text = "\n\n".join(sections)

        if not any(s.classroom_assignments for s in selected.values()):
            panel._show_message(
                "No Room Assignments",
                "These schedules have no classroom assignments. Enable Feature 4 "
                "(classrooms, slots, proctor ratio) and generate again to produce a "
                "proctor report.",
                QMessageBox.Icon.Information,
            )
            return

        from src.ui.proctor_report_dialog import ProctorReportDialog

        dialog = ProctorReportDialog(report_text, parent=panel)
        dialog.exec()
