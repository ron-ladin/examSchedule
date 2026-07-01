"""Status, stale-state, and summary presentation helpers for results UI."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.ui.results_panel import _ResultsPanel


class ResultsStatusController:
    """Coordinate non-modal status UI for the results panel."""

    def __init__(self, panel: "_ResultsPanel") -> None:
        self._panel = panel

    def mark_stale(self) -> None:
        """Show the stale-data warning and disable schedule/report exports."""
        panel = self._panel
        panel._has_stale_results = True
        panel._stale_banner.setVisible(True)
        panel._save_btn.setEnabled(False)
        panel._proctor_btn.setEnabled(False)
        self.update_summary()

    def clear_stale(self) -> None:
        """Hide the stale-data warning and re-enable Export."""
        panel = self._panel
        panel._has_stale_results = False
        panel._stale_banner.setVisible(False)
        panel._save_btn.setEnabled(True)
        panel._proctor_btn.setEnabled(True)
        self.update_summary()

    def is_stale(self) -> bool:
        """Return True when panel or controller state says results are stale."""
        panel = self._panel
        return panel._has_stale_results or panel._controller.results_stale

    def mark_ranking_dirty(self, message: str) -> None:
        """Show that current results need explicit async Result Ranking."""
        panel = self._panel
        if not panel.has_results():
            return
        panel._summary_presenter.mark_ranking_dirty(message)
        self.sync_ranking_dirty_state()
        self.update_summary()

    def show_workload_status(self, message: str) -> None:
        """Show a non-popup status for normal background workload progress."""
        panel = self._panel
        panel._summary_lbl.setStyleSheet(
            "color: #64748B; font-weight: 600; font-size: 12px;"
        )
        panel._summary_lbl.setText(message)

    def on_limits_toggled(self, expanded: bool) -> None:
        """Expand/collapse the active generation limits details."""
        self._panel._limits_panel._on_toggled(expanded)

    def refresh_active_limits_panel(self) -> None:
        """Show enabled threshold rules used by the displayed generation."""
        panel = self._panel
        panel._limits_panel.show_limits(
            panel._generation_thresholds,
            imported_schedule=panel._is_imported_schedule,
        )
        panel._limits_toggle = panel._limits_panel.toggle
        panel._limits_details = panel._limits_panel.details

    def clear_ranking_dirty(self) -> None:
        panel = self._panel
        panel._summary_presenter.clear_ranking_dirty()
        self.sync_ranking_dirty_state()

    def sync_ranking_dirty_state(self) -> None:
        panel = self._panel
        panel._ranking_dirty = panel._summary_presenter.ranking_dirty
        panel._ranking_dirty_message = panel._summary_presenter.ranking_dirty_message

    def update_summary(self) -> None:
        panel = self._panel
        if not panel._schedules_by_period:
            return

        non_empty = {
            key: value
            for key, value in panel._schedules_by_period.items()
            if value
        }

        period_schedules_total = sum(len(schedules) for schedules in non_empty.values())

        has_more = any(
            panel._controller.has_more_schedules(period_key)
            or period_key in panel._truncated_periods
            for period_key in non_empty
        )
        summary = panel._summary_presenter.build(
            has_any_periods=bool(panel._schedules_by_period),
            has_results=bool(non_empty),
            is_stale=self.is_stale(),
            is_imported_schedule=panel._is_imported_schedule,
            combined_options_total=panel._controller.get_combined_schedule_count(
                non_empty
            ),
            period_schedules_total=period_schedules_total,
            has_more=has_more,
        )
        if summary is None:
            return

        panel._summary_lbl.setStyleSheet(summary.style)
        panel._summary_lbl.setText(summary.text)
