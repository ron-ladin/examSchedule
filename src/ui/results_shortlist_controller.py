"""Shortlist flow extracted from the Results panel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QMessageBox

from src.domain.schedule import Schedule
from src.ui.favorite_schedules import (
    FavoriteSchedule,
    FavoritesDialog,
    find_schedule_by_fingerprint,
    schedule_fingerprint,
)
from src.ui.tokens import (
    COLOR_CAL_ACTIVE_BG,
    COLOR_PANEL_BLUE,
    COLOR_PRIMARY_ACTION,
)

if TYPE_CHECKING:  # pragma: no cover - imported only for type checkers.
    from src.ui.results_panel import _ResultsPanel


_SHORTLIST_ADD_BUTTON_STYLE = (
    f"QPushButton {{ background: {COLOR_PANEL_BLUE}; color: {COLOR_PRIMARY_ACTION};"
    " border: 1px solid #93C5FD; border-radius: 8px;"
    " padding: 7px 16px; font-weight: 700; }"
    f"QPushButton:hover {{ background: {COLOR_CAL_ACTIVE_BG}; }}"
    "QPushButton:disabled { background: #F1F5F9; color: #94A3B8;"
    " border-color: #CBD5E1; }"
)
_SHORTLIST_REMOVE_BUTTON_STYLE = (
    "QPushButton { background: #DC2626; color: #FFFFFF;"
    " border: 1px solid #B91C1C; border-radius: 8px;"
    " padding: 7px 16px; font-weight: 700; }"
    "QPushButton:hover { background: #B91C1C; }"
    "QPushButton:disabled { background: #F1F5F9; color: #94A3B8;"
    " border-color: #CBD5E1; }"
)


class ResultsShortlistController:
    """Manage shortlisted schedule options for the Results panel."""

    def __init__(
        self,
        panel: "_ResultsPanel",
        *,
        display_period_key: Callable[[str], str],
    ) -> None:
        self._panel = panel
        self._display_period_key = display_period_key
        self._export_shortlisted: Callable[..., bool] | None = None

    def set_export_shortlisted(self, export_shortlisted: Callable[..., bool]) -> None:
        self._export_shortlisted = export_shortlisted

    def clear_favorites(self) -> None:
        panel = self._panel
        panel._favorite_schedules.clear()
        self.refresh_favorite_buttons()

    def refresh_shortlist_labels(self) -> None:
        """Keep shortlist labels accurate after ranking/load-order changes."""
        panel = self._panel
        updated: list[FavoriteSchedule] = []
        for favorite in panel._favorite_schedules:
            schedules = panel._schedules_by_period.get(favorite.period_key)
            if not schedules:
                updated.append(favorite)
                continue

            index = find_schedule_by_fingerprint(schedules, favorite.signature)
            if index is None:
                updated.append(favorite)
                continue

            updated.append(
                replace(
                    favorite,
                    label=self.favorite_label(favorite.period_key, index),
                )
            )

        panel._favorite_schedules = updated
        self.refresh_favorite_buttons()

    def favorite_label(self, period_key: str, index: int) -> str:
        panel = self._panel
        index_nav = panel._nav_model.index_nav(period_key)
        nav_pos = index_nav.get(index)
        if nav_pos is None:
            panel._rebuild_navigation_cache(period_key)
            nav_pos = panel._nav_model.index_nav(period_key).get(index)

        if nav_pos is None:
            return f"{self._display_period_key(period_key)} | Schedule {index + 1:,}"

        date_pos, variant_pos = nav_pos
        label_parts = [
            self._display_period_key(period_key),
            f"Date option {date_pos + 1:,}",
        ]

        schedules = panel._schedules_by_period.get(period_key, [])
        schedule = schedules[index] if 0 <= index < len(schedules) else None
        if schedule is not None and panel._schedule_has_classroom_data(schedule):
            label_parts.append(f"Classroom choice {variant_pos + 1:,}")

        return " | ".join(label_parts)

    def current_shortlist_row(self) -> int | None:
        panel = self._panel
        period_key = panel._current_period_key()
        if period_key is None:
            return None

        schedules = panel._schedules_by_period.get(period_key, [])
        if not schedules:
            return None

        index = panel._period_indices.get(period_key, 0)
        if index < 0 or index >= len(schedules):
            return None

        signature = schedule_fingerprint(schedules[index])
        for row, favorite in enumerate(panel._favorite_schedules):
            if favorite.period_key == period_key and favorite.signature == signature:
                return row
        return None

    def toggle_current_favorite(self, period_key: str) -> None:
        row = self.current_shortlist_row()
        if row is not None:
            self.delete_favorite_at(row)
            return

        self.save_current_favorite(period_key)

    def save_current_favorite(self, period_key: str) -> None:
        panel = self._panel
        schedules = panel._schedules_by_period.get(period_key, [])
        if not schedules:
            return

        index = panel._period_indices.get(period_key, 0)
        if index < 0 or index >= len(schedules):
            return

        signature = schedule_fingerprint(schedules[index])
        for favorite in panel._favorite_schedules:
            if favorite.period_key == period_key and favorite.signature == signature:
                self.refresh_favorite_buttons()
                return

        panel._favorite_schedules.append(
            FavoriteSchedule(
                period_key=period_key,
                signature=signature,
                label=self.favorite_label(period_key, index),
            )
        )
        self.refresh_favorite_buttons()

    def save_visible_favorite(self) -> None:
        period_key = self._panel._current_period_key()
        if period_key is not None:
            self.save_current_favorite(period_key)

    def toggle_visible_favorite(self) -> None:
        period_key = self._panel._current_period_key()
        if period_key is not None:
            self.toggle_current_favorite(period_key)

    def delete_favorite_at(self, row: int) -> bool:
        panel = self._panel
        if row < 0 or row >= len(panel._favorite_schedules):
            return False
        del panel._favorite_schedules[row]
        self.refresh_favorite_buttons()
        return True

    def refresh_favorite_buttons(self, saved_period_key: str | None = None) -> None:
        panel = self._panel
        count = len(panel._favorite_schedules)
        current = panel._current_period_key()
        has_current_schedule = bool(
            current is not None and panel._schedules_by_period.get(current)
        )
        current_is_shortlisted = self.current_shortlist_row() is not None

        panel._save_favorite_btn.setVisible(not panel._is_imported_schedule)
        panel._save_favorite_btn.setEnabled(has_current_schedule)
        panel._favorites_btn.setEnabled(count > 0)
        panel._favorites_btn.setText(f"Shortlist ({count})")

        if current_is_shortlisted:
            panel._save_favorite_btn.setText("Remove from Shortlist")
            panel._save_favorite_btn.setStyleSheet(_SHORTLIST_REMOVE_BUTTON_STYLE)
        else:
            panel._save_favorite_btn.setText("Add to Shortlist")
            panel._save_favorite_btn.setStyleSheet(_SHORTLIST_ADD_BUTTON_STYLE)

    def show_favorites_dialog(self) -> None:
        panel = self._panel
        if not panel._favorite_schedules:
            panel._show_message(
                "Shortlist Empty",
                "Add one or more schedule options to the Shortlist before choosing a final export.",
                QMessageBox.Icon.Information,
            )
            return

        dialog = FavoritesDialog(panel._favorite_schedules, panel)

        def open_selected() -> None:
            row = dialog.favorites_list.currentRow()
            self.open_favorite_at(row, close_dialog=dialog.accept)

        def export_selected() -> None:
            if self._export_shortlisted is not None:
                self._export_shortlisted(close_dialog=dialog.accept)

        def delete_selected() -> None:
            row = dialog.favorites_list.currentRow()
            if not self.delete_favorite_at(row):
                return
            dialog.remove_row(row, len(panel._favorite_schedules))

        dialog.openRequested.connect(lambda _row: open_selected())
        dialog.exportRequested.connect(lambda _row: export_selected())
        dialog.deleteRequested.connect(lambda _row: delete_selected())
        dialog.exec()

    def open_favorite_at(self, row: int, close_dialog=None) -> bool:
        panel = self._panel
        if row < 0 or row >= len(panel._favorite_schedules):
            return False

        favorite = panel._favorite_schedules[row]

        schedules = panel._schedules_by_period.get(favorite.period_key)
        if not schedules:
            self.show_missing_favorite_message()
            return False

        index = find_schedule_by_fingerprint(schedules, favorite.signature)
        if index is None:
            self.show_missing_favorite_message()
            return False

        panel._period_indices[favorite.period_key] = index
        panel._select_period_key(favorite.period_key)
        panel._refresh_period_card(favorite.period_key)
        if close_dialog is not None:
            close_dialog()
        return True

    def schedule_for_shortlist_row(
        self,
        row: int,
    ) -> tuple[FavoriteSchedule, Schedule] | None:
        panel = self._panel
        if row < 0 or row >= len(panel._favorite_schedules):
            return None

        favorite = panel._favorite_schedules[row]
        schedules = panel._schedules_by_period.get(favorite.period_key)
        if not schedules:
            return None

        index = find_schedule_by_fingerprint(schedules, favorite.signature)
        if index is None:
            return None

        return favorite, schedules[index]

    def shortlisted_schedule_selection(self) -> dict[str, list[Schedule]] | None:
        panel = self._panel
        selected: dict[str, list[Schedule]] = {}

        for favorite in panel._favorite_schedules:
            schedules = panel._schedules_by_period.get(favorite.period_key)
            if not schedules:
                return None

            index = find_schedule_by_fingerprint(schedules, favorite.signature)
            if index is None:
                return None

            selected.setdefault(favorite.period_key, []).append(schedules[index])

        return selected

    def show_missing_favorite_message(self) -> None:
        self._panel._show_message(
            "Shortlist Option Unavailable",
            "This shortlisted schedule is no longer available in the current results. "
            "The generated results may have changed; generate or load the matching "
            "results and try again.",
            QMessageBox.Icon.Information,
        )
