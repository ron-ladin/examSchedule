"""
Widget: DateEditorWidget  —  SCRUM-144
----------------------------------------
SRS §2.4 — Exam Period Date Editor.

Displays a scrollable year-calendar for one ExamPeriod so the user can:
    §2.4.1  See every month of the exam window at a glance.
    §2.4.2  Click any active day to exclude it (greyed out); click again to re-include.
    §2.4.3  Change the window start / end date with two QDateEdit controls.

Usage:
    editor = DateEditorWidget(exam_period)
    editor.period_changed.connect(lambda: ...)
    updated = editor.get_exam_period()   # deep copy with all edits applied
"""

import calendar
import copy
from datetime import date

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.domain.exam_period import ExamPeriod
from src.ui.tokens import (
    COLOR_CAL_ACTIVE_BG as _ACTIVE_BG,
    COLOR_CAL_ACTIVE_FG as _ACTIVE_FG,
    COLOR_CAL_EXCLUDED_BG as _EXCLUDED_BG,
    COLOR_CAL_EXCLUDED_FG as _EXCLUDED_FG,
)


# ── Colour palette ────────────────────────────────────────────────────────────
_SAT_BG, _SAT_FG = "#f3f4f6", "#9ca3af"       # Saturday (auto-excluded)
_OUT_BG, _OUT_FG = "#FEF2F2", "#EF4444"       # outside range — red to signal unavailability


def _build_legend() -> QWidget:
    """Colour-swatch legend row replacing the emoji squares."""
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(8, 0, 0, 0)
    row.setSpacing(6)
    for bg_color, label_text in (
        (_ACTIVE_BG, "Active"),
        (_EXCLUDED_BG, "Excluded"),
        (_SAT_BG, "Saturday"),
    ):
        swatch = QFrame()
        swatch.setFixedSize(12, 12)
        swatch.setStyleSheet(
            f"background: {bg_color}; border-radius: 3px; border: 1px solid #D1D5DB;"
        )
        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: #6b7280; font-size: 11px;")
        row.addWidget(swatch)
        row.addWidget(lbl)
    row.addStretch()
    return w


# ── Day button ────────────────────────────────────────────────────────────────

class _DayButton(QPushButton):
    """One day cell inside the calendar. Emits toggled_date when clicked."""

    toggled_date = pyqtSignal(date)

    def __init__(
        self,
        d: date,
        in_range: bool,
        is_saturday: bool,
        excluded: bool,
        parent=None,
    ):
        super().__init__(str(d.day), parent)
        self._date = d
        self._in_range = in_range
        self._is_saturday = is_saturday
        self._excluded = excluded

        self.setFixedSize(44, 44)
        self.setFlat(True)
        self.setToolTip(d.strftime("%A %d %B"))
        self._refresh_style()

        if in_range and not is_saturday:
            self.clicked.connect(self._emit_toggle)
        else:
            self.setEnabled(False)

    # ── Public ────────────────────────────────────────────────────────────────

    def set_excluded(self, excluded: bool) -> None:
        self._excluded = excluded
        self._refresh_style()

    # ── Private ───────────────────────────────────────────────────────────────

    def _emit_toggle(self) -> None:
        self.toggled_date.emit(self._date)

    def _refresh_style(self) -> None:
        if self._is_saturday:
            bg, fg = _SAT_BG, _SAT_FG
        elif not self._in_range:
            bg, fg = _OUT_BG, _OUT_FG
        elif self._excluded:
            bg, fg = _EXCLUDED_BG, _EXCLUDED_FG
        else:
            bg, fg = _ACTIVE_BG, _ACTIVE_FG

        self.setStyleSheet(
            f"QPushButton {{"
            f"  background: {bg}; color: {fg};"
            f"  border: none; border-radius: 6px; font-size: 13px; font-weight: bold;"
            f"}}"
            f"QPushButton:hover:enabled {{ border: 2px solid {fg}; }}"
        )


# ── Month widget ──────────────────────────────────────────────────────────────

