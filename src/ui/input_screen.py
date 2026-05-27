"""
Widget: InputScreen
--------------------
Collects all user input before schedule generation (SRS §2.1 – §2.4).

    §2.1   File loading — courses and exam periods, with Replace / Append / Update mode.
    §2.2   Programme multi-select (QListWidget with checkboxes, max 5).
    §2.3   Course detail tree — shows courses grouped by programme.
    §2.4   Exam period date editor — one DateEditorWidget per loaded period.

Signals
-------
schedule_ready(dict, dict)
    Emitted after a successful generation.
    Arguments: schedules_by_period, courses_by_id
"""

import logging
from pathlib import Path
from typing import Dict, List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.controller import DesktopController
from src.domain.exam_period import ExamPeriod
from src.ui.date_editor import DateEditorWidget

logger = logging.getLogger(__name__)

_MAX_PROGRAMMES = 5


class InputScreen(QWidget):
    """Input view — file loading, programme selection, date editing, generate."""

    schedule_ready = pyqtSignal(dict, dict)  # (schedules_by_period, courses_by_id)

    def __init__(self, controller: DesktopController, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._date_editors: Dict[str, DateEditorWidget] = {}

        main = QVBoxLayout(self)
        main.setContentsMargins(12, 12, 12, 8)
        main.setSpacing(8)

        title = QLabel("Syncademic — Exam Schedule Generator")
        title.setStyleSheet("font-size: 17px; font-weight: bold;")
        main.addWidget(title)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_data_tab(), "Files & Programmes")
        self._periods_tab_widget = self._build_periods_tab_container()
        self._tabs.addTab(self._periods_tab_widget, "Exam Periods")
        main.addWidget(self._tabs, stretch=1)

        # Bottom bar
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(0, 4, 0, 0)
        self._status_label = QLabel("Load courses and exam-period files to begin.")
        self._status_label.setStyleSheet("color: #6b7280;")
        bl.addWidget(self._status_label)
        bl.addStretch()
        self._gen_btn = QPushButton("▶  Generate Schedule")
        self._gen_btn.setEnabled(False)
        self._gen_btn.setFixedHeight(36)
        self._gen_btn.setStyleSheet(
            "QPushButton { background:#3b82f6; color:white; padding:6px 18px;"
            "  border-radius:5px; font-size:13px; font-weight:bold; }"
            "QPushButton:disabled { background:#9ca3af; }"
            "QPushButton:hover:!disabled { background:#2563eb; }"
        )
        self._gen_btn.clicked.connect(self._on_generate)
        bl.addWidget(self._gen_btn)
        main.addWidget(bar)

    # ── File-loading tab ──────────────────────────────────────────────────────

    def _build_data_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)

        # § 2.1 — File loading
        file_box = QGroupBox("1. Load Data Files  (§2.1)")
        fl = QVBoxLayout(file_box)

        # Shared load mode
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Load mode:"))
        self._mode_group = QButtonGroup(self)
        for label in ("Replace", "Append", "Update"):
            rb = QRadioButton(label)
            self._mode_group.addButton(rb)
            mode_row.addWidget(rb)
        self._mode_group.buttons()[0].setChecked(True)
        mode_row.addStretch()
        fl.addLayout(mode_row)

        # Courses row
        cr = QHBoxLayout()
        self._courses_label = QLabel("No file loaded")
        self._courses_label.setStyleSheet("color:#9ca3af;")
        btn_c = QPushButton("Load Courses File…")
        btn_c.clicked.connect(self._load_courses)
        cr.addWidget(btn_c)
        cr.addWidget(self._courses_label, 1)
        fl.addLayout(cr)

        # Dates row
        dr = QHBoxLayout()
        self._dates_label = QLabel("No file loaded")
        self._dates_label.setStyleSheet("color:#9ca3af;")
        btn_d = QPushButton("Load Exam Periods File…")
        btn_d.clicked.connect(self._load_dates)
        dr.addWidget(btn_d)
        dr.addWidget(self._dates_label, 1)
        fl.addLayout(dr)

        layout.addWidget(file_box)

        # §2.2 — Programme multi-select
        prog_box = QGroupBox("2. Select Study Programmes  (§2.2) — max 5")
        pl = QVBoxLayout(prog_box)
        self._prog_list = QListWidget()
        self._prog_list.setMinimumHeight(110)
        self._prog_list.itemChanged.connect(self._on_programme_toggled)
        pl.addWidget(self._prog_list)
        self._prog_count_lbl = QLabel("0 / 5 selected")
        self._prog_count_lbl.setStyleSheet("color:#6b7280; font-size:11px;")
        pl.addWidget(self._prog_count_lbl)
        layout.addWidget(prog_box)

        # §2.3 — Course detail tree
        detail_box = QGroupBox("3. Course Details  (§2.3)")
        dl = QVBoxLayout(detail_box)
        self._course_tree = QTreeWidget()
        self._course_tree.setHeaderLabels(
            ["Course Name", "ID", "Year", "Semester", "Requirement", "Evaluation"]
        )
        self._course_tree.setMinimumHeight(140)
        dl.addWidget(self._course_tree)
        layout.addWidget(detail_box)

        layout.addStretch()
        return w

    # ── Exam-periods tab ──────────────────────────────────────────────────────

    def _build_periods_tab_container(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(4, 4, 4, 4)

        self._no_periods_hint = QLabel("Load an exam-periods file to edit dates here.")
        self._no_periods_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_periods_hint.setStyleSheet("color:#9ca3af; font-style:italic;")
        vl.addWidget(self._no_periods_hint)

        self._period_tabs = QTabWidget()
        self._period_tabs.setVisible(False)
        vl.addWidget(self._period_tabs)
        return w

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
            self._courses_label.setText(f"{Path(path).name}  ({count} courses)")
            self._courses_label.setStyleSheet("color:#16a34a;")
            self._refresh_programme_list()
            self._set_status(f"{count} courses in memory.")
            self._update_generate_btn()
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
            self._dates_label.setText(f"{Path(path).name}  ({count} periods)")
            self._dates_label.setStyleSheet("color:#16a34a;")
            self._refresh_period_editors()
            self._set_status(f"{count} exam period(s) in memory.")
            self._update_generate_btn()
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            logger.exception("Error loading exam periods")

    # ── Programme list ────────────────────────────────────────────────────────

    def _refresh_programme_list(self) -> None:
        self._prog_list.blockSignals(True)
        self._prog_list.clear()
        for pid in self._controller.get_programme_ids():
            item = QListWidgetItem(pid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._prog_list.addItem(item)
        self._prog_list.blockSignals(False)
        self._update_prog_count_label()

    def _on_programme_toggled(self, item: QListWidgetItem) -> None:
        if self._count_checked() > _MAX_PROGRAMMES:
            item.setCheckState(Qt.CheckState.Unchecked)
            QMessageBox.information(
                self, "Limit reached",
                f"You can select at most {_MAX_PROGRAMMES} programmes.",
            )
            return
        self._update_prog_count_label()
        self._refresh_course_tree()
        self._update_generate_btn()

    def _count_checked(self) -> int:
        return sum(
            1 for i in range(self._prog_list.count())
            if self._prog_list.item(i).checkState() == Qt.CheckState.Checked
        )

    def _get_selected_ids(self) -> List[str]:
        return [
            self._prog_list.item(i).text()
            for i in range(self._prog_list.count())
            if self._prog_list.item(i).checkState() == Qt.CheckState.Checked
        ]

    def _update_prog_count_label(self) -> None:
        n = self._count_checked()
        self._prog_count_lbl.setText(f"{n} / {_MAX_PROGRAMMES} selected")
        self._prog_count_lbl.setStyleSheet(
            f"color:{'#dc2626' if n == _MAX_PROGRAMMES else '#6b7280'}; font-size:11px;"
        )

    # ── Course detail tree ────────────────────────────────────────────────────

    def _refresh_course_tree(self) -> None:
        self._course_tree.clear()
        for prog_id in self._get_selected_ids():
            prog_item = QTreeWidgetItem([prog_id, "", "", "", "", ""])
            prog_item.setExpanded(True)
            self._course_tree.addTopLevelItem(prog_item)
            for course in self._controller.get_courses_by_programme(prog_id):
                for offering in course.offerings:
                    if offering.program_id != prog_id:
                        continue
                    child = QTreeWidgetItem([
                        course.name,
                        course.id,
                        str(offering.year),
                        offering.semester,
                        offering.requirement,
                        course.evaluation_type,
                    ])
                    prog_item.addChild(child)
        self._course_tree.resizeColumnToContents(0)

    # ── Exam period date editors ───────────────────────────────────────────────

    def _refresh_period_editors(self) -> None:
        self._period_tabs.clear()
        self._date_editors.clear()

        periods = self._controller.get_exam_periods()
        if not periods:
            self._no_periods_hint.setVisible(True)
            self._period_tabs.setVisible(False)
            return

        self._no_periods_hint.setVisible(False)
        self._period_tabs.setVisible(True)

        for period in periods:
            key = period.get_key()
            editor = DateEditorWidget(period)
            editor.period_changed.connect(self._sync_periods_to_controller)
            self._date_editors[key] = editor

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(editor)
            self._period_tabs.addTab(scroll, key)

    def _sync_periods_to_controller(self) -> None:
        updated: List[ExamPeriod] = [
            e.get_exam_period() for e in self._date_editors.values()
        ]
        self._controller.update_exam_periods(updated)

    # ── Generation ────────────────────────────────────────────────────────────

    def _on_generate(self) -> None:
        selected = self._get_selected_ids()
        self._controller.set_selected_programs(selected)
        self._sync_periods_to_controller()

        self._gen_btn.setEnabled(False)
        self._gen_btn.setText("⏳  Generating…")
        try:
            schedules_by_period, courses_by_id = self._controller.generate()
            total = sum(len(v) for v in schedules_by_period.values())
            self._set_status(
                f"✓ {total} schedule(s) generated across "
                f"{len(schedules_by_period)} period(s)."
            )
            self.schedule_ready.emit(schedules_by_period, courses_by_id)
        except Exception as exc:
            QMessageBox.critical(self, "Generation Error", str(exc))
            logger.exception("Generation failed")
        finally:
            self._gen_btn.setEnabled(True)
            self._gen_btn.setText("▶  Generate Schedule")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, msg: str) -> None:
        self._status_label.setText(msg)

    def _update_generate_btn(self) -> None:
        self._gen_btn.setEnabled(
            self._controller.has_courses
            and self._controller.has_periods
            and self._count_checked() >= 1
        )
