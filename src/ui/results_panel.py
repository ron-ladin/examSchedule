"""
Widget: _ResultsPanel — Schedule Results Tab (SRS §3.1–§3.5)
--------------------------------------------------------------
Shows one exam-period card per period with independent Prev/Next navigation.
Each card has a "Load More" button when more schedules exist beyond the initial
RESULT_BATCH_SIZE batch — clicking it spawns a background subprocess to fetch
only the next batch.

Public API:
    load(schedules_by_period, courses_by_id, prog_color_map, truncated_periods)
"""

import logging
import multiprocessing
from datetime import date, timedelta
from pathlib import Path
from queue import Empty as _QueueEmpty

from PyQt6.QtCore import Qt, QRect, QSize, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
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

from src.controller import DesktopController, RESULT_BATCH_SIZE
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

    _DATE_FG_EXAM = QColor("#7C3AED")
    _DATE_FG_EMPTY = QColor("#94A3B8")
    _COURSE_FG = QColor("#1F2937")
    _META_FG = QColor("#6B7280")
    _SEP_COLOR = QColor("#BFDBFE")

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
        lines = text.split("\n")
        pad = 5

        has_exams = len(lines) > 2
        left_offset = pad

        if has_exams and bg is not None:
            stripe_color = bg.color() if isinstance(bg, QBrush) else QColor(bg)
            stripe_color.setAlpha(210)
            painter.fillRect(
                QRect(rect.left(), rect.top(), 4, rect.height()),
                stripe_color,
            )
            left_offset = 9

        r = rect.adjusted(left_offset, pad, -pad, -pad)
        y = r.top()

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

        rest_start = 1
        if len(lines) > 1 and "─" in lines[1]:
            painter.setPen(QPen(self._SEP_COLOR, 1))
            painter.drawLine(r.left(), y + 1, r.left() + min(r.width(), 70), y + 1)
            y += 6
            rest_start = 2

        body_font = QFont(painter.font())
        body_font.setBold(False)
        body_font.setPointSize(8)
        painter.setFont(body_font)

        for line in lines[rest_start:]:
            if y + 12 > r.bottom():
                break

            is_meta = "·" in line
            painter.setPen(self._META_FG if is_meta else self._COURSE_FG)
            painter.drawText(
                QRect(r.left(), y, r.width(), 13),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                line.strip(),
            )
            y += 13

    def sizeHint(self, option, index) -> QSize:
        text: str = index.data(Qt.ItemDataRole.DisplayRole) or ""
        n = max(1, text.count("\n") + 1)
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

        self._counter_labels: dict[str, QLabel] = {}
        self._cal_tables: dict[str, QTableWidget] = {}
        self._prev_btns: dict[str, QPushButton] = {}
        self._next_btns: dict[str, QPushButton] = {}
        self._load_more_btns: dict[str, QPushButton] = {}
        self._load_more_chunk_btns: dict[str, QPushButton] = {}

        self._lm_queues: dict[str, multiprocessing.Queue] = {}
        self._lm_chunk_sizes: dict[str, int | None] = {}
        self._lm_procs: dict[str, multiprocessing.Process] = {}
        self._lm_timers: dict[str, QTimer] = {}
        self._lm_ticks: dict[str, int] = {}
        self._lm_advance_after_load: set[str] = set()

        self._total_by_period: dict[str, int] = {}
        self._cell_data: dict[str, dict[tuple[int, int], tuple]] = {}

        self._has_stale_results: bool = False
        self._stale_banner: QLabel = QLabel()
        self._save_btn: QPushButton = QPushButton()

        self._setup_ui()

    def mark_stale(self) -> None:
        """Show the stale-data warning and disable Export."""
        self._has_stale_results = True
        self._stale_banner.setVisible(True)
        self._save_btn.setEnabled(False)

    def clear_stale(self) -> None:
        """Hide the stale-data warning and re-enable Export."""
        self._has_stale_results = False
        self._stale_banner.setVisible(False)
        self._save_btn.setEnabled(True)

    def load(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        courses_by_id: dict[str, Course],
        prog_color_map: dict[str, str],
        truncated_periods: set[str] | None = None,
    ) -> None:
        self.clear_stale()

        self._schedules_by_period = schedules_by_period
        self._courses_by_id = courses_by_id
        self._prog_color_map = prog_color_map
        self._truncated_periods = truncated_periods or set()
        self._period_indices = {k: 0 for k in schedules_by_period}
        self._total_by_period = {}

        for key, scheds in schedules_by_period.items():
            if key not in self._truncated_periods:
                self._total_by_period[key] = len(scheds)

        all_period_keys = [p.get_key() for p in self._controller.get_exam_periods()]
        merged: dict[str, list[Schedule]] = {k: [] for k in all_period_keys}
        merged.update(schedules_by_period)

        self._schedules_by_period = merged
        self._period_indices = {k: 0 for k in merged}

        while self._cards_splitter.count():
            widget = self._cards_splitter.widget(0)
            if widget:
                widget.setParent(None)
                widget.deleteLater()

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

        # Avoid opacity effects while rebuilding result widgets.
        # QGraphicsOpacityEffect caused QPainter warnings and visual flicker.
        self._content.setGraphicsEffect(None)

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

        self._save_btn = QPushButton("⬇  Export Schedule")
        self._save_btn.clicked.connect(self._on_save)
        action_row.addWidget(self._save_btn)

        cl.addLayout(action_row)

        self._stale_banner = QLabel(
            "⚠  Exam period dates were changed after generation. "
            "The displayed schedules may contain now-excluded dates. "
            "Click  ▶  Generate again to update."
        )
        self._stale_banner.setWordWrap(True)
        self._stale_banner.setStyleSheet(
            "background: #FEF3C7; color: #92400E;"
            " border: 1px solid #F59E0B; border-radius: 8px;"
            " padding: 8px 14px; font-size: 12px; font-weight: 500;"
        )
        self._stale_banner.setVisible(False)

        cl.addWidget(self._stale_banner)

        tip_lbl = QLabel("💡  Tip: Click on any scheduled exam date to view full details.")
        tip_lbl.setStyleSheet(
            "background: rgba(0,90,194,0.06); color: #004394;"
            " border: 1px solid rgba(0,90,194,0.12); border-radius: 8px;"
            " padding: 8px 14px; font-size: 12px; font-weight: 500;"
        )
        tip_lbl.setWordWrap(True)

        cl.addWidget(tip_lbl)

        self._cards_splitter = QSplitter(Qt.Orientation.Vertical)
        self._cards_splitter.setChildrenCollapsible(False)
        self._cards_splitter.setHandleWidth(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(self._cards_splitter)

        cl.addWidget(scroll)
        root.addWidget(self._content)

    def _build_period_card(self, period_key: str) -> QGroupBox:
        card = QGroupBox(_display_period_key(period_key))
        card.setStyleSheet("""
            QGroupBox {
                background: rgba(255, 255, 255, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.9);
                border-radius: 12px;
                margin-top: 22px;
                padding: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 4px 16px;
                background: #005ac2;
                color: white;
                border-radius: 8px;
                font-weight: 700;
                font-size: 12px;
            }
        """)
        card.setMinimumHeight(320)

        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        nav = QHBoxLayout()

        prev_btn = QPushButton("◀  Prev")
        prev_btn.setFixedWidth(90)
        prev_btn.clicked.connect(lambda _=False, k=period_key: self._go_prev_period(k))

        counter = QLabel("Loading…")
        counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        counter.setStyleSheet(
            "font-weight: 700; color: #005ac2; font-size: 13px;"
            "background: rgba(0, 90, 194, 0.06);"
            "border: 1px solid rgba(0, 90, 194, 0.15);"
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

        has_more = period_key in self._truncated_periods

        lm_row = QHBoxLayout()
        lm_row.setSpacing(8)

        chunk_btn = QPushButton(f"⟳  +{RESULT_BATCH_SIZE:,} more options")
        chunk_btn.setStyleSheet(
            "color: #005ac2; border: 2px solid #005ac2; border-radius: 8px;"
            "padding: 6px 12px; font-size: 11px; font-weight: 600;"
            "background: rgba(0, 90, 194, 0.06);"
        )
        chunk_btn.setVisible(has_more)
        chunk_btn.clicked.connect(lambda _=False, k=period_key: self._on_load_more(k))

        lm_row.addWidget(chunk_btn)
        lm_row.addStretch()

        layout.addLayout(lm_row)

        table = _make_data_table(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
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

        self._counter_labels[period_key] = counter
        self._cal_tables[period_key] = table
        self._prev_btns[period_key] = prev_btn
        self._next_btns[period_key] = next_btn
        self._load_more_btns[period_key] = chunk_btn
        self._load_more_chunk_btns[period_key] = chunk_btn

        table.cellClicked.connect(
            lambda row, col, k=period_key: self._on_cell_clicked(k, row, col)
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
            self._populate_calendar(
                self._cal_tables[period_key],
                schedules[idx],
                period_key,
            )
        else:
            table = self._cal_tables[period_key]
            table.clearContents()
            table.setRowCount(0)

        self._update_summary()

    def _go_prev_period(self, period_key: str) -> None:
        if self._period_indices[period_key] > 0:
            self._period_indices[period_key] -= 1
            self._refresh_period_card(period_key)

    def _go_next_period(self, period_key: str) -> None:
        idx = self._period_indices[period_key]
        target = idx + 1
        schedules = self._schedules_by_period[period_key]

        if target >= len(schedules) and self._controller.has_more_schedules(period_key):
            self._lm_advance_after_load.add(period_key)
            self._on_load_more(period_key)
            return

        if target < len(schedules):
            self._period_indices[period_key] = target

        remaining_loaded = len(schedules) - self._period_indices[period_key] - 1

        if (
            remaining_loaded <= 100
            and self._controller.has_more_schedules(period_key)
            and period_key not in self._lm_procs
        ):
            self._on_load_more(period_key)

        self._refresh_period_card(period_key)

    def _on_load_more(self, period_key: str, chunk_size: int | None = None) -> None:
        if period_key in self._lm_procs:
            return

        already = len(self._schedules_by_period[period_key])
        queue, proc = self._controller.start_load_more_for_period(period_key, already)

        self._lm_queues[period_key] = queue
        self._lm_procs[period_key] = proc
        self._lm_ticks[period_key] = 0
        self._lm_chunk_sizes[period_key] = RESULT_BATCH_SIZE

        btn = self._load_more_btns[period_key]
        btn.setEnabled(False)
        btn.setText(f"⠋  Loading {RESULT_BATCH_SIZE:,}…")

        timer = QTimer(self)
        timer.timeout.connect(lambda: self._poll_load_more(period_key))
        timer.start(150)

        self._lm_timers[period_key] = timer

    def _poll_load_more(self, period_key: str) -> None:
        tick = self._lm_ticks.get(period_key, 0)
        spinner = _SPINNER_CHARS[tick % len(_SPINNER_CHARS)]
        self._lm_ticks[period_key] = tick + 1

        btn = self._load_more_btns.get(period_key)
        if btn:
            btn.setText(f"{spinner}  Loading {RESULT_BATCH_SIZE:,}…")

        try:
            result = self._lm_queues[period_key].get_nowait()
        except (_QueueEmpty, OSError):
            return

        timer = self._lm_timers.pop(period_key, None)
        if timer:
            timer.stop()

        if not (
            isinstance(result, tuple)
            and len(result) == 4
            and result[0] is True
            and isinstance(result[1], dict)
            and isinstance(result[2], dict)
            and isinstance(result[3], set)
        ):
            error_details = (
                result[1]
                if isinstance(result, tuple) and len(result) > 1
                else result
            )

            if btn:
                btn.setEnabled(True)
                btn.setText("⚠  Load failed — retry")

            logger.error("Load more failed for %s: %s", period_key, error_details)
            self._cleanup_load_more_state(period_key, terminate=True)
            return

        _, all_by_period, _courses_by_id, truncated_periods = result

        old_len = len(self._schedules_by_period[period_key])
        extra = all_by_period.get(period_key, [])
        still_more = period_key in truncated_periods

        if extra:
            self._schedules_by_period[period_key].extend(extra)

        if period_key in self._lm_advance_after_load:
            self._lm_advance_after_load.discard(period_key)

            if extra and old_len < len(self._schedules_by_period[period_key]):
                self._period_indices[period_key] = old_len

        self._controller.set_has_more_for_period(period_key, still_more)

        if still_more:
            self._truncated_periods.add(period_key)
        else:
            self._truncated_periods.discard(period_key)
            self._total_by_period[period_key] = len(
                self._schedules_by_period[period_key]
            )

        self._cleanup_load_more_state(period_key)
        self._refresh_period_card(period_key)

        if still_more and btn:
            btn.setEnabled(True)
            btn.setText(f"⟳  +{RESULT_BATCH_SIZE:,} more options")

    def _cleanup_load_more_state(
        self,
        period_key: str,
        terminate: bool = False,
    ) -> None:
        timer = self._lm_timers.pop(period_key, None)
        if timer is not None:
            timer.stop()

        self._lm_queues.pop(period_key, None)
        self._lm_chunk_sizes.pop(period_key, None)
        self._lm_ticks.pop(period_key, None)
        self._lm_advance_after_load.discard(period_key)

        proc = self._lm_procs.pop(period_key, None)
        if proc is not None:
            try:
                if terminate and proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=0.5)

                    if proc.is_alive():
                        proc.kill()
                        proc.join(timeout=0.5)

                proc.join(timeout=0.1)
            except Exception:
                logger.debug("Failed cleaning up load-more process", exc_info=True)

    def _update_summary(self) -> None:
        if not self._schedules_by_period:
            return

        non_empty = {
            key: value
            for key, value in self._schedules_by_period.items()
            if value
        }

        combined = self._controller.get_combined_schedule_count(non_empty)

        all_known = bool(self._total_by_period) and all(
            key in self._total_by_period for key in non_empty
        )

        if all_known:
            total_combined = 1
            for key in non_empty:
                total_combined *= self._total_by_period[key]

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

    def _populate_calendar(
        self,
        table: QTableWidget,
        schedule: Schedule,
        period_key: str = "",
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
                        (
                            offering
                            for offering in course.offerings
                            if offering.program_id in self._prog_color_map
                        ),
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
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
                )

                if course_ids:
                    item.setToolTip("Click to view exam details")

                if first_prog and first_prog in self._prog_color_map:
                    color = QColor(self._prog_color_map[first_prog])
                    color.setAlpha(75)
                    item.setBackground(color)

                table.setItem(week, dow, item)
                self._cell_data[period_key][(week, dow)] = (
                    current_date,
                    list(course_ids),
                )

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
            exam_date,
            course_ids,
            self._courses_by_id,
            self._prog_color_map,
            parent=self,
        )
        dialog.exec()

    def _on_save(self) -> None:
        if self._has_stale_results:
            QMessageBox.warning(
                self,
                "Stale Schedules",
                "Exam period dates have changed since the last generation.\n\n"
                "Please click  ▶  Generate again before exporting.",
            )
            return

        if not self._schedules_by_period:
            QMessageBox.warning(
                self,
                "Nothing to Save",
                "No schedules have been generated.",
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Schedule",
            "schedules.txt",
            "Text files (*.txt);;All files (*)",
        )

        if not path:
            return

        selected = {
            key: [self._schedules_by_period[key][self._period_indices[key]]]
            for key in self._schedules_by_period
            if self._schedules_by_period[key]
        }

        if not selected:
            QMessageBox.warning(
                self,
                "Nothing to Save",
                "No schedules are currently displayed.",
            )
            return

        try:
            self._controller.export(selected, Path(path))
            QMessageBox.information(
                self,
                "Saved",
                f"Schedule saved to:\n{path}",
            )
        except Exception:
            QMessageBox.critical(
                self,
                "Save Error",
                "Could not save the schedule file. Please check the selected path and try again.",
            )
            logger.exception("Save failed")
