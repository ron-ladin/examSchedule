"""
Widget: ConfigScreen — Full-screen entry / configuration (Screen 0).

Layout
------
  Brand header   (fixed 64 px)
  Scroll area    (expands to fill window)
    └─ centred content (max 780 px wide)
         ├─ Steps pill
         ├─ Row: [Load Mode card] [Files card]
         └─ Study Programmes card
  Bottom footer  (fixed 76 px — Generate button ALWAYS visible here)

Signals
-------
generation_started(object)  → (selected_ids, prog_color_map)  IMMEDIATE on click
schedule_generated(object)  → full result tuple  when async subprocess finishes
generation_failed(str)      → error message
courses_changed(list[str])  → after courses or programme selection changes
periods_changed()           → after exam periods are (re)loaded
"""

import logging
import multiprocessing
import time
from pathlib import Path
from queue import Empty as _QueueEmpty

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.controller import DesktopController, _run_generation_process
from src.ui.assets.icons import BookIcon, CalendarIcon, GraduationIcon
from src.ui.assets.logo_widget import LogoWidget
from src.ui.tokens import PROGRAMME_COLOURS, PROGRAM_NAMES_MAPPING

logger = logging.getLogger(__name__)

_MAX_PROGS = 5
_MAX_GEN_SECS = 30


# ── module-level helpers ──────────────────────────────────────────────────────

def _section_lbl(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "font-size:10px; font-weight:700; color:#94A3B8;"
        " letter-spacing:0.6px; background:transparent;"
    )
    return lbl


def _card() -> QFrame:
    f = QFrame()
    f.setStyleSheet("QFrame { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; }")
    eff = QGraphicsDropShadowEffect()
    eff.setBlurRadius(14)
    eff.setColor(QColor(0, 0, 0, 14))
    eff.setOffset(0, 2)
    f.setGraphicsEffect(eff)
    return f


# ── ConfigScreen ──────────────────────────────────────────────────────────────

