"""Active scheduling limits UI extracted from ResultsPanel."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QToolButton, QVBoxLayout, QWidget

from src.domain.threshold import Criterion, ThresholdEntry, ThresholdSettings
from src.ui.tokens import (
    COLOR_CAL_ACTIVE_BG,
    COLOR_PANEL_BLUE,
    COLOR_PANEL_BLUE_BORDER,
    COLOR_PRIMARY_ACTION,
    COLOR_TEXT_DARK,
    COLOR_VIOLET,
)

_THRESHOLD_LABELS: dict[Criterion, tuple[str, str]] = {
    Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS: (
        "Mandatory exam gap",
        "at least {k} day(s) between mandatory exams",
    ),
    Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS: (
        "Any exam gap",
        "at least {k} day(s) between any two exams",
    ),
    Criterion.MAX_ELECTIVE_COLLISIONS: (
        "Elective collisions",
        "at most {k} same-day elective collision(s)",
    ),
    Criterion.MIN_DAYS_EXAM_PERIOD_SPREAD: (
        "Exam-period spread",
        "at least {k} day(s) from first to last mandatory exam",
    ),
    Criterion.MAX_EXAMS_PER_DAY: (
        "Exams per day",
        "at most {k} exam(s) on one day",
    ),
}


def active_threshold_entries(thresholds: ThresholdSettings) -> list[ThresholdEntry]:
    """Return enabled threshold entries in domain enum order."""
    by_criterion = {entry.criterion: entry for entry in thresholds.entries}
    return [
        by_criterion[criterion]
        for criterion in Criterion
        if criterion in by_criterion and by_criterion[criterion].enabled
    ]


def format_threshold_entry(entry: ThresholdEntry) -> str:
    """Human-readable summary for one active scheduling limit."""
    title, detail_template = _THRESHOLD_LABELS[entry.criterion]
    return f"{title}: {detail_template.format(k=entry.k)}"


class ActiveLimitsPanel(QWidget):
    """Small collapsible panel showing thresholds used for a generation."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background: {COLOR_PANEL_BLUE};"
            f" border: 1px solid {COLOR_PANEL_BLUE_BORDER};"
            " border-radius: 8px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        self.toggle = QToolButton()
        self.toggle.setCheckable(True)
        self.toggle.setChecked(False)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setText("Active scheduling limits")
        self.toggle.setToolTip(
            "Show the enabled threshold settings used for this generation."
        )
        self.toggle.setStyleSheet(
            "QToolButton {"
            f" background: transparent; color: {COLOR_PRIMARY_ACTION}; border: none;"
            " font-size: 13px; font-weight: 800; padding: 0;"
            "}"
            f"QToolButton:hover {{ color: {COLOR_VIOLET}; }}"
        )
        self.toggle.toggled.connect(self._on_toggled)
        layout.addWidget(self.toggle)

        self.details = QLabel("")
        self.details.setWordWrap(True)
        self.details.setVisible(False)
        self.details.setStyleSheet(
            "background: rgba(255, 255, 255, 0.62);"
            f" color: {COLOR_TEXT_DARK}; border: 1px solid {COLOR_CAL_ACTIVE_BG};"
            " border-radius: 8px; padding: 8px 10px;"
            " font-size: 12px; font-weight: 600;"
        )
        layout.addWidget(self.details)
        self.setVisible(False)

    def _on_toggled(self, expanded: bool) -> None:
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.details.setVisible(expanded)

    def show_limits(
        self,
        thresholds: ThresholdSettings | None,
        *,
        imported_schedule: bool,
    ) -> None:
        active_entries = [] if thresholds is None else active_threshold_entries(thresholds)

        if imported_schedule or not active_entries:
            self.setVisible(False)
            self.toggle.setChecked(False)
            self.details.setText("")
            return

        self.toggle.setChecked(False)
        self.toggle.setText(f"Active scheduling limits ({len(active_entries)})")
        self.details.setText(
            "<br>".join(
                f"<span style='color:{COLOR_VIOLET};'>*</span> "
                f"{format_threshold_entry(entry)}"
                for entry in active_entries
            )
        )
        self.details.setTextFormat(Qt.TextFormat.RichText)
        self.setVisible(True)
