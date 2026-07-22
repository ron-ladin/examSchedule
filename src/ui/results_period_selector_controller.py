"""Period selector flow extracted from the Results panel."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import QSignalBlocker

from src.domain.semester import display_semester

if TYPE_CHECKING:  # pragma: no cover - imported only for type checkers.
    from src.ui.results_panel import _ResultsPanel


class ResultsPeriodSelectorController:
    """Manage the Results panel semester/moed selector."""

    def __init__(
        self,
        panel: "_ResultsPanel",
        *,
        display_period_key: Callable[[str], str],
    ) -> None:
        self._panel = panel
        self._display_period_key = display_period_key

    def period_key_at_tab_index(self, index: int) -> str | None:
        """Return the period key displayed by tab *index*, if any."""
        period_keys = list(self._panel._schedules_by_period)
        if 0 <= index < len(period_keys):
            return period_keys[index]
        return None

    @staticmethod
    def period_parts(period_key: str) -> tuple[str, str]:
        """Return (semester, moed) for a period key."""
        if " - " in period_key:
            semester, moed = period_key.split(" - ", 1)
            return semester.strip(), moed.strip()
        if " — " in period_key:
            semester, moed = period_key.split(" — ", 1)
            return semester.strip(), moed.strip()
        return period_key.strip(), ""

    def period_keys_for_semester(self, semester: str) -> list[str]:
        return [
            key
            for key in self.period_keys_for_selector()
            if self.period_parts(key)[0] == semester
        ]

    def period_keys_for_selector(self) -> list[str]:
        """Return all periods the user can inspect, including empty ones."""
        return list(self._panel._schedules_by_period)

    def first_period_with_results(self) -> str | None:
        """Return the first period that currently has visible schedules."""
        for key, schedules in self._panel._schedules_by_period.items():
            if schedules:
                return key
        return None

    def refresh_period_selector(self, preferred_key: str | None = None) -> None:
        """Populate the compact semester/moed selector from available periods."""
        panel = self._panel
        if not hasattr(panel, "_semester_combo"):
            return

        period_keys = self.period_keys_for_selector()
        panel._period_selector.setVisible(bool(period_keys))
        if not period_keys:
            return

        current_key = (
            preferred_key
            or self.first_period_with_results()
            or self.current_period_key()
            or period_keys[0]
        )
        current_semester, _ = self.period_parts(current_key)

        semesters: list[str] = []
        for key in period_keys:
            semester, _moed = self.period_parts(key)
            if semester not in semesters:
                semesters.append(semester)

        with QSignalBlocker(panel._semester_combo):
            panel._semester_combo.clear()
            for semester in semesters:
                panel._semester_combo.addItem(display_semester(semester), semester)
            semester_index = max(0, panel._semester_combo.findData(current_semester))
            panel._semester_combo.setCurrentIndex(semester_index)
            current_semester = panel._semester_combo.currentData()

        self.populate_moed_selector(current_semester, current_key)

    def populate_moed_selector(
        self,
        semester: str,
        preferred_key: str | None = None,
    ) -> None:
        panel = self._panel
        period_keys = self.period_keys_for_semester(semester)
        with QSignalBlocker(panel._moed_combo):
            panel._moed_combo.clear()
            for key in period_keys:
                _semester, moed = self.period_parts(key)
                panel._moed_combo.addItem(moed or self._display_period_key(key), key)
            preferred_index = (
                panel._moed_combo.findData(preferred_key)
                if preferred_key is not None
                else -1
            )
            panel._moed_combo.setCurrentIndex(max(0, preferred_index))

        selected_key = panel._moed_combo.currentData()
        if selected_key:
            self.select_period_key(selected_key)

    def select_period_key(self, period_key: str) -> None:
        panel = self._panel
        period_keys = list(panel._schedules_by_period)
        try:
            index = period_keys.index(period_key)
        except ValueError:
            return
        if panel._period_tabs.currentIndex() != index:
            panel._period_tabs.setCurrentIndex(index)
        else:
            self.on_period_tab_changed(index)

    def on_period_semester_changed(self, _index: int) -> None:
        semester = self._panel._semester_combo.currentData()
        if semester:
            self.populate_moed_selector(semester)

    def on_period_moed_changed(self, _index: int) -> None:
        period_key = self._panel._moed_combo.currentData()
        if period_key:
            self.select_period_key(period_key)

    def current_period_key(self) -> str | None:
        """Return the period key for the currently visible tab."""
        return self.period_key_at_tab_index(self._panel._period_tabs.currentIndex())

    def on_period_tab_changed(self, index: int) -> None:
        """Refresh a period lazily when it becomes visible."""
        panel = self._panel
        period_key = self.period_key_at_tab_index(index)
        if period_key is not None and period_key in panel._cards:
            if (
                hasattr(panel, "_moed_combo")
                and panel._moed_combo.currentData() != period_key
            ):
                self.refresh_period_selector(preferred_key=period_key)
            panel._refresh_period_card(period_key)
