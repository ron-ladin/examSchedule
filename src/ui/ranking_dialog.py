"""
Dialog: RankingDialog — re-rank generated results from the output screen.

Wraps the shared :class:`SortPriorityList` (Phase 2) so the results screen offers
the exact same prioritization UX as the input Settings tab. It is initialized
with the sorting state used to generate the current results, and on Apply emits
the new ``SortingConfig`` so the controller can re-rank the cached schedules in
memory — without re-running schedule generation.
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from src.domain.sorting import SortingConfig
from src.ui.widgets.sort_priority_list import SortPriorityList


class RankingDialog(QDialog):
    """Modal dialog to reorder result-ranking criteria and apply in place."""

    ranking_applied = pyqtSignal(SortingConfig)

    def __init__(
        self,
        current: SortingConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Result Ranking")
        self.setMinimumSize(520, 460)
        self._build_ui(current)

    def _build_ui(self, current: SortingConfig) -> None:
        self.setStyleSheet(
            """
            QDialog { background: #F4F7FB; }
            QListWidget {
                background: #FFFFFF; color: #172033; border: 1px solid #DCE5F0;
                border-radius: 9px; padding: 6px; font-size: 13px;
            }
            QListWidget::item { padding: 10px; margin: 2px; border-radius: 6px; }
            QListWidget::item:selected { background: #DBEAFE; color: #0755B5; }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Re-rank generated schedules")
        title.setStyleSheet(
            "font-size:18px; font-weight:800; color:#172033; background:transparent;"
        )
        layout.addWidget(title)


        self._sort_list = SortPriorityList()
        self._sort_list.load_config(current)
        layout.addWidget(self._sort_list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
        )
        apply_btn = buttons.button(QDialogButtonBox.StandardButton.Apply)
        apply_btn.setText("Apply")
        apply_btn.clicked.connect(self._on_apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_apply(self) -> None:
        self.ranking_applied.emit(self._sort_list.to_config())
        self.accept()