class _MonthWidget(QFrame):
    """Mini-calendar for a single month (§2.4.1)."""

    _HEADERS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]

    def __init__(
        self,
        year: int,
        month: int,
        date_ranges: list[tuple[date, date]],
        excluded_dates: set[date],
        parent=None,
    ):
        super().__init__(parent)
        self._year = year
        self._month = month
        self._date_ranges = date_ranges
        self._excluded_dates = excluded_dates
        self._day_buttons: dict[date, _DayButton] = {}

        self.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.8);"
            " border: 1px solid rgba(194,198,214,0.4); border-radius: 8px; }"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._build()
        self.setMinimumWidth(7 * 46 + 16)

    def day_buttons(self) -> dict[date, "_DayButton"]:
        return self._day_buttons

    def _build(self) -> None:
        grid = QGridLayout(self)
        grid.setSpacing(2)
        grid.setContentsMargins(6, 4, 6, 6)

        # Month title
        title = QLabel(date(self._year, self._month, 1).strftime("%B %Y"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFixedHeight(26)
        title.setStyleSheet(
            "font-weight: 700; font-size: 12px; color: #004394;"
            " background: transparent; border: none; padding: 0;"
        )
        grid.addWidget(title, 0, 0, 1, 7)

        # Day-of-week headers
        for col, name in enumerate(self._HEADERS):
            header = QLabel(name)
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header.setStyleSheet(
                "font-size: 10px; color: #6b7280; font-weight: bold;"
            )
            header.setFixedSize(44, 26)
            grid.addWidget(header, 1, col)

        # Day cells
        first_weekday = date(self._year, self._month, 1).weekday()  # 0 = Monday
        num_days = calendar.monthrange(self._year, self._month)[1]

        row, col = 2, first_weekday
        for day in range(1, num_days + 1):
            d = date(self._year, self._month, day)
            btn = _DayButton(
                d,
                in_range=any(s <= d <= e for s, e in self._date_ranges),
                is_saturday=(d.weekday() == 5),
                excluded=(d in self._excluded_dates),
            )
            self._day_buttons[d] = btn
            grid.addWidget(btn, row, col)
            col += 1
            if col == 7:
                col = 0
                row += 1


# ── Main widget ───────────────────────────────────────────────────────────────

class DateEditorWidget(QWidget):
    """
    Year-calendar date editor for one ExamPeriod  (SRS §2.4).

    Signals
    -------
    period_changed
        Emitted after every toggle or range change.

    Methods
    -------
    get_exam_period() -> ExamPeriod
        Returns a deep copy of the period with all edits applied.
    """

    period_changed = pyqtSignal()
    _multi_range_notice: QLabel

    def __init__(self, exam_period: ExamPeriod, parent=None):
        super().__init__(parent)
        self._period = copy.deepcopy(exam_period)
        self._day_buttons: dict[date, _DayButton] = {}
        self._building = False       # guard: suppress spurious range-changed callbacks
        self._showing_error = False  # guard: prevent re-entrant validation popup
        self._multi_range: bool = len(self._period.date_ranges) > 1
        self._setup_ui()

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_exam_period(self) -> ExamPeriod:
        """Return a deep copy of the current edited exam period."""
        return copy.deepcopy(self._period)

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self._multi_range_notice = QLabel(
            "This period has multiple date ranges — start/end editing is disabled. "
            "You can still exclude individual days by clicking them."
        )
        self._multi_range_notice.setStyleSheet(
            "color: #92400E; background: #FEF3C7;"
            " border: 1px solid #F59E0B; border-radius: 6px;"
            " padding: 4px 10px; font-size: 12px;"
        )
        self._multi_range_notice.setVisible(False)
        outer.addWidget(self._multi_range_notice)

        # §2.4.3 — Start / End date editors ─────────────────────────────────
        range_row = QWidget()
        range_layout = QHBoxLayout(range_row)
        range_layout.setContentsMargins(0, 0, 0, 0)

        range_layout.addWidget(QLabel("Exam window:"))

        _date_edit_style = (
            "QDateEdit { background:#FFFFFF; color:#0F172A; border:1px solid #D1D5DB;"
            " border-radius:6px; padding:3px 8px; }"
            "QDateEdit::drop-down {"
            "  subcontrol-origin: padding; subcontrol-position: top right;"
            "  width: 28px; background: #2563EB; border-left: 1px solid #1D4ED8;"
            "  border-radius: 0 6px 6px 0;"
            "}"
            "QDateEdit::drop-down:hover { background: #1D4ED8; }"
            "QDateEdit::down-arrow {"
            "  width: 0px; height: 0px;"
            "  border-left: 4px solid transparent;"
            "  border-right: 4px solid transparent;"
            "  border-top: 6px solid white;"
            "}"
            "QCalendarWidget { background:#FFFFFF; }"
            "QCalendarWidget QAbstractItemView { background:#FFFFFF; color:#0F172A; }"
            "QCalendarWidget QWidget#qt_calendar_navigationbar { background:#F8FAFC; }"
            "QCalendarWidget QToolButton { color:#374151; background:transparent; }"
        )

        self._start_edit = QDateEdit()
        self._start_edit.setCalendarPopup(True)
        self._start_edit.setDisplayFormat("dd/MM/yyyy")
        self._start_edit.setStyleSheet(_date_edit_style)

        self._end_edit = QDateEdit()
        self._end_edit.setCalendarPopup(True)
        self._end_edit.setDisplayFormat("dd/MM/yyyy")
        self._end_edit.setStyleSheet(_date_edit_style)

        if self._period.date_ranges:
            start_date = min(s for s, _ in self._period.date_ranges)
            end_date   = max(e for _, e in self._period.date_ranges)
            self._start_edit.setDate(
                QDate(start_date.year, start_date.month, start_date.day)
            )
            self._end_edit.setDate(
                QDate(end_date.year, end_date.month, end_date.day)
            )

        range_layout.addWidget(QLabel("Start:"))
        range_layout.addWidget(self._start_edit)
        range_layout.addWidget(QLabel("End:"))
        range_layout.addWidget(self._end_edit)
        range_layout.addStretch()

        range_layout.addWidget(_build_legend())

        self._start_edit.dateChanged.connect(self._on_range_changed)
        self._end_edit.dateChanged.connect(self._on_range_changed)

        outer.addWidget(range_row)

        # §2.4.1 — Year calendar ────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMinimumHeight(260)

        self._cal_container = QWidget()
        self._cal_layout = QGridLayout(self._cal_container)
        self._cal_layout.setSpacing(8)
        self._cal_layout.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(self._cal_container)
        outer.addWidget(scroll)

        self._rebuild_calendar()

        if self._multi_range:
            self._multi_range_notice.setVisible(True)
            self._start_edit.setEnabled(False)
            self._end_edit.setEnabled(False)

    def _rebuild_calendar(self) -> None:
        """Recreate all month widgets from the current period state."""
        self._building = True
        self._day_buttons.clear()

        # Remove old month widgets
        while self._cal_layout.count():
            item = self._cal_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._period.date_ranges:
            self._building = False
            return

        range_start = min(s for s, _ in self._period.date_ranges)
        range_end   = max(e for _, e in self._period.date_ranges)

        # Enumerate all calendar months covered by [range_start, range_end]
        current_month = date(range_start.year, range_start.month, 1)
        end_month = date(range_end.year, range_end.month, 1)

        _GRID_COLS = 2
        month_index = 0

        while current_month <= end_month:
            month_widget = _MonthWidget(
                current_month.year,
                current_month.month,
                date_ranges=self._period.date_ranges,
                excluded_dates=self._period.excluded_dates,
            )
            for d, btn in month_widget.day_buttons().items():
                if btn.isEnabled():
                    btn.toggled_date.connect(self._on_day_toggled)
                self._day_buttons[d] = btn

            grid_row, grid_col = divmod(month_index, _GRID_COLS)
            self._cal_layout.addWidget(month_widget, grid_row, grid_col)
            month_index += 1

            # Advance to next month
            if current_month.month == 12:
                current_month = date(current_month.year + 1, 1, 1)
            else:
                current_month = date(
                    current_month.year,
                    current_month.month + 1,
                    1,
                )

        for c in range(_GRID_COLS):
            self._cal_layout.setColumnStretch(c, 1)

        self._building = False

    # ── Event handlers ─────────────────────────────────────────────────────────

    def _on_day_toggled(self, d: date) -> None:
        """§2.4.2 — Toggle one date between active and excluded."""
        if d in self._period.excluded_dates:
            self._period.excluded_dates.discard(d)
        else:
            self._period.excluded_dates.add(d)

        btn = self._day_buttons.get(d)
        if btn:
            btn.set_excluded(d in self._period.excluded_dates)

        if not self._building:
            self.period_changed.emit()

    def _on_range_changed(self) -> None:
        """§2.4.3 — Sync the period date range with the QDateEdit values."""
        if self._multi_range or self._building or self._showing_error:
            return

        start_qdate = self._start_edit.date()
        end_qdate = self._end_edit.date()
        new_start = date(
            start_qdate.year(),
            start_qdate.month(),
            start_qdate.day(),
        )
        new_end = date(
            end_qdate.year(),
            end_qdate.month(),
            end_qdate.day(),
        )

        if new_start > new_end:
            self._showing_error = True
            QMessageBox.warning(
                self,
                "Invalid Date Range",
                "The <b>Start Date</b> must be before the <b>End Date</b>.<br><br>"
                "Please select a valid date range.",
            )
            self._showing_error = False
            # Reset controls to the model's current valid range so UI stays in sync
            if self._period.date_ranges:
                start_date = min(s for s, _ in self._period.date_ranges)
                end_date   = max(e for _, e in self._period.date_ranges)
                self._start_edit.blockSignals(True)
                self._end_edit.blockSignals(True)
                self._start_edit.setDate(
                    QDate(start_date.year, start_date.month, start_date.day)
                )
                self._end_edit.setDate(
                    QDate(end_date.year, end_date.month, end_date.day)
                )
                self._start_edit.blockSignals(False)
                self._end_edit.blockSignals(False)
            return

        # Trim excluded dates that fall outside the new range
        self._period.excluded_dates = {
            d
            for d in self._period.excluded_dates
            if new_start <= d <= new_end
        }
        self._period.date_ranges = [(new_start, new_end)]

        self._rebuild_calendar()
        self.period_changed.emit()
