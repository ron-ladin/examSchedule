"""
UI Screen: SettingsScreen
--------------------------
PyQt6 dialog for configuring threshold criteria (§2) and sort priorities (§3).

Spec §1.1: must work in both GUI (V2.0) and be skippable in CLI (V1.0).
Spec §2:   each criterion has an ON/OFF toggle and a user-defined k value.
Spec §3:   user selects sort criteria and assigns priority order (1 = primary).
Spec §6.2: no operation in this screen may block the UI thread.

Layout (two tabs):
    Tab 1 — Thresholds
        For each criterion (2.1–2.5): [checkbox ON/OFF] [label] [spinbox k]
    Tab 2 — Sort Order
        Draggable list of sort criteria; user reorders to set priority.
        Checkbox per row to include/exclude a criterion from the sort.

Signals emitted:
    settings_changed(Settings) — emitted when the user clicks Apply/OK.

Usage:
    dialog = SettingsScreen(current_settings, parent=self)
    dialog.settings_changed.connect(self._on_settings_changed)
    dialog.exec()
"""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

_log = logging.getLogger(__name__)

from src.domain.settings import Settings
from src.domain.sorting import SortCriterion, SortRule, SortingConfig
from src.domain.threshold import (
    CRITERION_MIN_K,
    Criterion,
    ThresholdEntry,
    ThresholdSettings,
)

# Human-readable labels for each criterion, shown in the UI.
_THRESHOLD_LABELS: dict[Criterion, str] = {
    Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS: "Min days between mandatory exams (§2.1)",
    Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS:       "Min days between any two exams (§2.2)",
    Criterion.MAX_ELECTIVE_COLLISIONS:          "Max same-day elective collisions (§2.3)",
    Criterion.MIN_DAYS_EXAM_PERIOD_SPREAD:      "Min exam period spread — first to last (§2.4)",
    Criterion.MAX_EXAMS_PER_DAY:                "Max exams on any single day (§2.5)",
}

_SORT_LABELS: dict[SortCriterion, str] = {
    SortCriterion.SORT_MIN_DAYS_MANDATORY:  "Min days between mandatory exams (§3.1)",
    SortCriterion.SORT_AVG_DAYS_ANY:        "Avg days between any exams (§3.2)",
    SortCriterion.SORT_ELECTIVE_COLLISIONS: "Elective collisions (§3.3)",
    SortCriterion.SORT_EXAM_PERIOD_SPREAD:  "Exam period spread (§3.4)",
    SortCriterion.SORT_MAX_EXAMS_PER_DAY:   "Max exams per day (§3.5)",
}

# QListWidgetItem user-data role for storing the SortCriterion enum value.
_CRITERION_ROLE = Qt.ItemDataRole.UserRole


class SettingsScreen(QDialog):
    """Modal dialog for threshold + sort settings (spec §2 and §3)."""

    # Emitted with the new Settings when the user accepts the dialog.
    settings_changed = pyqtSignal(Settings)

    def __init__(self, current: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Scheduling Settings")
        self.setMinimumWidth(520)

        self._current = current

        # Threshold widgets: criterion → (QCheckBox, QSpinBox)
        self._threshold_widgets: dict[Criterion, tuple[QCheckBox, QSpinBox]] = {}
        self._sort_list: QListWidget | None = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._build_threshold_tab(), "Thresholds (§2)")
        tabs.addTab(self._build_sort_tab(), "Sort Order (§3)")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_threshold_tab(self) -> QWidget:
        # TODO (§6.2): add an "Apply" button so users can test threshold
        #   changes without closing the dialog — keeps the UI feeling live.
        widget = QWidget()
        form = QFormLayout(widget)
        form.setSpacing(10)

        for criterion in Criterion:
            entry = self._current.thresholds.for_criterion(criterion)
            enabled = entry.enabled if entry else False
            k_value = entry.k if entry else CRITERION_MIN_K[criterion]

            checkbox = QCheckBox(_THRESHOLD_LABELS[criterion])
            checkbox.setChecked(enabled)

            spinbox = QSpinBox()
            spinbox.setMinimum(CRITERION_MIN_K[criterion])
            spinbox.setMaximum(365)
            spinbox.setValue(k_value)
            # Disable k input when the criterion is toggled OFF.
            spinbox.setEnabled(enabled)
            checkbox.toggled.connect(spinbox.setEnabled)

            self._threshold_widgets[criterion] = (checkbox, spinbox)
            form.addRow(checkbox, spinbox)

        return widget

    def _build_sort_tab(self) -> QWidget:
        # TODO: enable drag-drop reordering (QListWidget.DragDropMode.InternalMove)
        #   so users can drag rows to set priority visually — spec §3.
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel(
            "Check criteria to include. Top item = highest priority (primary sort)."
        ))

        self._sort_list = QListWidget()
        self._sort_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)

        # Insert currently active criteria in priority order first.
        seen: set[SortCriterion] = set()
        for rule in sorted(self._current.sorting.rules, key=lambda r: r.priority):
            self._add_sort_item(rule.criterion, checked=True)
            seen.add(rule.criterion)

        # Then append the rest (unchecked).
        for criterion in SortCriterion:
            if criterion not in seen:
                self._add_sort_item(criterion, checked=False)

        layout.addWidget(self._sort_list)
        return widget

    def _add_sort_item(self, criterion: SortCriterion, *, checked: bool) -> None:
        item = QListWidgetItem(_SORT_LABELS[criterion])
        item.setData(_CRITERION_ROLE, criterion)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._sort_list.addItem(item)

    # ------------------------------------------------------------------
    # Slot: accept
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        try:
            new_settings = self._build_settings()
        except ValueError as exc:
            # TODO: surface this as an inline QLabel error instead of ignoring.
            _log.warning("SettingsScreen validation error: %s", exc)
            return

        self.settings_changed.emit(new_settings)
        self.accept()

    # ------------------------------------------------------------------
    # Building the immutable Settings object from widget state
    # ------------------------------------------------------------------

    def _build_settings(self) -> Settings:
        return Settings(
            thresholds=self._build_threshold_settings(),
            sorting=self._build_sorting_config(),
        )

    def _build_threshold_settings(self) -> ThresholdSettings:
        entries: list[ThresholdEntry] = []
        for criterion, (checkbox, spinbox) in self._threshold_widgets.items():
            enabled = checkbox.isChecked()
            k = spinbox.value()
            minimum = CRITERION_MIN_K[criterion]
            if enabled and k < minimum:
                raise ValueError(
                    f"{criterion.value}: k must be >= {minimum} when ON, got {k}"
                )
            entries.append(ThresholdEntry(criterion=criterion, enabled=enabled, k=k))
        return ThresholdSettings(entries=tuple(entries))

    def _build_sorting_config(self) -> SortingConfig:
        if self._sort_list is None:
            raise RuntimeError("_sort_list was not initialized — call _build_ui() first")
        rules: list[SortRule] = []
        priority = 1
        for i in range(self._sort_list.count()):
            item = self._sort_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                criterion: SortCriterion = item.data(_CRITERION_ROLE)
                rules.append(SortRule(priority=priority, criterion=criterion))
                priority += 1
        return SortingConfig(rules=tuple(rules))
