"""
Unit Tests: SortPriorityList widget
-----------------------------------
Covers the dynamic drag-and-drop ranking UX rules:
  * priority numbers (1..N) shown on checked rows,
  * checking jumps a row to the bottom of the checked block,
  * unchecking drops a row to the top of the unchecked block,
  * only checked rows are draggable,
  * round-trip through SortingConfig.
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip(
    "PyQt6.QtWidgets",
    reason="PyQt6 native GUI libraries are not available in this environment.",
    exc_type=ImportError,
)
QtCore = pytest.importorskip("PyQt6.QtCore", exc_type=ImportError)

from src.domain.sorting import SortCriterion, SortingConfig
from src.ui.widgets.sort_priority_list import SortPriorityList

QApplication = QtWidgets.QApplication
Qt = QtCore.Qt


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _criterion_at(widget, row):
    return widget.item(row).data(Qt.ItemDataRole.UserRole)


def _checked_criteria(widget):
    return [
        widget.item(i).data(Qt.ItemDataRole.UserRole)
        for i in range(widget.count())
        if widget.item(i).checkState() == Qt.CheckState.Checked
    ]


def test_load_config_orders_enabled_first(qapp):
    widget = SortPriorityList()
    config = SortingConfig.from_ordered_criteria(
        [SortCriterion.SORT_AVG_DAYS_ANY, SortCriterion.SORT_MIN_DAYS_MANDATORY]
    )
    widget.load_config(config)

    # All five criteria present, the two enabled ones first in priority order.
    assert widget.count() == len(SortCriterion)
    assert _criterion_at(widget, 0) == SortCriterion.SORT_AVG_DAYS_ANY
    assert _criterion_at(widget, 1) == SortCriterion.SORT_MIN_DAYS_MANDATORY


def test_checked_rows_show_priority_numbers(qapp):
    widget = SortPriorityList()
    widget.load_config(
        SortingConfig.from_ordered_criteria(
            [SortCriterion.SORT_MIN_DAYS_MANDATORY, SortCriterion.SORT_AVG_DAYS_ANY]
        )
    )
    assert widget.item(0).text().startswith("1.")
    assert widget.item(1).text().startswith("2.")
    # Unchecked rows carry no priority prefix.
    assert not widget.item(2).text().startswith("3.")


def test_checking_keeps_row_in_place(qapp):
    widget = SortPriorityList()
    widget.load_config(
        SortingConfig.from_ordered_criteria([SortCriterion.SORT_MIN_DAYS_MANDATORY])
    )
    # Row 0 is the single checked row; remaining rows are unchecked.
    # Check an unchecked row (row 2) — it must jump to index 1 (bottom of checked).
    target_criterion = _criterion_at(widget, 2)
    widget.item(2).setCheckState(Qt.CheckState.Checked)

    assert _criterion_at(widget, 2) == target_criterion
    assert _checked_criteria(widget)[-1] == target_criterion
    # Re-numbered: the newly checked row is priority 2.
    assert widget.item(2).text().startswith("2.")


def test_unchecking_keeps_row_in_place(qapp):
    widget = SortPriorityList()
    widget.load_config(
        SortingConfig.from_ordered_criteria(
            [
                SortCriterion.SORT_MIN_DAYS_MANDATORY,
                SortCriterion.SORT_AVG_DAYS_ANY,
                SortCriterion.SORT_ELECTIVE_COLLISIONS,
            ]
        )
    )
    # Uncheck the top priority row -> it must move below the remaining checked rows.
    dropped = _criterion_at(widget, 1)
    widget.item(1).setCheckState(Qt.CheckState.Unchecked)

    checked = _checked_criteria(widget)
    assert dropped not in checked
    assert len(checked) == 2
    # First unchecked slot sits right after the checked block (index 2).
    assert _criterion_at(widget, 1) == dropped
    assert widget.item(0).text().startswith("1.")
    assert widget.item(2).text().startswith("2.")


def test_can_check_third_row_without_checking_rows_above_it(qapp):
    widget = SortPriorityList()
    widget.load_config(SortingConfig())

    target = _criterion_at(widget, 2)
    widget.item(2).setCheckState(Qt.CheckState.Checked)

    assert _criterion_at(widget, 2) == target
    assert _checked_criteria(widget) == [target]
    assert widget.item(0).checkState() == Qt.CheckState.Unchecked
    assert widget.item(1).checkState() == Qt.CheckState.Unchecked
    assert widget.item(2).text().startswith("1.")


def test_only_checked_rows_are_draggable(qapp):
    widget = SortPriorityList()
    widget.load_config(
        SortingConfig.from_ordered_criteria([SortCriterion.SORT_MIN_DAYS_MANDATORY])
    )
    for i in range(widget.count()):
        item = widget.item(i)
        draggable = bool(item.flags() & Qt.ItemFlag.ItemIsDragEnabled)
        is_checked = item.checkState() == Qt.CheckState.Checked
        assert draggable == is_checked


def test_to_config_round_trips_order(qapp):
    widget = SortPriorityList()
    ordered = [
        SortCriterion.SORT_ELECTIVE_COLLISIONS,
        SortCriterion.SORT_MAX_EXAMS_PER_DAY,
    ]
    widget.load_config(SortingConfig.from_ordered_criteria(ordered))
    result = widget.to_config()
    assert list(result.enabled_criteria) == ordered


def test_emits_order_changed_on_toggle(qapp):
    widget = SortPriorityList()
    widget.load_config(SortingConfig())  # nothing checked
    fired = []
    widget.order_changed.connect(lambda: fired.append(True))
    widget.item(0).setCheckState(Qt.CheckState.Checked)
    assert fired


def test_drag_drop_reorders_priority(qapp):
    # A real InternalMove drag relocates a row in the model; simulate that move
    # with takeItem/insertItem and assert to_config() reflects the new priority.
    widget = SortPriorityList()
    ordered = [
        SortCriterion.SORT_MIN_DAYS_MANDATORY,
        SortCriterion.SORT_AVG_DAYS_ANY,
        SortCriterion.SORT_ELECTIVE_COLLISIONS,
    ]
    widget.load_config(SortingConfig.from_ordered_criteria(ordered))

    # Drag the 3rd checked row (index 2) up to the top (index 0).
    moved = widget.takeItem(2)
    widget.insertItem(0, moved)
    widget._renumber()

    assert list(widget.to_config().enabled_criteria) == [
        SortCriterion.SORT_ELECTIVE_COLLISIONS,
        SortCriterion.SORT_MIN_DAYS_MANDATORY,
        SortCriterion.SORT_AVG_DAYS_ANY,
    ]
    # Priority prefixes follow the new order.
    assert widget.item(0).text().startswith("1.")
    assert widget.item(1).text().startswith("2.")
    assert widget.item(2).text().startswith("3.")


def test_drag_drop_preserves_manual_row_position(qapp):
    # Simulate a drag that drops a checked row into the unchecked block. The
    # widget's post-drop normalization must re-anchor it above the unchecked
    # rows, preserving the checked/unchecked boundary.
    widget = SortPriorityList()
    widget.load_config(
        SortingConfig.from_ordered_criteria(
            [SortCriterion.SORT_MIN_DAYS_MANDATORY, SortCriterion.SORT_AVG_DAYS_ANY]
        )
    )
    # Move the top checked row to the very bottom (into the unchecked block).
    moved = widget.takeItem(0)
    widget.addItem(moved)

    # Mimic what dropEvent runs after Qt performs the model move.
    widget._updating = True
    widget._normalize()
    widget._updating = False
    widget._renumber()

    checked = _checked_criteria(widget)
    assert checked == [
        SortCriterion.SORT_AVG_DAYS_ANY,
        SortCriterion.SORT_MIN_DAYS_MANDATORY,
    ]
    assert _criterion_at(widget, widget.count() - 1) == (
        SortCriterion.SORT_MIN_DAYS_MANDATORY
    )
    assert list(widget.to_config().enabled_criteria) == checked
