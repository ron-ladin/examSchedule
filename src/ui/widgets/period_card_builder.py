"""build_period_card — constructs one exam-period results card.

Extracted from _ResultsPanel. The builder wires each card's navigation,
jump, load-more and Auto buttons back to the panel / its load-more
controller, registers the resulting widget bundle in ``panel._cards`` and
returns the card widget.
"""

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from src.controller import LOAD_BATCH_SIZE
from src.ui.calendar_cell_delegate import _CalendarCellDelegate
from src.ui.period_card import PeriodCardWidgets

_NAV_REPEAT_DELAY_MS = 450
_NAV_REPEAT_INTERVAL_MS = 120


class _CalendarTable(QTableWidget):
    """Calendar table that reports where inside a date cell the user clicked."""

    calendarCellClicked = pyqtSignal(int, int, QPoint)

    def mouseReleaseEvent(self, event) -> None:
        index = self.indexAt(event.position().toPoint())
        if index.isValid() and event.button() == Qt.MouseButton.LeftButton:
            self.calendarCellClicked.emit(
                index.row(),
                index.column(),
                event.position().toPoint(),
            )
        super().mouseReleaseEvent(event)


def _enable_press_and_hold(button: QPushButton) -> None:
    """Repeat button clicks while it remains pressed."""
    button.setAutoRepeat(True)
    button.setAutoRepeatDelay(_NAV_REPEAT_DELAY_MS)
    button.setAutoRepeatInterval(_NAV_REPEAT_INTERVAL_MS)


def _make_data_table(headers: list[str]) -> QTableWidget:
    table = _CalendarTable()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setMinimumHeight(36)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    # Track the mouse on both the widget and its viewport so hover-move events
    # reach mouseMoveEvent without requiring a button press (SCRUM-420).
    table.setMouseTracking(True)
    table.viewport().setMouseTracking(True)
    return table


