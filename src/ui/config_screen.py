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
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from src.domain.sorting import SortingConfig
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.adapters.readers.schedule_file_reader import EmptyScheduleImportError
from src.controller import DesktopController, MissingStudentCountError
from src.domain.settings import Settings
from src.ui.settings_screen import SettingsScreen
from src.ui.generation_poller import GenerationPoller
from src.ui.periods_editor_dialog import ExamPeriodsEditorDialog
from src.ui.results_panel import _display_period_key
from src.ui.tokens import PROGRAMME_COLOURS, PROGRAM_NAMES_MAPPING
from src.ui.widgets.config_input_cards import FilesCard, LoadModeCard
from src.ui.widgets.feature4_card import Feature4Card
from src.ui.widgets.programme_row import ProgrammeRow

logger = logging.getLogger(__name__)

_LOGO_PNG = str(Path(__file__).parent / "assets" / "logo.png")

_MAX_PROGS = 5


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


class ConfigScreen(QWidget):
    """Full-screen configuration (Screen 0)."""

    generation_started = pyqtSignal(object)
    schedule_generated = pyqtSignal(object)
    generation_failed = pyqtSignal(str)
    courses_changed = pyqtSignal(list)
    periods_changed = pyqtSignal()

    def __init__(self, controller: DesktopController, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._settings_dialog: SettingsScreen | None = None
        self._allow_unassigned_generation = False

        self._last_courses_by_id: dict = {}

        self._poller = GenerationPoller(controller, parent=self)
        self._poller.generation_succeeded.connect(self._on_generation_succeeded)
        self._poller.generation_failed.connect(self._fail)
        self._poller.progress_reset.connect(self._reset_progress)

        self._setup_ui()

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

        settings_btn = QPushButton("⚙  Settings")
        settings_btn.setObjectName("settingsBtn")
        settings_btn.setFixedHeight(32)
        settings_btn.setStyleSheet(
            "QPushButton#settingsBtn {"
            " background: rgba(0,90,194,0.08); border: 1px solid rgba(0,90,194,0.25);"
            " border-radius: 6px; padding: 0 14px;"
            " font-size: 13px; font-weight: 600; color: #005ac2;"
            "}"
            "QPushButton#settingsBtn:hover { background: rgba(0,90,194,0.15); }"
            "QPushButton#settingsBtn:pressed { background: rgba(0,90,194,0.25); }"
        )
        settings_btn.clicked.connect(self._on_open_settings)
        hl.addWidget(settings_btn)

        return hdr

    def _build_scroll_area(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")

        outer = QWidget()
        outer.setObjectName("configScrollOuter")
        outer.setStyleSheet("QWidget#configScrollOuter { background:transparent; }")

        ol = QHBoxLayout(outer)
        ol.setContentsMargins(32, 32, 32, 32)

        content = QWidget()
        content.setMaximumWidth(900)
        content.setObjectName("configScrollContent")
        content.setStyleSheet("QWidget#configScrollContent { background:transparent; }")

        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(20)

        steps_row = QWidget()
        steps_row.setObjectName("configStepsRow")
        steps_row.setStyleSheet("QWidget#configStepsRow { background:transparent; }")

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

        self._mode_card = LoadModeCard()
        self._files_card = FilesCard(self._load_courses, self._load_dates)

        top = QHBoxLayout()
        top.setSpacing(16)
        top.addWidget(self._mode_card, 1)
        top.addWidget(self._files_card, 1)

        cl.addLayout(top)
        cl.addWidget(self._build_prog_card())
        cl.addWidget(self._build_periods_card())
        self._feature4_card = Feature4Card(self._controller)
        self._feature4_card.gen_btn_update_needed.connect(self._update_gen_btn)
        cl.addWidget(self._feature4_card)

        self._gen_btn = QPushButton("▶  Generate Schedule")
        self._gen_btn.setObjectName("generateBtn")
        self._gen_btn.setEnabled(False)
        self._gen_btn.setFixedHeight(44)
        self._gen_btn.setFixedWidth(220)
        self._gen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gen_btn.clicked.connect(self._on_generate)

        self._import_btn = QPushButton("📂  Load Schedule")
        self._import_btn.setFixedHeight(44)
        self._import_btn.setFixedWidth(160)
        self._import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._import_btn.setToolTip("Load a previously generated schedules.txt file")
        self._import_btn.clicked.connect(self._import_schedule)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._import_btn)
        btn_row.addWidget(self._gen_btn)
        cl.addLayout(btn_row)
        cl.addStretch(1)

        ol.addStretch(1)
        ol.addWidget(content, 0)
        ol.addStretch(1)

        scroll.setWidget(outer)
        return scroll

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
            "Load a courses file to see programmes here."
        )
        self._prog_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._prog_placeholder.setStyleSheet(
            "font-size:11px; color:#94A3B8; padding:16px 8px; background:transparent;"
        )
        vl.addWidget(self._prog_placeholder)

        self._prog_rows: dict[str, ProgrammeRow] = {}

        self._prog_rows_container = QWidget()
        self._prog_rows_container.setStyleSheet("background: transparent;")
        self._prog_rows_layout = QVBoxLayout(self._prog_rows_container)
        self._prog_rows_layout.setContentsMargins(4, 4, 4, 4)
        self._prog_rows_layout.setSpacing(2)
        self._prog_rows_layout.addStretch()

        prog_scroll = QScrollArea()
        prog_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        prog_scroll.setWidgetResizable(True)
        prog_scroll.setFixedHeight(160)
        prog_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        prog_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        prog_scroll.setWidget(self._prog_rows_container)
        prog_scroll.setStyleSheet(
            "QScrollArea { border:1px solid rgba(194,198,214,0.4); border-radius:10px;"
            " background:rgba(255,255,255,0.75); }"
        )
        prog_scroll.setVisible(False)
        self._prog_scroll = prog_scroll

        vl.addWidget(self._prog_scroll)

        return c

    def _build_periods_card(self) -> QFrame:
        c = _card()

        vl = QVBoxLayout(c)
        vl.setContentsMargins(20, 18, 20, 18)
        vl.setSpacing(10)
        vl.addWidget(_section_lbl("EXAM PERIODS"))

        self._periods_summary_lbl = QLabel("No periods loaded")
        self._periods_summary_lbl.setStyleSheet(
            "font-size:12px; color:#42474e; background:transparent;"
        )
        vl.addWidget(self._periods_summary_lbl)

        self._edit_periods_btn = QPushButton("Edit Exam Periods ▶")
        self._edit_periods_btn.setEnabled(False)
        self._edit_periods_btn.setFixedHeight(32)
        self._edit_periods_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_periods_btn.setStyleSheet(
            "QPushButton { color:#004394; border:1px solid #004394;"
            " border-radius:6px; padding:0 14px; font-size:12px; font-weight:600;"
            " background:rgba(0,67,148,0.06); }"
            "QPushButton:hover:enabled { background:rgba(0,67,148,0.12); }"
            "QPushButton:disabled { color:#aaa; border-color:#ccc; }"
        )
        self._edit_periods_btn.clicked.connect(self._on_edit_periods)

        vl.addWidget(self._edit_periods_btn)

        return c

    def _refresh_periods_card(self) -> None:
        periods = self._controller.get_exam_periods()

        if not periods:
            self._periods_summary_lbl.setText("No periods loaded")
            self._edit_periods_btn.setEnabled(False)
            return

        # Reflect the periods actually loaded, using the same display format as
        # the results calendar tabs (avoids drift from a hardcoded list).
        display_names = [
            _display_period_key(period.get_key()) for period in periods
        ]

        self._periods_summary_lbl.setText(
            "Editable exam periods:\n" + ", ".join(display_names)
        )
        self._edit_periods_btn.setEnabled(True)

    def _on_edit_periods(self) -> None:
        dlg = ExamPeriodsEditorDialog(self._controller, parent=self)
        dlg.exec()
        self._refresh_periods_card()
        self.periods_changed.emit()

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("configFooter")
        footer.setFixedHeight(44)
        footer.setStyleSheet(
            "QWidget#configFooter {"
            " background: rgba(255, 255, 255, 0.85);"
            " border-top: 1px solid rgba(194, 198, 214, 0.6);"
            "}"
        )

        vl = QVBoxLayout(footer)
        vl.setContentsMargins(32, 6, 32, 6)
        vl.setSpacing(2)

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

        self._status_label = QLabel("")
        self._status_label.setWordWrap(False)
        self._status_label.setStyleSheet(
            "font-size:11px; color:#64748B; background:transparent;"
        )
        vl.addWidget(self._status_label)

        return footer

    def _load_courses(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Courses File",
            "",
            "Text files (*.txt);;All files (*)",
        )

        if not path:
            return

        mode = self._mode_card.selected_mode()

        try:
            # Spec 4.3: pre-merge validation lives in the controller. It rejects
            # the load with MissingStudentCountError BEFORE mutating any state
            # when Feature 4 is on and an Exam offering lacks a StudentCount.
            count = self._controller.load_courses(Path(path), mode=mode)

            self._files_card.courses_label.setText(f"{Path(path).name}  ({count})")
            self._files_card.courses_label.setStyleSheet(
                "font-size:11px; color:#059669; background:rgba(16,185,129,0.1);"
                " border-radius:4px; padding:2px 7px;"
            )

            self._refresh_programme_list()
            self._set_status(f"✓  {count} courses loaded.")
            self._update_gen_btn()

        except MissingStudentCountError:
            # Controller left self._courses untouched — just surface the error.
            self._files_card.courses_label.setText(f"{Path(path).name} - Missing StudentCount")
            self._files_card.courses_label.setStyleSheet(
                "font-size:11px; color:#B91C1C; background:rgba(239,68,68,0.1);"
                " border-radius:4px; padding:2px 7px;"
            )
            QMessageBox.critical(
                self,
                "Missing Student Counts",
                "Feature 4 is enabled, but this courses file has Exam courses "
                "without a StudentCount (5th column).\n\n"
                "The file load was aborted (spec 4.3). Add StudentCount to "
                "every exam course, or disable Feature 4, then try again.",
            )
            self._set_status("✗  Courses load aborted — missing StudentCount.")
            self._update_gen_btn()

        except Exception:
            QMessageBox.critical(
                self,
                "Load Error",
                "Could not load the courses file. Please check the file format and try again.",
            )
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

        mode = self._mode_card.selected_mode()

        try:
            count = self._controller.load_periods(Path(path), mode=mode)
            self._files_card.dates_label.setText(f"{Path(path).name}  ({count})")
            self._files_card.dates_label.setStyleSheet(
                "font-size:11px; color:#059669; background:rgba(16,185,129,0.1);"
                " border-radius:4px; padding:2px 7px;"
            )

            self._set_status(f"✓  {count} exam period(s) loaded.")
            self._update_gen_btn()
            self._refresh_periods_card()
            self.periods_changed.emit()

        except Exception:
            QMessageBox.critical(
                self,
                "Load Error",
                "Could not load the exam periods file. Please check the file format and try again.",
            )
            logger.exception("Error loading exam periods")

    def _refresh_programme_list(self) -> None:
        # Clear old rows
        while self._prog_rows_layout.count() > 1:  # keep trailing stretch
            item = self._prog_rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._prog_rows.clear()

        for pid in self._controller.get_programme_ids():
            name = PROGRAM_NAMES_MAPPING.get(pid, "Unknown Program")
            row = ProgrammeRow(pid, name, parent=self._prog_rows_container)
            row.toggled.connect(self._on_programme_toggled)
            row.view_courses_clicked.connect(self._on_view_courses_for)
            self._prog_rows[pid] = row
            self._prog_rows_layout.insertWidget(self._prog_rows_layout.count() - 1, row)

        has = bool(self._prog_rows)
        self._prog_placeholder.setVisible(not has)
        self._prog_scroll.setVisible(has)

        self._update_prog_label()
        self.courses_changed.emit(self._get_selected_ids())

    def _on_programme_toggled(self, pid: str, checked: bool) -> None:
        if checked and self._count_checked() > _MAX_PROGS:
            self._prog_rows[pid].set_checked(False)
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

    def _on_view_courses_for(self, pid: str) -> None:
        from src.ui.programme_courses_dialog import ProgrammeCoursesDialog

        dlg = ProgrammeCoursesDialog(pid, self._controller, parent=self)
        dlg.exec()

    def _update_programme_colours(self) -> None:
        slot = 0
        for pid, row in self._prog_rows.items():
            if row.is_checked():
                row.set_label_color(PROGRAMME_COLOURS[slot % len(PROGRAMME_COLOURS)])
                slot += 1
            else:
                row.set_label_color("#64748B")

    def _count_checked(self) -> int:
        return sum(1 for row in self._prog_rows.values() if row.is_checked())

    def _get_selected_ids(self) -> list[str]:
        return [pid for pid, row in self._prog_rows.items() if row.is_checked()]

    def _update_prog_label(self) -> None:
        self._prog_count_lbl.setText(f"{self._count_checked()} / {_MAX_PROGS} selected")

    def _on_open_settings(self) -> None:
        """Open (or raise) the modeless SettingsScreen dialog."""
        is_running = self._poller.is_running()
        if self._settings_dialog is None:
            self._settings_dialog = SettingsScreen(
                self._controller.settings,
                parent=self,
            )
            self._settings_dialog.settings_changed.connect(self._on_settings_changed)
            self._settings_dialog.sort_order_changed.connect(self._on_sort_order_changed)

        self._settings_dialog.set_generation_state(is_running)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _on_sort_order_changed(self, config: SortingConfig) -> None:
        """Re-sort cached results after the settings dialog is saved."""
        try:
            resorted = self._controller.resort(config)
        except ValueError:
            self._controller.apply_sort(config)
            return
        read_only_import = self._controller.read_only_import
        self.schedule_generated.emit(
            ([], resorted, self._last_courses_by_id, {}, set(), read_only_import)
        )

    def _on_settings_changed(self, new_settings: Settings) -> None:
        """Persist the full settings (thresholds + sort) from the dialog OK path."""
        self._controller.apply_settings(new_settings)
        logger.info("Settings updated via SettingsScreen.")

    def _notify_settings_state(self, is_running: bool) -> None:
        """Propagate generation state to the settings dialog if it is open."""
        if self._settings_dialog is not None and self._settings_dialog.isVisible():
            self._settings_dialog.set_generation_state(is_running)

    def _on_generate(self) -> None:
        selected = self._get_selected_ids()
        self._controller.set_selected_programs(selected)

        if not self._confirm_capacity_warning():
            return

        self._controller.set_allow_unassigned_classrooms(
            self._allow_unassigned_generation
        )
        color_map = {
            pid: PROGRAMME_COLOURS[i % len(PROGRAMME_COLOURS)]
            for i, pid in enumerate(selected)
        }

        self.generation_started.emit((selected, color_map))

        self._gen_btn.setEnabled(False)
        self._notify_settings_state(True)
        self._set_status("Generating schedules…")
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setStyleSheet(
            "QProgressBar { background:#E2E8F0; border:none; border-radius:2px; }"
            "QProgressBar::chunk { background:#2563EB; }"
        )

        self._poller.start(selected, color_map, self._allow_unassigned_generation)

    def _confirm_capacity_warning(self) -> bool:
        """Show the optional Feature 4 capacity warning before generation."""
        shortfall = self._controller.feature4_capacity_shortfall()
        if shortfall is None:
            self._allow_unassigned_generation = False
            return True

        total_capacity, largest_exam_students = shortfall
        response = QMessageBox.warning(
            self,
            "Insufficient Classroom Capacity",
            "The total classroom capacity is lower than the number of students "
            "in at least one exam.\n\n"
            f"Total classroom capacity: {total_capacity:,}\n"
            f"Largest exam: {largest_exam_students:,} students\n"
            f"Shortfall: {largest_exam_students - total_capacity:,}\n\n"
            "Generation may reject schedules that cannot be assigned to rooms. "
            "Do you want to proceed anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        self._allow_unassigned_generation = response == QMessageBox.StandardButton.Yes
        return self._allow_unassigned_generation


    def _import_schedule(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Schedule File",
            "",
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return

        if not self._import_size_ok(path):
            return

        try:
            imported = self._controller.import_schedule(Path(path))
        except EmptyScheduleImportError:
            # Atomic import: controller state is untouched when the file is empty.
            QMessageBox.warning(
                self,
                "Empty File",
                "No schedules found in the selected file.",
            )
            logger.info("Imported schedule file contained no schedules")
            return
        except FileNotFoundError:
            QMessageBox.critical(self, "Load Error", "The file no longer exists.")
            logger.exception("Schedule file missing during import")
            return
        except PermissionError:
            QMessageBox.critical(self, "Load Error", "Permission denied to read the file.")
            logger.exception("Permission denied reading schedule file")
            return
        except UnicodeDecodeError:
            QMessageBox.critical(self, "Load Error", "The file encoding is not valid UTF-8.")
            logger.exception("Encoding error reading schedule file")
            return
        except ValueError as e:
            QMessageBox.critical(self, "Load Error", f"Data format error: {e}")
            logger.exception("ValueError reading schedule file")
            return
        except OSError:
            QMessageBox.critical(self, "Load Error", "Could not read the schedule file.")
            logger.exception("OSError reading schedule file")
            return
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"An unexpected error occurred: {e}")
            logger.exception("Unexpected error reading schedule file")
            return

        # import_schedule() guarantees a non-empty result (it raises
        # EmptyScheduleImportError otherwise), so we can render directly.
        schedules_by_period = imported.schedules_by_period

        self._last_courses_by_id = imported.courses_by_id

        result_tuple = ([], schedules_by_period, imported.courses_by_id, {}, set(), True)

        self.schedule_generated.emit(result_tuple)
        self._set_status(f"✓  Schedule loaded from {Path(path).name}.", ok=True)

    def _import_size_ok(self, path: str) -> bool:
        """Reject oversized files before parsing, failing safe if stat() errors."""
        max_import_bytes = 50 * 1024 * 1024
        try:
            size = Path(path).stat().st_size
        except FileNotFoundError:
            QMessageBox.critical(self, "Load Error", "The file no longer exists.")
            logger.exception("Schedule file missing before import")
            return False
        except PermissionError:
            QMessageBox.critical(self, "Load Error", "Permission denied to read the file.")
            logger.exception("Permission denied stat-ing schedule file")
            return False
        except OSError:
            QMessageBox.critical(self, "Load Error", "Could not access the schedule file.")
            logger.exception("OSError stat-ing schedule file")
            return False

        if size > max_import_bytes:
            QMessageBox.warning(
                self,
                "File Too Large",
                "The selected file exceeds the 50 MB import limit. "
                "Please select a smaller schedule file.",
            )
            return False

        return True

    def _on_generation_succeeded(self, result_tuple: object) -> None:
        self._notify_settings_state(False)
        self._gen_btn.setEnabled(True)
        self._set_status("✓  Schedule generated.", ok=True)
        if isinstance(result_tuple, tuple) and len(result_tuple) >= 3:
            self._last_courses_by_id = result_tuple[2]
        self.schedule_generated.emit(result_tuple)

    def _fail(self, msg: str) -> None:
        self._reset_progress()
        self._notify_settings_state(False)
        self._poller.stop()
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
        running = self._poller.is_running()

        # When Feature 4 is enabled, generation is blocked until all its
        # inputs and student counts are valid (spec 4.2).
        feature4_ok = (
            not self._controller.feature4_enabled
            or self._controller.feature4_ready()
        )

        self._gen_btn.setEnabled(
            not running
            and self._controller.has_courses
            and self._controller.has_periods
            and self._count_checked() >= 1
            and feature4_ok
        )
