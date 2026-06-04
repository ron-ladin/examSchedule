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
from PyQt6.QtGui import QColor, QPixmap
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
from src.ui.tokens import PROGRAMME_COLOURS, PROGRAM_NAMES_MAPPING

logger = logging.getLogger(__name__)

_LOGO_PNG = str(Path(__file__).parent / "assets" / "logo.png")

_MAX_PROGS = 5

# Full generation can take longer than the old 1000-result batch generation.
_MAX_GEN_SECS = 180


# ── module-level helpers ──────────────────────────────────────────────────────

def _section_lbl(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "font-size:10px; font-weight:700; color:#72778c;"
        " letter-spacing:0.6px; background:transparent;"
    )
    return lbl


def _card() -> QFrame:
    f = QFrame()
    f.setStyleSheet(
        "QFrame {"
        " background: rgba(255, 255, 255, 0.75);"
        " border: 1px solid rgba(255, 255, 255, 0.9);"
        " border-radius: 12px;"
        "}"
    )
    eff = QGraphicsDropShadowEffect()
    eff.setBlurRadius(18)
    eff.setColor(QColor(0, 67, 148, 13))
    eff.setOffset(0, 4)
    f.setGraphicsEffect(eff)
    return f


# ── ConfigScreen ──────────────────────────────────────────────────────────────