def build_period_card(panel, period_key: str) -> QWidget:
    """Build the results card for ``period_key`` and register it on ``panel``."""
    read_only_import = (
        panel.is_imported_schedule_view()
        if hasattr(panel, "is_imported_schedule_view")
        else False
    )

    card = QWidget()
    card.setStyleSheet("background: transparent;")
    card.setMinimumHeight(260 if read_only_import else 320)

    layout = QVBoxLayout(card)
    layout.setSpacing(8)

    # Top navigation row: date-level schedules.
    # These buttons skip classroom-only variants and move between schedules
    # whose exam dates are different. This preserves the original high-level
    # browsing experience before Feature 4 variants were added.
    date_nav = QHBoxLayout()

    prev_date_btn = QPushButton("◀  Prev Dates")
    prev_date_btn.setFixedWidth(120)
    _enable_press_and_hold(prev_date_btn)
    prev_date_btn.clicked.connect(
        lambda _=False, k=period_key: panel._navigator.go_prev_date_option(k)
    )

    date_counter = QLabel("Date option: Loading…")
    date_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
    date_counter.setStyleSheet(
        "font-weight: 700; color: #334155; font-size: 12px;"
        "background: rgba(100, 116, 139, 0.08);"
        "border: 1px solid rgba(100, 116, 139, 0.16);"
        "border-radius: 10px; padding: 5px 16px;"
    )

    date_jump_input = QLineEdit()
    date_jump_input.setFixedWidth(72)
    date_jump_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
    date_jump_input.setPlaceholderText("#")
    date_jump_input.setValidator(QIntValidator(1, 999999999, panel))
    date_jump_input.setToolTip("Enter a date-option number and press Go.")
    date_jump_input.setStyleSheet(
        "QLineEdit { background:white; border:1px solid #CBD5E1;"
        " border-radius:8px; padding:5px 6px; font-weight:600;"
        " color:#111827; }"
        "QLineEdit:focus { border-color:#2563EB; }"
    )
    date_jump_input.returnPressed.connect(
        lambda k=period_key: panel._navigator.jump_to_date_option(k)
    )

    date_jump_btn = QPushButton("Go")
    date_jump_btn.setFixedWidth(44)
    date_jump_btn.clicked.connect(
        lambda _=False, k=period_key: panel._navigator.jump_to_date_option(k)
    )

    next_date_btn = QPushButton("Next Dates  ▶")
    next_date_btn.setFixedWidth(120)
    _enable_press_and_hold(next_date_btn)
    next_date_btn.clicked.connect(
        lambda _=False, k=period_key: panel._navigator.go_next_date_option(k)
    )

    date_nav.addWidget(prev_date_btn)
    date_nav.addStretch()
    date_nav.addWidget(date_counter)
    date_nav.addSpacing(8)
    date_nav.addWidget(date_jump_input)
    date_nav.addWidget(date_jump_btn)
    date_nav.addStretch()
    date_nav.addWidget(next_date_btn)

    if not read_only_import:
        layout.addLayout(date_nav)

    # Bottom navigation row: Feature 4 variants for the same date schedule.
    # These buttons move between different classroom/time-slot allocations
    # while keeping the exam dates unchanged.
    variant_navigation = QWidget()
    variant_navigation.setStyleSheet("background: transparent;")
    nav = QHBoxLayout(variant_navigation)
    nav.setContentsMargins(0, 0, 0, 0)

    prev_btn = QPushButton("◀  Prev Variant")
    prev_btn.setFixedWidth(120)
    _enable_press_and_hold(prev_btn)
    prev_btn.clicked.connect(lambda _=False, k=period_key: panel._navigator.go_prev_variant(k))

    counter = QLabel("Variant: Loading…")
    counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
    counter.setStyleSheet(
        "font-weight: 700; color: #005ac2; font-size: 13px;"
        "background: rgba(0, 90, 194, 0.06);"
        "border: 1px solid rgba(0, 90, 194, 0.15);"
        "border-radius: 10px; padding: 6px 20px;"
    )

    variant_jump_input = QLineEdit()
    variant_jump_input.setFixedWidth(72)
    variant_jump_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
    variant_jump_input.setPlaceholderText("#")
    variant_jump_input.setValidator(QIntValidator(1, 999999999, panel))
    variant_jump_input.setToolTip(
        "Enter a classroom/time-slot variant number for these dates and press Go."
    )
    variant_jump_input.setStyleSheet(
        "QLineEdit { background:white; border:1px solid #CBD5E1;"
        " border-radius:8px; padding:5px 6px; font-weight:600;"
        " color:#111827; }"
        "QLineEdit:focus { border-color:#2563EB; }"
    )
    variant_jump_input.returnPressed.connect(
        lambda k=period_key: panel._navigator.jump_to_variant(k)
    )

    variant_jump_btn = QPushButton("Go")
    variant_jump_btn.setFixedWidth(44)
    variant_jump_btn.clicked.connect(
        lambda _=False, k=period_key: panel._navigator.jump_to_variant(k)
    )

    next_btn = QPushButton("Next Variant  ▶")
    next_btn.setFixedWidth(120)
    _enable_press_and_hold(next_btn)
    next_btn.clicked.connect(lambda _=False, k=period_key: panel._navigator.go_next_variant(k))

    nav.addWidget(prev_btn)
    nav.addStretch()
    nav.addWidget(counter)
    nav.addSpacing(8)
    nav.addWidget(variant_jump_input)
    nav.addWidget(variant_jump_btn)
    nav.addStretch()
    nav.addWidget(next_btn)

    layout.addWidget(variant_navigation)
    variant_navigation.setVisible(not read_only_import)

    has_more = period_key in panel._truncated_periods

    lm_row = QHBoxLayout()
    lm_row.setSpacing(8)

    chunk_btn = QPushButton(f"⟳  +{LOAD_BATCH_SIZE:,} more options")
    chunk_btn.setStyleSheet(
        "color: #005ac2; border: 2px solid #005ac2; border-radius: 8px;"
        "padding: 6px 12px; font-size: 11px; font-weight: 600;"
        "background: rgba(0, 90, 194, 0.06);"
    )
    chunk_btn.setVisible(has_more)
    chunk_btn.clicked.connect(lambda _=False, k=period_key: panel._lm.on_load_more(k))

    auto_dates_btn = QPushButton("⚡  Auto Load Dates")
    auto_dates_btn.setStyleSheet(
        "color: #047857; border: 2px solid #047857; border-radius: 8px;"
        "padding: 6px 12px; font-size: 11px; font-weight: 700;"
        "background: rgba(4, 120, 87, 0.07);"
    )
    auto_dates_btn.setVisible(has_more)
    auto_dates_btn.setToolTip(
        "Automatically load more date options. Each date option uses only "
        "the first classroom/time-slot variant."
    )
    auto_dates_btn.clicked.connect(
        lambda _=False, k=period_key: panel._lm.toggle_auto_load_dates(k)
    )

    auto_variants_btn = QPushButton("⚡  Auto Load Classes Variants")
    auto_variants_btn.setStyleSheet(
        "color: #7C3AED; border: 2px solid #7C3AED; border-radius: 8px;"
        "padding: 6px 12px; font-size: 11px; font-weight: 700;"
        "background: rgba(124, 58, 237, 0.07);"
    )
    auto_variants_btn.setVisible(True)
    auto_variants_btn.setToolTip(
        "Automatically load more classroom/time-slot variants for the "
        "currently displayed dates only."
    )
    auto_variants_btn.clicked.connect(
        lambda _=False, k=period_key: panel._lm.toggle_auto_load_variants(k)
    )

    lm_row.addWidget(chunk_btn)
    lm_row.addWidget(auto_dates_btn)
    lm_row.addWidget(auto_variants_btn)
    lm_row.addStretch()

    if not read_only_import:
        layout.addLayout(lm_row)

    table = _make_data_table(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])
    table.setMinimumHeight(220)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.setItemDelegate(_CalendarCellDelegate(table))
    table.setStyleSheet("""
        QTableWidget {
            border: none;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.85);
            gridline-color: rgba(194, 198, 214, 0.25);
        }
        QHeaderView::section {
            background: #005ac2;
            color: white;
            font-weight: 700;
            font-size: 11px;
            padding: 6px 4px;
            border: none;
            border-right: 1px solid #004494;
        }
        QHeaderView::section:last-child { border-right: none; }
    """)
    layout.addWidget(table)

    empty_lbl = QLabel("No exams scheduled for this period.")
    empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    empty_lbl.setStyleSheet(
        "color: #72778c; font-size: 13px; padding: 24px; background: transparent;"
    )
    empty_lbl.setVisible(False)
    layout.addWidget(empty_lbl)

    panel._cards[period_key] = PeriodCardWidgets(
        date_counter_label=date_counter,
        date_jump_input=date_jump_input,
        prev_date_btn=prev_date_btn,
        next_date_btn=next_date_btn,
        variant_navigation=variant_navigation,
        counter_label=counter,
        variant_jump_input=variant_jump_input,
        cal_table=table,
        empty_label=empty_lbl,
        prev_btn=prev_btn,
        next_btn=next_btn,
        load_more_btn=chunk_btn,
        auto_date_btn=auto_dates_btn,
        auto_variant_btn=auto_variants_btn,
    )

    table.calendarCellClicked.connect(
        lambda row, col, pos, k=period_key: panel._on_cell_clicked(k, row, col, pos)
    )

    panel._refresh_period_card(period_key)
    return card
