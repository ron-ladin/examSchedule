"""
Period Card Widgets
-------------------
Per-period widget bundle for the results panel. Groups the date/variant
navigation labels, jump inputs, navigation buttons, calendar table, Load More /
Auto Load buttons, and the empty-state label that previously lived as ~14
parallel ``dict[str, QWidget]`` attributes on _ResultsPanel.

This is a plain data holder (not a QWidget subclass): _ResultsPanel still builds
and wires the widgets, but stores one PeriodCardWidgets per period in a single
``self._cards`` mapping instead of fourteen separate dicts. That shrinks the
god-object surface and keeps a period's widgets discoverable in one place.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton, QTableWidget


@dataclass(frozen=True)
class PeriodCardWidgets:
    """All widgets that make up one period's results card."""

    # Date-level navigation: different exam dates.
    date_counter_label: QLabel
    date_jump_input: QLineEdit
    prev_date_btn: QPushButton
    next_date_btn: QPushButton

    # Variant-level navigation: same dates, different Feature 4 allocations.
    counter_label: QLabel
    variant_jump_input: QLineEdit
    cal_table: QTableWidget
    empty_label: QLabel
    prev_btn: QPushButton
    next_btn: QPushButton

    # Loading controls.
    load_more_btn: QPushButton
    auto_date_btn: QPushButton
    auto_variant_btn: QPushButton

    @property
    def auto_load_btn(self) -> QPushButton:
        """Backward-compatible alias: the date auto-load button."""
        return self.auto_date_btn