class ConfigScreen(QWidget):
    """Full-screen configuration (Screen 0)."""

    generation_started = pyqtSignal(object)  # (selected_ids, prog_color_map) — immediate
    schedule_generated = pyqtSignal(object)  # full result tuple — async
    generation_failed = pyqtSignal(str)
    courses_changed = pyqtSignal(list)
    periods_changed = pyqtSignal()

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
        root.addWidget(self._build_scroll_area(), 1)
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setObjectName("appHeader")
        hdr.setFixedHeight(80)

        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)
        hl.setSpacing(12)

        logo = QLabel()
        logo.setStyleSheet("background: transparent; border: none;")
        logo.setFixedSize(32, 32)

        pix = QPixmap(_LOGO_PNG)
        if not pix.isNull():
            logo.setPixmap(
                pix.scaled(
                    32,
                    32,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        hl.addWidget(logo)

        brand = QLabel("Syncacademic")
        brand.setStyleSheet(
            "font-size: 22px; font-weight: 800; color: #005ac2;"
            " letter-spacing: -0.5px; background: transparent;"
        )

        tagline = QLabel("Academic Command Center")
        tagline.setStyleSheet(
            "font-size: 12px; color: #42474e; font-weight: 500; background: transparent;"
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
        content.setMaximumWidth(900)
        content.setStyleSheet("background:transparent;")

        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(20)

        steps_row = QWidget()
        steps_row.setStyleSheet("background: transparent;")

        sl = QHBoxLayout(steps_row)
        sl.setContentsMargins(0, 4, 0, 4)
        sl.setSpacing(0)
        sl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for i, (icon, text, active) in enumerate([
            ("①", "Load files", True),
            ("②", "Select programmes", False),
            ("③", "Generate", False),
        ]):
            if i > 0:
                div = QLabel("  ——  ")
                div.setStyleSheet(
                    "color: rgba(194, 198, 214, 0.9);"
                    " background: transparent; font-size: 11px;"
                )
                sl.addWidget(div)

            step = QLabel(f"{icon}  {text}")
            step.setStyleSheet(
                f"font-size: 13px; font-weight: {'700' if active else '500'};"
                f" color: {'#004394' if active else '#42474e'};"
                " background: transparent;"
            )
            sl.addWidget(step)

        cl.addWidget(steps_row)

        top = QHBoxLayout()
        top.setSpacing(16)
        top.addWidget(self._build_mode_card(), 1)
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

        vl = QVBoxLayout(c)
        vl.setContentsMargins(20, 18, 20, 18)
        vl.setSpacing(10)
        vl.addWidget(_section_lbl("LOAD MODE"))

        self._mode_group = QButtonGroup(self)
        self._mode_frames: list[QFrame] = []

        radio_style = (
            "QRadioButton { font-size:14px; font-weight:600; color:#171c20;"
            " spacing:10px; background:transparent; }"
            "QRadioButton::indicator { width:18px; height:18px; border-radius:9px;"
            " border:2px solid rgba(194,198,214,0.9); background:white; }"
            "QRadioButton::indicator:hover { border-color:#004394; }"
            "QRadioButton::indicator:checked { border:5px solid #004394;"
            " background:white; border-radius:9px; }"
        )

        for label, hint_text in (
            ("Replace", "Clear all existing data"),
            ("Update", "Merge with existing data"),
        ):
            option_frame = QFrame()
            option_frame.setCursor(Qt.CursorShape.PointingHandCursor)

            fl = QVBoxLayout(option_frame)
            fl.setContentsMargins(0, 0, 0, 0)
            fl.setSpacing(0)

            rb_row = QWidget()
            rb_row.setStyleSheet("background:transparent;")

            rl = QHBoxLayout(rb_row)
            rl.setContentsMargins(14, 12, 14, 4)
            rl.setSpacing(10)

            rb = QRadioButton(label)
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            rb.setStyleSheet(radio_style)

            self._mode_group.addButton(rb)

            rl.addWidget(rb)
            rl.addStretch()

            hint = QLabel(hint_text)
            hint.setContentsMargins(42, 0, 14, 10)
            hint.setStyleSheet(
                "font-size:12px; color:#42474e; background:transparent;"
            )

            fl.addWidget(rb_row)
            fl.addWidget(hint)

            rb.toggled.connect(lambda _: self._update_mode_card_styles())
            self._mode_frames.append(option_frame)
            vl.addWidget(option_frame)

        self._mode_group.buttons()[0].setChecked(True)
        self._update_mode_card_styles()

        vl.addStretch()
        return c

    def _update_mode_card_styles(self) -> None:
        checked = self._mode_group.checkedButton()

        for btn, frame in zip(self._mode_group.buttons(), self._mode_frames):
            if btn is checked:
                frame.setStyleSheet(
                    "QFrame { background:rgba(0,67,148,0.05);"
                    " border:1.5px solid #004394; border-radius:10px; }"
                )
            else:
                frame.setStyleSheet(
                    "QFrame { background:rgba(255,255,255,0.6);"
                    " border:1px solid rgba(194,198,214,0.5); border-radius:10px; }"
                )

    def _build_files_card(self) -> QFrame:
        c = _card()

        vl = QVBoxLayout(c)
        vl.setContentsMargins(20, 18, 20, 18)
        vl.setSpacing(10)
        vl.addWidget(_section_lbl("FILES"))

        specs = [
            (
                BookIcon(14, "#004394"),
                "Courses",
                "Load Courses",
                "_load_courses_btn",
                "_courses_label",
                self._load_courses,
            ),
            (
                CalendarIcon(14, "#004394"),
                "Exam Periods",
                "Load Periods",
                "_load_periods_btn",
                "_dates_label",
                self._load_dates,
            ),
            (
                GraduationIcon(14, "#004394"),
                "Programmes",
                "Load Programs",
                "_load_programs_btn",
                "_programs_label",
                self._load_programs,
            ),
        ]

        file_btn_style = (
            "QPushButton { background:rgba(222,227,235,0.9);"
            " border:1px solid rgba(194,198,214,0.5); border-radius:8px;"
            " padding:5px 12px; font-size:12px; font-weight:600; color:#171c20; }"
            "QPushButton:hover { background:rgba(0,67,148,0.08);"
            " border-color:#004394; color:#004394; }"
        )

        for icon, title, btn_text, btn_attr, lbl_attr, slot in specs:
            btn = QPushButton(btn_text)
            btn.setFixedWidth(110)
            btn.setStyleSheet(file_btn_style)
            btn.clicked.connect(slot)

            lbl = QLabel("No file loaded")
            lbl.setStyleSheet(
                "font-size:11px; color:#72778c; background:transparent;"
            )

            setattr(self, btn_attr, btn)
            setattr(self, lbl_attr, lbl)

            row = QFrame()
            row.setStyleSheet(
                "QFrame { background:transparent; border-radius:8px; border:none; }"
                "QFrame:hover { background:rgba(0,67,148,0.04); }"
            )

            hl = QHBoxLayout(row)
            hl.setContentsMargins(10, 8, 10, 8)
            hl.setSpacing(10)

            hl.addWidget(icon)

            title_lbl = QLabel(title)
            title_lbl.setStyleSheet(
                "font-size:14px; font-weight:600; color:#171c20; background:transparent;"
            )

            hl.addWidget(title_lbl)
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
        self._prog_count_lbl.setStyleSheet(
            "font-size:11px; color:#64748B; background:transparent;"
        )

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
        self._prog_list.setFixedHeight(160)
        self._prog_list.setVisible(False)
        self._prog_list.setStyleSheet("""
            QListWidget {
                border: 1px solid rgba(194,198,214,0.4); border-radius: 10px;
                background: rgba(255,255,255,0.75); outline: none; padding: 4px;
            }
            QListWidget::item {
                padding: 9px 12px; border-radius: 8px; margin: 2px 2px;
                font-size: 13px; color: #171c20; font-weight: 500;
            }
            QListWidget::item:hover    { background: rgba(0,67,148,0.05); }
            QListWidget::item:selected { background: transparent; }
            QListWidget::indicator {
                width: 18px; height: 18px; border-radius: 5px;
                border: 2px solid rgba(194,198,214,0.9); background: white;
                margin-right: 6px;
            }
            QListWidget::indicator:hover   { border-color: #004394; }
            QListWidget::indicator:checked { background: #004394; border-color: #004394; }
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
            "QWidget#configFooter {"
            " background: rgba(255, 255, 255, 0.85);"
            " border-top: 1px solid rgba(194, 198, 214, 0.6);"
            "}"
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
        self._status_label.setStyleSheet(
            "font-size:11px; color:#64748B; background:transparent;"
        )
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
            self,
            "Select Courses File",
            "",
            "Text files (*.txt);;All files (*)",
        )

        if not path:
            return

        mode = self._mode_group.checkedButton().text().lower()

        try:
            count = self._controller.load_courses(Path(path), mode=mode)
            self._courses_label.setText(f"{Path(path).name}  ({count})")
            self._courses_label.setStyleSheet(
                "font-size:11px; color:#059669; background:rgba(16,185,129,0.1);"
                " border-radius:4px; padding:2px 7px;"
            )

            self._refresh_programme_list()
            self._set_status(f"✓  {count} courses loaded.")
            self._update_gen_btn()

        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            logger.exception("Error loading courses")

    def _load_dates(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Exam Periods File",
            "",
            "Text files (*.txt);;All files (*)",
        )

        if not path:
            return

        mode = self._mode_group.checkedButton().text().lower()

        try:
            count = self._controller.load_periods(Path(path), mode=mode)
            self._dates_label.setText(f"{Path(path).name}  ({count})")
            self._dates_label.setStyleSheet(
                "font-size:11px; color:#059669; background:rgba(16,185,129,0.1);"
                " border-radius:4px; padding:2px 7px;"
            )

            self._set_status(f"✓  {count} exam period(s) loaded.")
            self._update_gen_btn()
            self.periods_changed.emit()

        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            logger.exception("Error loading exam periods")

    def _load_programs(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Programs File",
            "",
            "Text files (*.txt);;All files (*)",
        )

        if not path:
            return

        try:
            count = self._controller.load_programs(Path(path))
            self._programs_label.setText(f"{Path(path).name}  ({count})")
            self._programs_label.setStyleSheet(
                "font-size:11px; color:#059669; background:rgba(16,185,129,0.1);"
                " border-radius:4px; padding:2px 7px;"
            )

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
            item.setData(Qt.ItemDataRole.UserRole, pid)
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
                self,
                "Limit Reached",
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
            item = self._prog_list.item(i)

            if item.checkState() == Qt.CheckState.Checked:
                item.setForeground(
                    QColor(PROGRAMME_COLOURS[slot % len(PROGRAMME_COLOURS)])
                )
                slot += 1
            else:
                item.setForeground(QColor(100, 116, 139))

        self._prog_list.blockSignals(False)

    def _count_checked(self) -> int:
        return sum(
            1
            for i in range(self._prog_list.count())
            if self._prog_list.item(i).checkState() == Qt.CheckState.Checked
        )

    def _get_selected_ids(self) -> list[str]:
        """Return programme IDs only via UserRole for selected items."""
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
                self._result_queue,
                self._controller.courses,
                self._controller.get_exam_periods(),
                selected,
            ),
            kwargs={
                "cap": None,
            },
            daemon=True,
        )

        self._gen_process.start()

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_result)
        self._poll_timer.start(150)

    def _poll_result(self) -> None:
        elapsed = int(time.monotonic() - self._gen_start_time)

        if elapsed > _MAX_GEN_SECS:
            if self._poll_timer:
                self._poll_timer.stop()

            if self._gen_process:
                self._gen_process.kill()

            self._fail(f"Generation timed out after {_MAX_GEN_SECS}s.")
            return

        try:
            result = self._result_queue.get_nowait()
        except (_QueueEmpty, OSError):
            if self._gen_process is not None and not self._gen_process.is_alive():
                self._dead_ticks += 1

                if self._dead_ticks >= 5:
                    self._dead_ticks = 0

                    if self._poll_timer:
                        self._poll_timer.stop()

                    self._fail("Generation process exited unexpectedly.")
            else:
                self._dead_ticks = 0

            return

        self._dead_ticks = 0

        if self._poll_timer:
            self._poll_timer.stop()

        self._reset_progress()

        if len(result) == 4 and result[0]:
            _, schedules_by_period, courses_by_id, truncated_periods = result

            self._controller.clear_results_stale()
            self._controller.set_has_more_from_truncated(truncated_periods)

            self._gen_btn.setEnabled(True)
            self._set_status("✓  Schedule generated.", ok=True)

            self.schedule_generated.emit(
                (
                    self._pending_selected,
                    schedules_by_period,
                    courses_by_id,
                    self._pending_color_map,
                    truncated_periods,
                )
            )
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