class ConfigScreen(QWidget):
    """Full-screen configuration (Screen 0)."""

    generation_started = pyqtSignal(object)  # (selected_ids, prog_color_map) — immediate
    schedule_generated = pyqtSignal(object)  # full result tuple — async
    generation_failed  = pyqtSignal(str)
    courses_changed    = pyqtSignal(list)
    periods_changed    = pyqtSignal()

    def __init__(self, controller: DesktopController, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._gen_process: multiprocessing.Process | None = None
        self._poll_timer: QTimer | None = None
        self._result_queue: multiprocessing.Queue | None = None
        self._pending_selected: list[str] = []
        self._pending_color_map: dict[str, str] = {}
        self._gen_start_time: float = 0.0
        self._dead_ticks: int = 0
        self._setup_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self._build_scroll_area(), 1)  # expands
        root.addWidget(self._build_footer())           # always visible

    def _build_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setObjectName("appHeader")
        hdr.setFixedHeight(64)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(32, 0, 32, 0)
        hl.setSpacing(12)
        hl.addWidget(LogoWidget(size=36))
        brand = QLabel("Syncacademic")
        brand.setStyleSheet(
            "font-size:20px; font-weight:800; color:#2563EB;"
            " letter-spacing:-0.5px; background:transparent;"
        )
        tagline = QLabel("Academic Command Center")
        tagline.setStyleSheet(
            "font-size:12px; color:#94A3B8; font-weight:500; background:transparent;"
        )
        hl.addWidget(brand)
        hl.addWidget(tagline)
        hl.addStretch()
        return hdr

    def _build_scroll_area(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:transparent; border:none;")

        outer = QWidget()
        outer.setStyleSheet("background:transparent;")
        ol = QHBoxLayout(outer)
        ol.setContentsMargins(32, 32, 32, 32)

        content = QWidget()
        content.setMaximumWidth(820)
        content.setStyleSheet("background:transparent;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(24)

        # Steps pill
        steps = QLabel("①  Load files   ·   ②  Select programmes   ·   ③  Generate")
        steps.setAlignment(Qt.AlignmentFlag.AlignCenter)
        steps.setStyleSheet(
            "font-size:11px; color:#64748B; background:#F1F5F9;"
            " border-radius:20px; padding:8px 20px; border:1px solid #E2E8F0;"
        )
        cl.addWidget(steps)

        top = QHBoxLayout()
        top.setSpacing(16)
        top.addWidget(self._build_mode_card(), 0)
        top.addWidget(self._build_files_card(), 1)
        cl.addLayout(top)

        cl.addWidget(self._build_prog_card())
        cl.addStretch(1)

        ol.addStretch(1)
        ol.addWidget(content, 0)
        ol.addStretch(1)
        scroll.setWidget(outer)
        return scroll

    def _build_mode_card(self) -> QFrame:
        c = _card()
        c.setFixedWidth(210)
        vl = QVBoxLayout(c)
        vl.setContentsMargins(20, 18, 20, 18)
        vl.setSpacing(8)
        vl.addWidget(_section_lbl("LOAD MODE"))
        self._mode_group = QButtonGroup(self)
        for label, hint_text in (
            ("Replace", "Clear all existing data"),
            ("Update",  "Merge with existing data"),
        ):
            rb = QRadioButton(label)
            rb.setStyleSheet("font-size:13px; color:#1F2937; font-weight:500; spacing:8px;")
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            self._mode_group.addButton(rb)
            vl.addWidget(rb)
            h = QLabel(hint_text)
            h.setStyleSheet(
                "font-size:9px; color:#94A3B8; margin-left:24px;"
                " margin-bottom:2px; background:transparent;"
            )
            vl.addWidget(h)
        self._mode_group.buttons()[0].setChecked(True)
        vl.addStretch()
        return c

    def _build_files_card(self) -> QFrame:
        c = _card()
        vl = QVBoxLayout(c)
        vl.setContentsMargins(20, 18, 20, 18)
        vl.setSpacing(10)
        vl.addWidget(_section_lbl("FILES"))

        specs = [
            (BookIcon(13, "#2563EB"),       "Courses",      "Load Courses",
             "_load_courses_btn", "_courses_label",   self._load_courses),
            (CalendarIcon(13, "#2563EB"),   "Exam Periods", "Load Periods",
             "_load_periods_btn", "_dates_label",     self._load_dates),
            (GraduationIcon(13, "#2563EB"), "Programmes",   "Load Programs",
             "_load_programs_btn", "_programs_label", self._load_programs),
        ]
        for icon, title, btn_text, btn_attr, lbl_attr, slot in specs:
            btn = QPushButton(btn_text)
            btn.setFixedWidth(106)
            btn.clicked.connect(slot)
            lbl = QLabel("No file loaded")
            lbl.setStyleSheet("font-size:10px; color:#94A3B8;")
            setattr(self, btn_attr, btn)
            setattr(self, lbl_attr, lbl)

            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(8)
            hl.addWidget(icon)
            t = QLabel(title)
            t.setStyleSheet("font-size:12px; font-weight:600; color:#374151;")
            hl.addWidget(t)
            hl.addStretch()
            hl.addWidget(btn)
            hl.addWidget(lbl)
            vl.addWidget(row)
        return c

    def _build_prog_card(self) -> QFrame:
        c = _card()
        vl = QVBoxLayout(c)
        vl.setContentsMargins(20, 18, 20, 18)
        vl.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.addWidget(_section_lbl("STUDY PROGRAMMES  (max 5)"))
        hdr.addStretch()
        self._prog_count_lbl = QLabel("0 / 5 selected")
        self._prog_count_lbl.setStyleSheet("font-size:11px; color:#64748B; background:transparent;")
        hdr.addWidget(self._prog_count_lbl)
        vl.addLayout(hdr)

        self._prog_placeholder = QLabel(
            "Load a courses or programs file to see programmes here."
        )
        self._prog_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._prog_placeholder.setStyleSheet(
            "font-size:11px; color:#94A3B8; padding:16px 8px; background:transparent;"
        )
        vl.addWidget(self._prog_placeholder)

        self._prog_list = QListWidget()
        self._prog_list.setFixedHeight(124)
        self._prog_list.setVisible(False)
        self._prog_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #E2E8F0; border-radius: 8px;
                background: #F8FAFC; outline: none; padding: 4px;
            }
            QListWidget::item {
                padding: 7px 10px; border-radius: 6px; margin: 1px 0;
                font-size: 12px; color: #374151; font-weight: 500;
            }
            QListWidget::item:hover    { background: #EFF6FF; }
            QListWidget::item:selected { background: transparent; }
            QListWidget::indicator {
                width: 16px; height: 16px; border-radius: 4px;
                border: 2px solid #CBD5E1; background: white; margin-right: 4px;
            }
            QListWidget::indicator:hover   { border-color: #2563EB; }
            QListWidget::indicator:checked { background: #2563EB; border-color: #2563EB; }
        """)
        self._prog_list.itemChanged.connect(self._on_programme_toggled)
        vl.addWidget(self._prog_list)
        return c

    def _build_footer(self) -> QWidget:
        """Fixed-height footer — Generate button is always anchored here."""
        footer = QWidget()
        footer.setObjectName("configFooter")
        footer.setFixedHeight(76)
        footer.setStyleSheet(
            "QWidget#configFooter { background:#FFFFFF; border-top:1px solid #E2E8F0; }"
        )
        vl = QVBoxLayout(footer)
        vl.setContentsMargins(32, 8, 32, 12)
        vl.setSpacing(4)

        self._progress_bar = QProgressBar()
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(3)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setStyleSheet(
            "QProgressBar { background:transparent; border:none; border-radius:2px; }"
            "QProgressBar::chunk { background:transparent; }"
        )
        vl.addWidget(self._progress_bar)

        row = QHBoxLayout()
        row.setSpacing(16)
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("font-size:11px; color:#64748B; background:transparent;")
        row.addWidget(self._status_label, 1)

        self._gen_btn = QPushButton("▶  Generate Schedule")
        self._gen_btn.setObjectName("generateBtn")
        self._gen_btn.setEnabled(False)
        self._gen_btn.setFixedHeight(44)
        self._gen_btn.setFixedWidth(220)
        self._gen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gen_btn.clicked.connect(self._on_generate)
        row.addWidget(self._gen_btn)
        vl.addLayout(row)
        return footer

    # ── File loading ──────────────────────────────────────────────────────────

    def _load_courses(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Courses File", "", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        mode = self._mode_group.checkedButton().text().lower()
        try:
            count = self._controller.load_courses(Path(path), mode=mode)
            self._courses_label.setText(f"{Path(path).name}  ({count})")
            self._courses_label.setStyleSheet("font-size:10px; color:#059669;")
            self._refresh_programme_list()
            self._set_status(f"✓  {count} courses loaded.")
            self._update_gen_btn()
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            logger.exception("Error loading courses")

    def _load_dates(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Exam Periods File", "", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        mode = self._mode_group.checkedButton().text().lower()
        try:
            count = self._controller.load_periods(Path(path), mode=mode)
            self._dates_label.setText(f"{Path(path).name}  ({count})")
            self._dates_label.setStyleSheet("font-size:10px; color:#059669;")
            self._set_status(f"✓  {count} exam period(s) loaded.")
            self._update_gen_btn()
            self.periods_changed.emit()
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            logger.exception("Error loading exam periods")

    def _load_programs(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Programs File", "", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        try:
            count = self._controller.load_programs(Path(path))
            self._programs_label.setText(f"{Path(path).name}  ({count})")
            self._programs_label.setStyleSheet("font-size:10px; color:#059669;")
            self._refresh_programme_list()
            self._set_status(f"✓  {count} programme(s) loaded.")
            self._update_gen_btn()
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            logger.exception("Error loading programs")

    # ── Programme list ────────────────────────────────────────────────────────

    def _refresh_programme_list(self) -> None:
        self._prog_list.blockSignals(True)
        self._prog_list.clear()
        for pid in self._controller.get_programme_ids():
            name = PROGRAM_NAMES_MAPPING.get(pid, "Unknown Program")
            item = QListWidgetItem(f"{pid}  —  {name}")
            item.setData(Qt.ItemDataRole.UserRole, pid)  # bare ID for _get_selected_ids
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._prog_list.addItem(item)
        self._prog_list.blockSignals(False)
        has = self._prog_list.count() > 0
        self._prog_placeholder.setVisible(not has)
        self._prog_list.setVisible(has)
        self._update_prog_label()
        self.courses_changed.emit(self._get_selected_ids())

    def _on_programme_toggled(self, item: QListWidgetItem) -> None:
        if self._count_checked() > _MAX_PROGS:
            self._prog_list.blockSignals(True)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._prog_list.blockSignals(False)
            QMessageBox.information(
                self, "Limit Reached",
                f"You can select at most {_MAX_PROGS} programmes.",
            )
            return
        self._update_programme_colours()
        self._update_prog_label()
        self._update_gen_btn()
        self.courses_changed.emit(self._get_selected_ids())

    def _update_programme_colours(self) -> None:
        slot = 0
        self._prog_list.blockSignals(True)
        for i in range(self._prog_list.count()):
            it = self._prog_list.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                it.setForeground(QColor(PROGRAMME_COLOURS[slot % len(PROGRAMME_COLOURS)]))
                slot += 1
            else:
                it.setForeground(QColor(100, 116, 139))
        self._prog_list.blockSignals(False)

    def _count_checked(self) -> int:
        return sum(
            1 for i in range(self._prog_list.count())
            if self._prog_list.item(i).checkState() == Qt.CheckState.Checked
        )

    def _get_selected_ids(self) -> list[str]:
        """Return programme IDs only (via UserRole) for selected items."""
        return [
            self._prog_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._prog_list.count())
            if self._prog_list.item(i).checkState() == Qt.CheckState.Checked
        ]

    def _update_prog_label(self) -> None:
        self._prog_count_lbl.setText(f"{self._count_checked()} / {_MAX_PROGS} selected")

    # ── Generation ────────────────────────────────────────────────────────────

    def _on_generate(self) -> None:
        selected = self._get_selected_ids()
        self._controller.set_selected_programs(selected)
        self._pending_selected = selected
        self._pending_color_map = {
            pid: PROGRAMME_COLOURS[i % len(PROGRAMME_COLOURS)]
            for i, pid in enumerate(selected)
        }

        # Switch to Results Screen BEFORE the heavy subprocess starts
        self.generation_started.emit((selected, self._pending_color_map))

        self._gen_btn.setEnabled(False)
        self._set_status("Generating schedules…")
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setStyleSheet(
            "QProgressBar { background:#E2E8F0; border:none; border-radius:2px; }"
            "QProgressBar::chunk { background:#2563EB; }"
        )

        if self._gen_process is not None and self._gen_process.is_alive():
            self._gen_process.kill()
        if self._poll_timer is not None:
            self._poll_timer.stop()
        if self._result_queue is not None:
            self._result_queue.cancel_join_thread()
            self._result_queue.close()

        self._gen_start_time = time.monotonic()
        self._dead_ticks = 0
        self._result_queue = multiprocessing.Queue()
        self._gen_process = multiprocessing.Process(
            target=_run_generation_process,
            args=(
                self._result_queue, self._controller.courses,
                self._controller.get_exam_periods(), selected,
            ),
            daemon=True,
        )
        self._gen_process.start()
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_result)
        self._poll_timer.start(150)

    def _poll_result(self) -> None:
        elapsed = int(time.monotonic() - self._gen_start_time)
        if elapsed > _MAX_GEN_SECS:
            self._poll_timer.stop()
            if self._gen_process:
                self._gen_process.kill()
            self._fail(f"Generation timed out after {_MAX_GEN_SECS}s.")
            return

        try:
            result = self._result_queue.get_nowait()
        except (_QueueEmpty, OSError):
            if not self._gen_process.is_alive():
                self._dead_ticks += 1
                if self._dead_ticks >= 5:
                    self._dead_ticks = 0
                    self._poll_timer.stop()
                    self._fail("Generation process exited unexpectedly.")
            else:
                self._dead_ticks = 0
            return

        self._dead_ticks = 0
        self._poll_timer.stop()
        self._reset_progress()

        if len(result) == 4 and result[0]:
            _, schedules_by_period, courses_by_id, truncated_periods = result
            self._controller.set_has_more_from_truncated(truncated_periods)
            self._gen_btn.setEnabled(True)
            self._set_status("✓  Schedule generated.", ok=True)
            self.schedule_generated.emit((
                self._pending_selected,
                schedules_by_period,
                courses_by_id,
                self._pending_color_map,
                truncated_periods,
            ))
        else:
            self._fail(result[1] if len(result) > 1 else "Unknown generation error.")

    def _fail(self, msg: str) -> None:
        self._reset_progress()
        if self._poll_timer:
            self._poll_timer.stop()
        logger.error("Generation failed: %s", msg)
        self._update_gen_btn()
        self.generation_failed.emit(msg)

    def _reset_progress(self) -> None:
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setStyleSheet(
            "QProgressBar { background:transparent; border:none; border-radius:2px; }"
            "QProgressBar::chunk { background:transparent; }"
        )

    def _set_status(self, text: str, ok: bool = False) -> None:
        color = "#059669" if ok else "#64748B"
        self._status_label.setStyleSheet(
            f"font-size:11px; color:{color}; background:transparent;"
        )
        self._status_label.setText(text)

    def _update_gen_btn(self) -> None:
        running = self._gen_process is not None and self._gen_process.is_alive()
        self._gen_btn.setEnabled(
            not running
            and self._controller.has_courses
            and self._controller.has_periods
            and self._count_checked() >= 1
        )
