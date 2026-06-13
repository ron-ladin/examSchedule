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
        All controls lock while generation is active (§280 AC).
    Tab 2 — Sort Order
        Draggable list of sort criteria; user reorders to set priority.
        Checkbox per row to include/exclude a criterion from the sort.
        Controls remain active during generation (§281 AC) — changes re-sort immediately.

Signals emitted:
    settings_changed(Settings)        — emitted on OK/Apply click (threshold commit).
    sort_order_changed(SortingConfig) — emitted immediately whenever sort list changes.

Usage (modeless — dialog stays open while generation runs):
    dialog = SettingsScreen(current_settings, is_generating=False, parent=self)
    dialog.settings_changed.connect(self._on_settings_changed)
    dialog.sort_order_changed.connect(controller.apply_sort)
    dialog.show()
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
    QMessageBox,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.domain.settings import Settings
from src.domain.sorting import SortCriterion, SortRule, SortingConfig
from src.domain.threshold import (
    CRITERION_MIN_K,
    Criterion,
    ThresholdEntry,
    ThresholdSettings,
)

_log = logging.getLogger(__name__)

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
    """Modeless dialog for threshold + sort settings (spec §2 and §3)."""

    # Emitted on OK: full settings object (thresholds + sort).
    settings_changed = pyqtSignal(Settings)

    # Emitted immediately whenever the sort list changes (drag or checkbox).
    # Connect to controller.apply_sort() for live re-sort without restart.
    sort_order_changed = pyqtSignal(SortingConfig)

    def __init__(
        self,
        current: Settings,
        is_generating: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Scheduling Settings")
        self.setMinimumWidth(540)

        self._current = current

        # Threshold widgets: criterion → (QCheckBox, QSpinBox)
        self._threshold_widgets: dict[Criterion, tuple[QCheckBox, QSpinBox]] = {}
        self._sort_list: QListWidget | None = None

        self._build_ui()

        # Apply generation-lock state after widgets exist.
        if is_generating:
            self.set_generation_state(True)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_threshold_tab(), "Thresholds (§2)")
        self._tabs.addTab(self._build_sort_tab(), "Sort Order (§3)")
        layout.addWidget(self._tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_threshold_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        form.setSpacing(10)

        for criterion in Criterion:
            entry = self._current.thresholds.for_criterion(criterion)
            enabled = entry.enabled if entry else False
            # Source of truth §2.3: k >= 0 for elective collisions; k >= 1 for all others.
            k_value = entry.k if entry else CRITERION_MIN_K[criterion]

            checkbox = QCheckBox(_THRESHOLD_LABELS[criterion])
            checkbox.setChecked(enabled)

            spinbox = QSpinBox()
            spinbox.setMinimum(CRITERION_MIN_K[criterion])
            spinbox.setMaximum(365)
            spinbox.setValue(k_value)
            # k input follows toggle state.
            spinbox.setEnabled(enabled)
            checkbox.toggled.connect(spinbox.setEnabled)

            self._threshold_widgets[criterion] = (checkbox, spinbox)
            form.addRow(checkbox, spinbox)

        return widget

    def _build_sort_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel(
            "Drag rows to reorder. Check to include. Top = highest priority."
        ))

        self._sort_list = QListWidget()
        self._sort_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)

        # Block signals during population so we don't emit sort_order_changed prematurely.
        self._sort_list.blockSignals(True)
        seen: set[SortCriterion] = set()
        for rule in sorted(self._current.sorting.rules, key=lambda r: r.priority):
            self._add_sort_item(rule.criterion, checked=True)
            seen.add(rule.criterion)
        for criterion in SortCriterion:
            if criterion not in seen:
                self._add_sort_item(criterion, checked=False)
        self._sort_list.blockSignals(False)

        # Live signals: checkbox toggle or drag-reorder → emit sort_order_changed.
        self._sort_list.itemChanged.connect(self._on_sort_list_changed)
        self._sort_list.model().rowsMoved.connect(self._on_sort_list_changed)

        layout.addWidget(self._sort_list)
        return widget

    def _add_sort_item(self, criterion: SortCriterion, *, checked: bool) -> None:
        item = QListWidgetItem(_SORT_LABELS[criterion])
        item.setData(_CRITERION_ROLE, criterion)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._sort_list.addItem(item)

    # ------------------------------------------------------------------
    # Public API: generation-state locking
    # ------------------------------------------------------------------

    def set_generation_state(self, is_running: bool) -> None:
        """Lock threshold controls while generation is active; sort tab stays enabled.

        Spec §280 AC: all threshold UI elements locked during generation.
        Spec §281 AC: sort controls MUST remain active during generation.
        """
        for checkbox, spinbox in self._threshold_widgets.values():
            checkbox.setEnabled(not is_running)
            # Spinbox enabled only when not running AND its toggle is ON.
            spinbox.setEnabled(not is_running and checkbox.isChecked())
        # Sort list is intentionally unaffected — spec §3 allows mid-run sort changes.

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_sort_list_changed(self, *_args) -> None:
        """Emit sort_order_changed immediately so the controller can re-sort."""
        config = self._build_sorting_config()
        self.sort_order_changed.emit(config)

    def _on_accept(self) -> None:
        try:
            new_settings = self._build_settings()
        except ValueError as exc:
            _log.warning("SettingsScreen validation error: %s", exc)
            QMessageBox.warning(self, "Invalid Settings", str(exc))
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
