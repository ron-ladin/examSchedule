"""
Widget: _ResultsPanel — Schedule Results Tab (SRS §3.1–§3.5)
--------------------------------------------------------------
Shows one exam-period card per period with independent Prev/Next navigation.
Each card has a "Load More" button when more schedules exist beyond the initial
RESULT_CAP batch — clicking it spawns a background subprocess to fetch them all.

Public API:
    load(schedules_by_period, courses_by_id, prog_color_map, truncated_periods)
"""

import logging
import multiprocessing
from datetime import date, timedelta
from pathlib import Path
from queue import Empty as _QueueEmpty

from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QSize, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGraphicsOpacityEffect,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.ui.assets.animated_widgets import AnimatedPlaceholder

from src.controller import DesktopController
from src.domain.course import Course
from src.domain.schedule import Schedule
from src.domain.semester import display_semester

logger = logging.getLogger(__name__)

_SPINNER_CHARS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class _CalendarCellDelegate(QStyledItemDelegate):
    """Custom painter for schedule calendar cells.

    Dates WITH exams: bold purple header (signals clickability).
    Dates without exams: muted gray header.
    Course lines: name darker, meta line lighter.
    """

    _DATE_FG_EXAM  = QColor("#7C3AED")  # violet-700 — clickable exam date
    _DATE_FG_EMPTY = QColor("#94A3B8")  # slate-400  — no exam
    _COURSE_FG     = QColor("#1F2937")  # gray-900
    _META_FG       = QColor("#6B7280")  # gray-500
    _SEP_COLOR     = QColor("#BFDBFE")  # blue-200

    def paint(self, painter, option, index) -> None:
        text: str = index.data(Qt.ItemDataRole.DisplayRole) or ""
        bg = index.data(Qt.ItemDataRole.BackgroundRole)

        painter.save()

        rect = option.rect
        if bg is not None:
            painter.fillRect(rect, bg)
        else:
            painter.fillRect(rect, Qt.GlobalColor.white)

        if text:
            self._draw_cell(painter, rect, text, bg)

        painter.restore()

    def _draw_cell(self, painter, rect, text: str, bg=None) -> None:
        lines = text.split('\n')
        pad = 5

        # Colored left accent stripe for cells that have exam data
        has_exams = len(lines) > 2
        left_offset = pad
        if has_exams and bg is not None:
            stripe_color = bg.color() if isinstance(bg, QBrush) else QColor(bg)
            stripe_color.setAlpha(210)
            painter.fillRect(QRect(rect.left(), rect.top(), 4, rect.height()), stripe_color)
            left_offset = 9

        r = rect.adjusted(left_offset, pad, -pad, -pad)
        y = r.top()

        # ── Date header (purple if exams, gray if empty) ──────────────────────
        has_exams = len(lines) > 2
        date_font = QFont(painter.font())
        date_font.setBold(True)
        date_font.setPointSize(9)
        painter.setFont(date_font)
        painter.setPen(self._DATE_FG_EXAM if has_exams else self._DATE_FG_EMPTY)
        painter.drawText(
            QRect(r.left(), y, r.width(), 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            lines[0],
        )
        y += 18

        # ── Thin separator ────────────────────────────────────────────────────
        rest_start = 1
        if len(lines) > 1 and '─' in lines[1]:
            painter.setPen(QPen(self._SEP_COLOR, 1))
            painter.drawLine(r.left(), y + 1, r.left() + min(r.width(), 70), y + 1)
            y += 6
            rest_start = 2

        # ── Course lines (name darker, ID·type·prog lighter) ─────────────────
        body_font = QFont(painter.font())
        body_font.setBold(False)
        body_font.setPointSize(8)
        painter.setFont(body_font)

        for line in lines[rest_start:]:
            if y + 12 > r.bottom():
                break
            is_meta = '·' in line
            painter.setPen(self._META_FG if is_meta else self._COURSE_FG)
            painter.drawText(
                QRect(r.left(), y, r.width(), 13),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                line.strip(),
            )
            y += 13

    def sizeHint(self, option, index) -> QSize:
        text: str = index.data(Qt.ItemDataRole.DisplayRole) or ""
        n = max(1, text.count('\n') + 1)
        return QSize(option.rect.width() or 120, max(52, 24 + n * 13))


def _make_data_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setMinimumHeight(36)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    return table


def _display_period_key(period_key: str) -> str:
    if " - " not in period_key:
        return period_key
    semester, moed = period_key.split(" - ", 1)
    return f"{display_semester(semester.strip())} — {moed.strip()}"


class _ResultsPanel(QWidget):
    """
    Tab 3 — Schedule Results.

    Each exam period is a card with its own Prev/Next navigator and an optional
    "Load More" button that fires a background subprocess to fetch the full set.
    """

    def __init__(self, controller: DesktopController, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._schedules_by_period: dict[str, list[Schedule]] = {}
        self._courses_by_id: dict[str, Course] = {}
        self._prog_color_map: dict[str, str] = {}
        self._period_indices: dict[str, int] = {}
        self._truncated_periods: set[str] = set()
        # Per-card widget refs
        self._counter_labels: dict[str, QLabel] = {}
        self._cal_tables: dict[str, QTableWidget] = {}
        self._prev_btns: dict[str, QPushButton] = {}
        self._next_btns: dict[str, QPushButton] = {}
        self._load_more_btns: dict[str, QPushButton] = {}
        self._load_more_chunk_btns: dict[str, QPushButton] = {}
        # Load-more async state
        self._lm_queues: dict[str, multiprocessing.Queue] = {}
        self._lm_chunk_sizes: dict[str, int | None] = {}
        self._lm_procs: dict[str, multiprocessing.Process] = {}
        self._lm_timers: dict[str, QTimer] = {}
        self._lm_ticks: dict[str, int] = {}
        self._fade_anim: QPropertyAnimation | None = None
        self._total_by_period: dict[str, int] = {}
        # Maps period_key → {(row, col): (date, [course_id, ...])}
        self._cell_data: dict[str, dict[tuple[int, int], tuple]] = {}
        self._setup_ui()

    # ── Public API ────────────────────────────────────────────────────────────

    def load(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        truncated_periods: set[str] | None = None,
    ) -> None:
        self._schedules_by_period = schedules_by_period
        self._courses_by_id = courses_by_id
        self._prog_color_map = prog_color_map
        self._truncated_periods = truncated_periods or set()
        self._period_indices = {k: 0 for k in schedules_by_period}
        self._total_by_period = {}
        # Only record true totals for non-truncated periods; truncated periods
        # get their real total only after Load More completes.
        for key, scheds in schedules_by_period.items():
            if key not in self._truncated_periods:
                self._total_by_period[key] = len(scheds)

        # Merge in empty entries for exam periods that have no schedules so
        # their calendars are always rendered (showing "0 / 0").
        all_period_keys = [p.get_key() for p in self._controller.get_exam_periods()]
        merged: dict[str, list] = {k: [] for k in all_period_keys}
        merged.update(schedules_by_period)
        self._schedules_by_period = merged
        self._period_indices = {k: 0 for k in merged}

        # Clear existing cards
        while self._cards_splitter.count():
            w = self._cards_splitter.widget(0)
            if w:
                w.setParent(None)
                w.deleteLater()
        self._counter_labels.clear()
        self._cal_tables.clear()
        self._prev_btns.clear()
        self._next_btns.clear()
        self._load_more_btns.clear()
        self._load_more_chunk_btns.clear()
        self._cell_data.clear()

        for period_key in merged:
            self._cards_splitter.addWidget(self._build_period_card(period_key))

        self._update_summary()
        self._placeholder.setVisible(False)
        self._content.setVisible(True)

        effect = QGraphicsOpacityEffect(self._content)
        self._content.setGraphicsEffect(effect)
        self._fade_anim = QPropertyAnimation(effect, b"opacity", self._content)
        self._fade_anim.setDuration(350)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.start()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setStyleSheet("background: transparent;")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        self._placeholder = AnimatedPlaceholder(
            "No schedules generated yet.\n\n"
            "Load files, select a programme, then click  ▶  Generate Schedule."
        )
        root.addWidget(self._placeholder)

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content.setVisible(False)
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)

        action_row = QHBoxLayout()
        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet(
            "color: #059669; font-weight: 600; font-size: 12px;"
        )
        action_row.addWidget(self._summary_lbl)
        action_row.addStretch()
        save_btn = QPushButton("⬇  Export Schedule")
        save_btn.clicked.connect(self._on_save)
        action_row.addWidget(save_btn)
        cl.addLayout(action_row)

        self._cards_splitter = QSplitter(Qt.Orientation.Vertical)
        self._cards_splitter.setChildrenCollapsible(False)
        self._cards_splitter.setHandleWidth(8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(self._cards_splitter)
        cl.addWidget(scroll)

        root.addWidget(self._content)

    # ── Period cards ──────────────────────────────────────────────────────────

    def _build_period_card(self, period_key: str) -> QGroupBox:
        card = QGroupBox(_display_period_key(period_key))
        card.setStyleSheet("""
            QGroupBox {
                background: #FAFCFF;
                border: 1px solid #DBEAFE;
                border-radius: 12px;
                margin-top: 22px;
                padding: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 4px 16px;
                background: #2563EB;
                color: white;
                border-radius: 8px;
                font-weight: 700;
                font-size: 12px;
            }
        """)
        card.setMinimumHeight(220)
        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        # Navigation bar
        nav = QHBoxLayout()
        prev_btn = QPushButton("◀  Prev")
        prev_btn.setFixedWidth(90)
        prev_btn.clicked.connect(lambda _=False, k=period_key: self._go_prev_period(k))

        counter = QLabel("Loading…")
        counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        counter.setStyleSheet(
            "font-weight: 700; color: #1D4ED8; font-size: 13px;"
            "background: #EFF6FF; border: 1px solid #BFDBFE;"
            "border-radius: 10px; padding: 6px 20px;"
        )

        next_btn = QPushButton("Next  ▶")
        next_btn.setFixedWidth(90)
        next_btn.clicked.connect(lambda _=False, k=period_key: self._go_next_period(k))

        nav.addWidget(prev_btn)
        nav.addStretch()
        nav.addWidget(counter)
        nav.addStretch()
        nav.addWidget(next_btn)
        layout.addLayout(nav)

        # Two load-more buttons side-by-side — shown when period was truncated
        has_more = period_key in self._truncated_periods
        lm_row = QHBoxLayout()
        lm_row.setSpacing(8)

        chunk_btn = QPushButton("⟳  +200 more options")
        chunk_btn.setStyleSheet(
            "color: #2563EB; border: 2px solid #2563EB; border-radius: 8px;"
            "padding: 6px 12px; font-size: 11px; font-weight: 600; background: #EFF6FF;"
        )
        chunk_btn.setVisible(has_more)
        chunk_btn.clicked.connect(
            lambda _=False, k=period_key: self._on_load_more(k, chunk_size=200)
        )

        load_all_btn = QPushButton("⟳  Load all remaining")
        load_all_btn.setStyleSheet(
            "color: #D97706; border: 2px solid #D97706; border-radius: 8px;"
            "padding: 6px 12px; font-size: 11px; font-weight: 600; background: #FFFBEB;"
        )
        load_all_btn.setVisible(has_more)
        load_all_btn.clicked.connect(
            lambda _=False, k=period_key: self._on_load_more(k, chunk_size=None)
        )

        lm_row.addWidget(chunk_btn)
        lm_row.addWidget(load_all_btn)
        lm_row.addStretch()
        layout.addLayout(lm_row)

        # Calendar table
        table = _make_data_table(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setItemDelegate(_CalendarCellDelegate(table))
        table.setStyleSheet("""
            QTableWidget {
                border: none;
                border-radius: 8px;
                background: white;
                gridline-color: #E8F0FE;
            }
            QHeaderView::section {
                background: #2563EB;
                color: white;
                font-weight: 700;
                font-size: 11px;
                padding: 6px 4px;
                border: none;
                border-right: 1px solid #1D4ED8;
            }
            QHeaderView::section:last-child { border-right: none; }
        """)
        layout.addWidget(table)

        self._counter_labels[period_key] = counter
        self._cal_tables[period_key] = table
        self._prev_btns[period_key] = prev_btn
        self._next_btns[period_key] = next_btn
        self._load_more_btns[period_key] = load_all_btn
        self._load_more_chunk_btns[period_key] = chunk_btn

        table.cellClicked.connect(
            lambda r, c, k=period_key: self._on_cell_clicked(k, r, c)
        )

        self._refresh_period_card(period_key)
        return card

    def _refresh_period_card(self, period_key: str) -> None:
        schedules = self._schedules_by_period[period_key]
        idx = self._period_indices[period_key]
        total = len(schedules)
        has_more = self._controller.has_more_schedules(period_key)

        known_total = self._total_by_period.get(period_key)
        display_total = known_total if known_total is not None else total

        if total == 0:
            nav_text = "0 / 0"
        else:
            nav_text = f"{idx + 1:,} / {display_total:,}"

        self._counter_labels[period_key].setText(nav_text)
        self._prev_btns[period_key].setEnabled(idx > 0)
        self._next_btns[period_key].setEnabled(idx < total - 1 or has_more)

        if period_key in self._load_more_btns:
            self._load_more_btns[period_key].setVisible(has_more)
        if period_key in self._load_more_chunk_btns:
            self._load_more_chunk_btns[period_key].setVisible(has_more)

        if schedules:
            self._populate_calendar(self._cal_tables[period_key], schedules[idx], period_key)
        else:
            table = self._cal_tables[period_key]
            table.clearContents()
            table.setRowCount(0)

        self._update_summary()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _go_prev_period(self, period_key: str) -> None:
        if self._period_indices[period_key] > 0:
            self._period_indices[period_key] -= 1
            self._refresh_period_card(period_key)

    def _go_next_period(self, period_key: str) -> None:
        idx = self._period_indices[period_key]
        target = idx + 1
        schedules = self._schedules_by_period[period_key]

        if target >= len(schedules) and self._controller.has_more_schedules(period_key):
            more = self._controller.load_more_schedules(period_key)
            if more:
                schedules.extend(more)

        if target < len(schedules):
            self._period_indices[period_key] = target

        # Always refresh so button states update even if index didn't advance
        self._refresh_period_card(period_key)

    # ── Load More (async subprocess) ──────────────────────────────────────────

    def _on_load_more(self, period_key: str, chunk_size: int | None = None) -> None:
        already = len(self._schedules_by_period[period_key])
        q, proc = self._controller.start_load_more_for_period(period_key, already)
        self._lm_queues[period_key] = q
        self._lm_procs[period_key] = proc
        self._lm_ticks[period_key] = 0
        self._lm_chunk_sizes[period_key] = chunk_size

        label = "⠋  Loading 200…" if chunk_size is not None else "⠋  Loading all…"
        btn = self._load_more_btns[period_key]
        btn.setEnabled(False)
        btn.setText(label)
        chunk_btn = self._load_more_chunk_btns.get(period_key)
        if chunk_btn:
            chunk_btn.setEnabled(False)

        timer = QTimer(self)
        timer.timeout.connect(lambda: self._poll_load_more(period_key))
        timer.start(150)
        self._lm_timers[period_key] = timer

    def _poll_load_more(self, period_key: str) -> None:
        tick = self._lm_ticks.get(period_key, 0)
        spin = _SPINNER_CHARS[tick % len(_SPINNER_CHARS)]
        self._lm_ticks[period_key] = tick + 1
        chunk_size = self._lm_chunk_sizes.get(period_key)
        spin_label = f"{spin}  Loading {'200' if chunk_size is not None else 'all'}…"

        btn = self._load_more_btns.get(period_key)
        if btn:
            btn.setText(spin_label)

        try:
            result = self._lm_queues[period_key].get_nowait()
        except (_QueueEmpty, OSError):
            return

        timer = self._lm_timers.pop(period_key, None)
        if timer:
            timer.stop()

        if not (len(result) == 4 and result[0]):
            err = result[1] if len(result) > 1 else "Unknown error"
            if btn:
                btn.setEnabled(True)
                btn.setText("⚠  Load failed — retry")
            chunk_btn = self._load_more_chunk_btns.get(period_key)
            if chunk_btn:
                chunk_btn.setEnabled(True)
            logger.error("Load more failed for %s: %s", period_key, err)
            return

        all_by_period = result[1]
        new_for_period = all_by_period.get(period_key, [])
        already = len(self._schedules_by_period[period_key])
        chunk_size = self._lm_chunk_sizes.get(period_key)

        if chunk_size is not None:
            extra = new_for_period[already:already + chunk_size]
            still_more = len(new_for_period) > already + chunk_size
        else:
            extra = new_for_period[already:]
            still_more = False

        for k, v in all_by_period.items():
            self._total_by_period[k] = len(v)

        if extra:
            self._schedules_by_period[period_key].extend(extra)

        self._controller._has_more_schedules[period_key] = still_more
        if not still_more:
            self._truncated_periods.discard(period_key)
        self._refresh_period_card(period_key)

        if still_more:
            if btn:
                btn.setEnabled(True)
                btn.setText("⟳  Load all remaining")
            chunk_btn = self._load_more_chunk_btns.get(period_key)
            if chunk_btn:
                chunk_btn.setEnabled(True)
                chunk_btn.setText("⟳  +200 more options")

    # ── Summary ───────────────────────────────────────────────────────────────

    def _update_summary(self) -> None:
        if not self._schedules_by_period:
            return

        # Exclude empty (0-schedule) periods from the combination count
        non_empty = {k: v for k, v in self._schedules_by_period.items() if v}
        combined = self._controller.get_combined_schedule_count(non_empty)
        all_known = bool(self._total_by_period) and all(
            k in self._total_by_period for k in non_empty
        )
        if all_known:
            total_combined = 1
            for k in non_empty:
                total_combined *= self._total_by_period[k]
            combined_str = f"{combined:,} / {total_combined:,}"
        else:
            combined_str = f"{combined:,}"

        if combined == 0:
            self._summary_lbl.setStyleSheet(
                "color: #DC2626; font-weight: 600; font-size: 12px;"
            )
            self._summary_lbl.setText("⚠  No valid combined schedules found.")
        else:
            self._summary_lbl.setStyleSheet(
                "color: #059669; font-weight: 600; font-size: 12px;"
            )
            self._summary_lbl.setText(f"✓  {combined_str} schedules generated")

    # ── Calendar ──────────────────────────────────────────────────────────────

    def _populate_calendar(
        self, table: QTableWidget, schedule: Schedule, period_key: str = ""
    ) -> None:
        table.clearContents()
        table.setRowCount(0)
        self._cell_data[period_key] = {}

        if not schedule.assignments:
            return

        date_to_ids: dict[date, list[str]] = {}
        for course_id, exam_date in schedule.assignments.items():
            date_to_ids.setdefault(exam_date, []).append(course_id)

        all_dates = sorted(date_to_ids)
        start, end = all_dates[0], all_dates[-1]
        week_start = start - timedelta(days=start.weekday())
        last_sunday = end + timedelta(days=6 - end.weekday())
        num_weeks = (last_sunday - week_start).days // 7 + 1

        table.setRowCount(num_weeks)

        for week in range(num_weeks):
            for dow in range(7):
                current_date = week_start + timedelta(days=week * 7 + dow)
                course_ids = date_to_ids.get(current_date, [])
                first_prog = None
                course_lines: list[str] = []

                for course_id in course_ids:
                    course = self._courses_by_id.get(course_id)
                    if not course:
                        course_lines.append(course_id)
                        continue

                    relevant = next(
                        (o for o in course.offerings if o.program_id in self._prog_color_map),
                        None,
                    )
                    req = "E" if (relevant and relevant.is_elective()) else "O"
                    prog_id = relevant.program_id if relevant else ""

                    if first_prog is None:
                        first_prog = prog_id

                    course_lines.append(f"  {course.name[:18]}")
                    prog_label = prog_id if prog_id else "—"
                    course_lines.append(f"  {course_id}  ·  {req}  ·  {prog_label}")

                date_header = current_date.strftime("%a %d/%m")
                cell_text = (
                    f"{date_header}\n{'─' * 14}\n" + "\n".join(course_lines)
                    if course_lines
                    else date_header
                )

                item = QTableWidgetItem(cell_text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                if course_ids:
                    item.setToolTip("Click to view exam details")

                if first_prog and first_prog in self._prog_color_map:
                    c = QColor(self._prog_color_map[first_prog])
                    c.setAlpha(75)
                    item.setBackground(c)

                table.setItem(week, dow, item)
                self._cell_data[period_key][(week, dow)] = (current_date, list(course_ids))

        table.resizeRowsToContents()

    def _on_cell_clicked(self, period_key: str, row: int, col: int) -> None:
        cell_info = self._cell_data.get(period_key, {}).get((row, col))
        if cell_info is None:
            return
        exam_date, course_ids = cell_info
        if not course_ids:
            return
        from src.ui.exam_detail_dialog import ExamDetailDialog
        dialog = ExamDetailDialog(
            exam_date, course_ids,
            self._courses_by_id, self._prog_color_map,
            parent=self,
        )
        dialog.exec()

    # ── Export ────────────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        if not self._schedules_by_period:
            QMessageBox.warning(self, "Nothing to Save", "No schedules have been generated.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Schedule", "schedules.txt", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return

        selected = {
            key: [self._schedules_by_period[key][self._period_indices[key]]]
            for key in self._schedules_by_period
            if self._schedules_by_period[key]
        }

        if not selected:
            QMessageBox.warning(self, "Nothing to Save", "No schedules are currently displayed.")
            return

        try:
            self._controller.export(selected, Path(path))
            QMessageBox.information(self, "Saved", f"Schedule saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            logger.exception("Save failed")
