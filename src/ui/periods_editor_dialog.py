"""
Widget: ExamPeriodsEditorDialog — modal editor for exam period dates (SRS §2.4).

Extracted from config_screen.py to keep that module focused and under the
project's file-size limit. Behaviour is unchanged: existing periods are always
synced back to the controller, while synthetic standard periods are added only
after the user edits that specific tab.
"""

from datetime import date, timedelta

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.controller import DesktopController
from src.ui.period_utils import (
    STANDARD_PERIOD_ORDER as _STANDARD_PERIOD_ORDER,
    build_display_periods as _build_display_periods,
)
from src.ui.results_panel import _display_period_key


class ExamPeriodsEditorDialog(QDialog):
    """Modal dialog for editing exam period dates before generation (SRS §2.4)."""

    def __init__(self, controller: "DesktopController", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Exam Periods")
        self.setModal(True)
        self.setMinimumSize(950, 560)

        self._controller = controller
        self._editors: dict[str, object] = {}
        self._existing_period_keys: set[str] = {
            period.get_key()
            for period in self._controller.get_exam_periods()
        }
        self._activated_synthetic_period_keys: set[str] = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        tabs = QTabWidget()
        tabs.setUsesScrollButtons(True)
        tabs.setMovable(False)

        # Important:
        # The tabs already exist, but inactive tab text was almost white.
        # This stylesheet makes all semester/moed tabs readable.
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background: transparent;
            }

            QTabBar::tab {
                background: transparent;
                color: #374151;
                padding: 8px 18px;
                margin-right: 4px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
                min-width: 110px;
            }

            QTabBar::tab:hover {
                background: rgba(0, 90, 194, 0.08);
                color: #005ac2;
            }

            QTabBar::tab:selected {
                background: #9CA3AF;
                color: #FFFFFF;
                font-weight: 700;
            }

            QTabBar::tab:disabled {
                color: #9CA3AF;
            }
        """)

        from src.ui.date_editor import DateEditorWidget

        self._tabs = tabs

        for period in _build_display_periods(self._controller):
            key = period.get_key()

            if not period.date_ranges:
                tabs.addTab(
                    self._build_missing_period_tab(period),
                    _display_period_key(key),
                )
                continue

            editor = DateEditorWidget(period)
            editor.period_changed.connect(lambda k=key: self._sync(k))

            self._editors[key] = editor
            tabs.addTab(editor, _display_period_key(key))

        root.addWidget(tabs)

        close_row = QHBoxLayout()
        close_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setFixedSize(110, 36)
        close_btn.clicked.connect(self.accept)

        close_row.addWidget(close_btn)
        root.addLayout(close_row)

    def _build_missing_period_tab(self, period: "ExamPeriod") -> QWidget:
        """Create a tab for a missing exam period with an activation button."""
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        missing_lbl = QLabel(
            "No exam period dates are defined for this semester/moed."
        )
        missing_lbl.setWordWrap(True)
        missing_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        missing_lbl.setStyleSheet(
            "background: #FEF3C7;"
            "color: #92400E;"
            "border: 1px solid #F59E0B;"
            "border-radius: 8px;"
            "padding: 10px 14px;"
            "font-size: 12px;"
            "font-weight: 600;"
        )

        create_btn = QPushButton("＋ Define exam period dates")
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.setFixedHeight(36)
        create_btn.setStyleSheet(
            "QPushButton {"
            " background: #005ac2;"
            " color: white;"
            " border: none;"
            " border-radius: 8px;"
            " padding: 8px 16px;"
            " font-size: 12px;"
            " font-weight: 700;"
            "}"
            "QPushButton:hover {"
            " background: #004494;"
            "}"
        )
        create_btn.clicked.connect(
            lambda _=False, p=period: self._activate_missing_period(p)
        )

        layout.addWidget(missing_lbl)
        layout.addWidget(create_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

        return wrapper

    def _activate_missing_period(self, period: "ExamPeriod") -> None:
        """Convert a missing display-only period into a real editable period."""
        from src.domain.exam_period import ExamPeriod
        from src.ui.date_editor import DateEditorWidget

        key = period.get_key()
        start = date.today()
        end = start + timedelta(days=13)

        new_period = ExamPeriod(
            semester=period.semester,
            moed=period.moed,
            date_ranges=[(start, end)],
            excluded_dates=set(),
        )

        self._activated_synthetic_period_keys.add(key)

        editor = DateEditorWidget(new_period)
        editor.period_changed.connect(lambda k=key: self._sync(k))
        self._editors[key] = editor

        tab_label = _display_period_key(key)
        tab_index = -1

        for i in range(self._tabs.count()):
            if self._tabs.tabText(i) == tab_label:
                tab_index = i
                break

        if tab_index == -1:
            self._tabs.addTab(editor, tab_label)
            self._tabs.setCurrentWidget(editor)
        else:
            self._tabs.removeTab(tab_index)
            self._tabs.insertTab(tab_index, editor, tab_label)
            self._tabs.setCurrentIndex(tab_index)

        self._sync(key)

    def _sync(self, changed_key: str | None = None) -> None:
        """
        Sync editor changes back to the controller.

        Existing periods are always updated.
        Synthetic standard periods are added only after the user edits that
        specific synthetic tab.
        """
        if changed_key and changed_key not in self._existing_period_keys:
            self._activated_synthetic_period_keys.add(changed_key)

        edited_by_key = {
            key: editor.get_exam_period()
            for key, editor in self._editors.items()
        }

        updated = []

        for period in self._controller.get_exam_periods():
            key = period.get_key()
            updated.append(edited_by_key.get(key, period))

        existing_updated_keys = {period.get_key() for period in updated}

        for semester, moed in _STANDARD_PERIOD_ORDER:
            key = f"{semester} - {moed}"

            if (
                key in self._activated_synthetic_period_keys
                and key in edited_by_key
                and key not in existing_updated_keys
            ):
                updated.append(edited_by_key[key])
                existing_updated_keys.add(key)

        deduped = []
        seen_keys = set()

        for period in updated:
            key = period.get_key()

            if key in seen_keys:
                continue

            deduped.append(period)
            seen_keys.add(key)

        self._controller.update_exam_periods(deduped)
