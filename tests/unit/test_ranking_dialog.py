"""
Unit Tests: RankingDialog
-------------------------
Covers the output-screen re-ranking dialog:
  * initializes its shared SortPriorityList from the given SortingConfig,
  * Apply emits ``ranking_applied`` with the exact current SortingConfig,
  * Cancel emits nothing.
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

from src.domain.sorting import SortCriterion, SortingConfig
from src.ui.ranking_dialog import RankingDialog

QApplication = QtWidgets.QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def test_initializes_from_config(qapp):
    config = SortingConfig.from_ordered_criteria(
        [SortCriterion.SORT_AVG_DAYS_ANY, SortCriterion.SORT_MIN_DAYS_MANDATORY]
    )
    dialog = RankingDialog(config)
    # The embedded list round-trips back to the same enabled order.
    assert list(dialog._sort_list.to_config().enabled_criteria) == [
        SortCriterion.SORT_AVG_DAYS_ANY,
        SortCriterion.SORT_MIN_DAYS_MANDATORY,
    ]


def test_apply_emits_ranking_applied_with_config(qapp):
    config = SortingConfig.from_ordered_criteria(
        [SortCriterion.SORT_ELECTIVE_COLLISIONS, SortCriterion.SORT_MAX_EXAMS_PER_DAY]
    )
    dialog = RankingDialog(config)
    received: list[SortingConfig] = []
    dialog.ranking_applied.connect(received.append)

    dialog._on_apply()

    assert len(received) == 1
    assert list(received[0].enabled_criteria) == [
        SortCriterion.SORT_ELECTIVE_COLLISIONS,
        SortCriterion.SORT_MAX_EXAMS_PER_DAY,
    ]


def test_cancel_emits_nothing(qapp):
    dialog = RankingDialog(
        SortingConfig.from_ordered_criteria([SortCriterion.SORT_MIN_DAYS_MANDATORY])
    )
    received: list[SortingConfig] = []
    dialog.ranking_applied.connect(received.append)

    dialog.reject()

    assert received == []
