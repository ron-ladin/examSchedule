"""PeriodNavigator — Prev/Next/Jump handlers for results-panel cards.

Extracted from _ResultsPanel. The navigator computes *where* navigation should
land and emits PyQt signals describing the intent; it never mutates the panel's
private state. The panel owns ``_period_indices`` and the card refresh, connects
its slots to these signals, and applies the change to its own state.

Read-only access to the live schedule/navigation state is supplied through the
NavigationModel and small accessor callables, so the navigator holds no back
reference to the panel.

Signals
-------
navigationRequested(period_key: str, index: int)
    The user navigated to a concrete schedule index for ``period_key``.
messageRequested(title: str, text: str, icon: object)
    A user-facing message box should be shown.
loadMoreDatesRequested(period_key: str)
    The user advanced past the last loaded date option; a date-options batch
    should be loaded and the view advanced once it arrives.
"""

from collections.abc import Callable

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox

from src.domain.schedule import Schedule
from src.ui.navigation_model import NavigationModel
from src.ui.period_card import PeriodCardWidgets


class PeriodNavigator(QObject):
    """Date-option and variant navigation for a single results panel."""

    navigationRequested = pyqtSignal(str, int)
    messageRequested = pyqtSignal(str, str, object)
    loadMoreDatesRequested = pyqtSignal(str)

    def __init__(
        self,
        nav_model: NavigationModel,
        cards: dict[str, PeriodCardWidgets],
        get_schedules: Callable[[], dict[str, list[Schedule]]],
        get_indices: Callable[[], dict[str, int]],
        has_more: Callable[[str], bool],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._nav = nav_model
        self._cards = cards
        self._get_schedules = get_schedules
        self._get_indices = get_indices
        self._has_more = has_more

    @staticmethod
    def _parse_jump_number(text: str) -> int | None:
        """Parse a 1-based positive jump number from a QLineEdit."""
        stripped = text.strip()
        if not stripped:
            return None
        try:
            value = int(stripped)
        except ValueError:
            return None
        return value if value >= 1 else None

    def _schedules(self, period_key: str) -> list[Schedule]:
        return self._get_schedules().get(period_key, [])

    def _current_index(self, period_key: str) -> int:
        return self._get_indices()[period_key]

    def jump_to_date_option(self, period_key: str) -> None:
        """Jump to a loaded date-level schedule option by 1-based number."""
        schedules = self._schedules(period_key)
        card = self._cards.get(period_key)
        jump_input = card.date_jump_input if card else None
        target = self._parse_jump_number(jump_input.text() if jump_input else "")

        if target is None:
            self.messageRequested.emit(
                "Invalid Date Option",
                "Enter a valid date-option number.",
                QMessageBox.Icon.Warning,
            )
            return

        if not schedules:
            self.messageRequested.emit(
                "No Date Options",
                "There are no schedules for this period.",
                QMessageBox.Icon.Warning,
            )
            return

        options = self._nav.date_options(period_key)
        if target > len(options):
            extra = ""
            if self._has_more(period_key):
                extra = "\n\nMore results may exist. Click '+ more options' and try again."
            self.messageRequested.emit(
                "Date Option Not Found",
                f"There is no loaded date option #{target:,} for this period.{extra}",
                QMessageBox.Icon.Warning,
            )
            return

        if jump_input is not None:
            jump_input.clear()
        self.navigationRequested.emit(period_key, options[target - 1][1][0])

    def jump_to_variant(self, period_key: str) -> None:
        """Jump to a classroom/time-slot variant for the current date option."""
        schedules = self._schedules(period_key)
        card = self._cards.get(period_key)
        jump_input = card.variant_jump_input if card else None
        target = self._parse_jump_number(jump_input.text() if jump_input else "")

        if target is None:
            self.messageRequested.emit(
                "Invalid Variant",
                "Enter a valid variant number.",
                QMessageBox.Icon.Warning,
            )
            return

        if not schedules:
            self.messageRequested.emit(
                "No Variants",
                "There are no schedules for this period.",
                QMessageBox.Icon.Warning,
            )
            return

        idx = self._current_index(period_key)
        nav_pos = self._nav.nav_position(period_key, idx)
        options = self._nav.date_options(period_key)

        if nav_pos is None:
            self.messageRequested.emit(
                "Variant Not Found",
                "The current schedule variant could not be found.",
                QMessageBox.Icon.Warning,
            )
            return

        date_pos, _variant_pos = nav_pos
        same_date_indices = options[date_pos][1]

        if target > len(same_date_indices):
            self.messageRequested.emit(
                "Variant Not Found",
                f"There is no variant #{target:,} for the current date option.",
                QMessageBox.Icon.Warning,
            )
            return

        if jump_input is not None:
            jump_input.clear()
        self.navigationRequested.emit(period_key, same_date_indices[target - 1])

    def go_prev_variant(self, period_key: str) -> None:
        """Move to the previous classroom/time-slot variant for the same dates."""
        if not self._schedules(period_key):
            return

        idx = self._current_index(period_key)
        nav_pos = self._nav.nav_position(period_key, idx)
        if nav_pos is None:
            return

        date_pos, variant_pos = nav_pos
        same_date_indices = self._nav.date_options(period_key)[date_pos][1]

        if variant_pos > 0:
            self.navigationRequested.emit(period_key, same_date_indices[variant_pos - 1])

    def go_next_variant(self, period_key: str) -> None:
        """Move to the next classroom/time-slot variant for the same dates."""
        if not self._schedules(period_key):
            return

        idx = self._current_index(period_key)
        nav_pos = self._nav.nav_position(period_key, idx)
        if nav_pos is None:
            return

        date_pos, variant_pos = nav_pos
        same_date_indices = self._nav.date_options(period_key)[date_pos][1]

        if variant_pos < len(same_date_indices) - 1:
            self.navigationRequested.emit(period_key, same_date_indices[variant_pos + 1])

    def go_prev_date_option(self, period_key: str) -> None:
        """Move to the previous date-level schedule option."""
        if not self._schedules(period_key):
            return

        idx = self._current_index(period_key)
        nav_pos = self._nav.nav_position(period_key, idx)
        if nav_pos is None:
            return

        date_pos, _variant_pos = nav_pos
        if date_pos <= 0:
            return

        options = self._nav.date_options(period_key)
        self.navigationRequested.emit(period_key, options[date_pos - 1][1][0])

    def go_next_date_option(self, period_key: str) -> None:
        """Move to the next schedule whose exam dates are different."""
        if not self._schedules(period_key):
            return

        idx = self._current_index(period_key)
        nav_pos = self._nav.nav_position(period_key, idx)
        if nav_pos is None:
            return

        date_pos, _variant_pos = nav_pos
        options = self._nav.date_options(period_key)

        if date_pos < len(options) - 1:
            self.navigationRequested.emit(period_key, options[date_pos + 1][1][0])
            return

        if self._has_more(period_key):
            self.loadMoreDatesRequested.emit(period_key)
