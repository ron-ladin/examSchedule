"""
Widget: SortPriorityList — prioritized drag-and-drop ranking list.

A reusable list widget for ordering the schedule sort criteria. It is shared by
the Settings dialog (input screen) and the Result Ranking dialog (output screen)
so both screens present the exact same prioritization UX.

Behaviour (the "dynamic UX rules"):
  * Only *checked* (enabled) criteria can be dragged and reordered; unchecked
    rows are not draggable.
  * Toggling a row's checkbox keeps it in place — checking or unchecking never
    moves a row, so checked and unchecked rows may be interleaved freely.
  * Priority follows top-to-bottom row order: the active priority numbers count
    only the checked rows in the order they currently appear.
  * Each checked row is prefixed with its live priority number (1..N); unchecked
    rows are greyed out and unnumbered.

Round-trips cleanly through ``SortingConfig``:
    widget.load_config(config)   # populate from a config
    new_config = widget.to_config()
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QWidget

from src.domain.sorting import SortCriterion, SortingConfig

# User-facing label for each criterion. Kept here (not in settings_screen) so the
# widget is the single source of truth for ranking labels across both screens.
SORT_LABELS: dict[SortCriterion, str] = {
    # NOTE: every criterion sorts DESCENDING (see SortingEngine), so each label
    # spells out that schedules with the highest value of that metric rank first.
    SortCriterion.SORT_MIN_DAYS_MANDATORY: "Sort by mandatory exam gaps (highest first)",
    SortCriterion.SORT_AVG_DAYS_ANY: "Sort by average gap between all exams (highest first)",
    SortCriterion.SORT_ELECTIVE_COLLISIONS: "Sort by elective collisions (highest first)",
    SortCriterion.SORT_EXAM_PERIOD_SPREAD: "Sort by exam-period spread (longest first)",
    SortCriterion.SORT_MAX_EXAMS_PER_DAY: "Sort by busiest exam day (highest first)",
}

_CRITERION_ROLE = Qt.ItemDataRole.UserRole

_ACTIVE_COLOR = QColor("#172033")
_INACTIVE_COLOR = QColor("#94A3B8")


class SortPriorityList(QListWidget):
    """Drag-and-drop list that ranks enabled sort criteria by priority."""

    order_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        # Guards against re-entrant itemChanged signals while we mutate items
        # (reordering, renumbering, and flag updates all emit itemChanged).
        self._updating = False
        self.itemChanged.connect(self._on_item_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load_config(self, config: SortingConfig) -> None:
        """Populate the list from a config: enabled criteria first (in order),
        then the remaining criteria as unchecked rows."""
        self._updating = True
        self.clear()
        enabled = config.enabled_criteria
        for criterion in enabled:
            self._add_item(criterion, checked=True)
        for criterion in SortCriterion:
            if criterion not in enabled:
                self._add_item(criterion, checked=False)
        self._updating = False
        self._renumber()

    def to_config(self) -> SortingConfig:
        """Return a SortingConfig reflecting the current checked order."""
        criteria = [
            self.item(i).data(_CRITERION_ROLE)
            for i in range(self.count())
            if self.item(i).checkState() == Qt.CheckState.Checked
        ]
        return SortingConfig.from_ordered_criteria(criteria)

    # ------------------------------------------------------------------
    # Item construction
    # ------------------------------------------------------------------
    def _add_item(self, criterion: SortCriterion, *, checked: bool) -> None:
        item = QListWidgetItem()
        item.setData(_CRITERION_ROLE, criterion)
        item.setFlags(self._flags_for(checked))
        item.setCheckState(
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )
        self.addItem(item)

    @staticmethod
    def _flags_for(checked: bool) -> Qt.ItemFlag:
        flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsUserCheckable
        )
        # Only checked rows are draggable; unchecked rows stay anchored.
        if checked:
            flags |= Qt.ItemFlag.ItemIsDragEnabled
        return flags

    # ------------------------------------------------------------------
    # Reactions: check-toggle and drop
    # ------------------------------------------------------------------
    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self._refresh_item_flags(item)
        finally:
            self._updating = False
        self._renumber()
        self.order_changed.emit()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().dropEvent(event)
        self._updating = True
        try:
            self._normalize()
        finally:
            self._updating = False
        self._renumber()
        self.order_changed.emit()

    # ------------------------------------------------------------------
    # Ordering helpers
    # ------------------------------------------------------------------
    def _checked_count(self) -> int:
        return sum(
            1
            for i in range(self.count())
            if self.item(i).checkState() == Qt.CheckState.Checked
        )

    def _refresh_item_flags(self, item: QListWidgetItem) -> None:
        """Refresh drag flags for a toggled item without moving it."""
        is_checked = item.checkState() == Qt.CheckState.Checked
        item.setFlags(self._flags_for(is_checked))

    def _normalize(self) -> None:
        """Refresh row flags after a drag without forcing checked rows together."""
        for i in range(self.count()):
            item = self.item(i)
            item.setFlags(
                self._flags_for(item.checkState() == Qt.CheckState.Checked)
            )

    def _renumber(self) -> None:
        """Prefix each checked row with its 1..N priority and grey unchecked rows."""
        self._updating = True
        try:
            priority = 0
            for i in range(self.count()):
                item = self.item(i)
                label = SORT_LABELS[item.data(_CRITERION_ROLE)]
                if item.checkState() == Qt.CheckState.Checked:
                    priority += 1
                    item.setText(f"{priority}.   {label}")
                    item.setForeground(_ACTIVE_COLOR)
                else:
                    item.setText(label)
                    item.setForeground(_INACTIVE_COLOR)
        finally:
            self._updating = False
