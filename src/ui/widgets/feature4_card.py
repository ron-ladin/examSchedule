"""Feature4Card — optional classroom-assignment input card (spec §4.1–4.4)."""

import logging
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)


def _section_lbl(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "font-size:10px; font-weight:700; color:#72778c;"
        " letter-spacing:0.6px; background:transparent;"
    )
    return lbl


class Feature4Card(QFrame):
    """Self-contained Feature 4 (classroom assignment) configuration card."""

    gen_btn_update_needed = pyqtSignal()

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._build_ui()
        self._apply_enabled_state()
        self.refresh_status()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            "QFrame { background: rgba(255, 255, 255, 0.75);"
            " border: 1px solid rgba(255, 255, 255, 0.9);"
            " border-radius: 12px; }"
        )
        eff = QGraphicsDropShadowEffect()
        eff.setBlurRadius(18)
        eff.setColor(QColor(0, 67, 148, 13))
        eff.setOffset(0, 4)
        self.setGraphicsEffect(eff)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(20, 18, 20, 18)
        vl.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(_section_lbl("FEATURE 4 - CLASSROOM ASSIGNMENT"))
        header.addStretch()

        self._status_lbl = QLabel()
        self._status_lbl.setFixedHeight(24)
        header.addWidget(self._status_lbl)
        vl.addLayout(header)

        self._toggle = QCheckBox("Enable classroom & slot assignment")
        self._toggle.setChecked(self._controller.feature4_enabled)
        self._toggle.toggled.connect(self._on_toggled)
        vl.addWidget(self._toggle)

        desc = QLabel(
            "When enabled, load classrooms, time slots, and proctor ratio .txt "
            "files. All three are required before generation."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:11px; color:#64748B; background:transparent;")
        vl.addWidget(desc)

        self._classrooms_label = QLabel("Missing")
        self._classrooms_label.setWordWrap(True)
        self._classrooms_label.setStyleSheet(self._input_style("missing"))
        self._load_classrooms_btn = QPushButton("Browse")
        self._load_classrooms_btn.setFixedWidth(120)
        self._load_classrooms_btn.clicked.connect(self._load_classrooms)
        crow = QHBoxLayout()
        crow.addWidget(self._row_title("Classrooms"))
        crow.addWidget(self._load_classrooms_btn)
        crow.addWidget(self._classrooms_label, 1)
        vl.addLayout(crow)

        self._load_slots_btn = QPushButton("Browse")
        self._load_slots_btn.setFixedWidth(120)
        self._load_slots_btn.clicked.connect(self._load_time_slots)
        self._slots_label = QLabel("Missing")
        self._slots_label.setWordWrap(True)
        self._slots_label.setStyleSheet(self._input_style("missing"))
        srow = QHBoxLayout()
        srow.addWidget(self._row_title("Time Slots"))
        srow.addWidget(self._load_slots_btn)
        srow.addWidget(self._slots_label, 1)
        vl.addLayout(srow)

        self._load_proctors_btn = QPushButton("Browse")
        self._load_proctors_btn.setFixedWidth(120)
        self._load_proctors_btn.clicked.connect(self._load_proctor_config)
        self._proctors_label = QLabel("Missing")
        self._proctors_label.setWordWrap(True)
        self._proctors_label.setStyleSheet(self._input_style("missing"))
        prow = QHBoxLayout()
        prow.addWidget(self._row_title("Proctor Ratio"))
        prow.addWidget(self._load_proctors_btn)
        prow.addWidget(self._proctors_label, 1)
        vl.addLayout(prow)

        self._inputs = [
            self._load_classrooms_btn,
            self._load_slots_btn,
            self._load_proctors_btn,
        ]

    @staticmethod
    def _row_title(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setMinimumWidth(105)
        lbl.setStyleSheet(
            "font-size:12px; font-weight:600; color:#171c20; background:transparent;"
        )
        return lbl

    @staticmethod
    def _input_style(state: str) -> str:
        colors = {
            "missing": ("#92400E", "#FEF3C7"),
            "valid": ("#047857", "#D1FAE5"),
            "invalid": ("#B91C1C", "#FEE2E2"),
        }
        fg, bg = colors[state]
        return (
            f"font-size:11px; color:{fg}; background:{bg};"
            " border-radius:4px; padding:3px 7px;"
        )

    def _on_toggled(self, checked: bool) -> None:
        if checked and self._controller.feature4_missing_student_counts():
            self._controller.set_feature4_enabled(False)
            self._toggle.setChecked(False)
            self._apply_enabled_state()
            QMessageBox.critical(
                self,
                "Missing Student Counts",
                "Feature 4 requires a StudentCount (5th column) for every Exam "
                "course, but the currently loaded courses file is missing at least "
                "one.\n\n"
                "Feature 4 has been disabled (spec §4.3). Reload a valid courses "
                "file before enabling Feature 4.",
            )
        else:
            self._controller.set_feature4_enabled(checked)
            self._apply_enabled_state()
        self.refresh_status()
        self.gen_btn_update_needed.emit()

    def _apply_enabled_state(self) -> None:
        for widget in self._inputs:
            widget.setEnabled(self._controller.feature4_enabled)

    def refresh_status(self) -> None:
        ctrl = self._controller
        active_style = (
            "font-size:11px; font-weight:800; color:#047857; background:#D1FAE5;"
            " border:1px solid #6EE7B7; border-radius:12px; padding:2px 10px;"
        )
        warn_style = (
            "font-size:11px; font-weight:800; color:#B91C1C; background:#FEE2E2;"
            " border:1px solid #FCA5A5; border-radius:12px; padding:2px 10px;"
        )
        idle_style = (
            "font-size:11px; font-weight:700; color:#64748B; background:#F1F5F9;"
            " border:1px solid #CBD5E1; border-radius:12px; padding:2px 10px;"
        )

        if not ctrl.feature4_enabled:
            text, style = "DISABLED", idle_style
        elif ctrl.feature4_ready():
            text, style = "ACTIVE", active_style
        elif ctrl.feature4_inputs_valid and ctrl.feature4_missing_student_counts():
            text, style = "BLOCKED - missing student counts", warn_style
        else:
            text, style = "INCOMPLETE - enter all inputs", idle_style

        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(style)
        if ctrl.feature4_ready():
            self.setStyleSheet(
                "QFrame { background:rgba(236,253,245,0.85);"
                " border:1px solid #6EE7B7; border-radius:12px; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { background:rgba(255,255,255,0.75);"
                " border:1px dashed #CBD5E1; border-radius:12px; }"
            )

    def _load_feature4_file(self, title, label, loader, clearer, success_text) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select {title} File", "",
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return

        try:
            result = loader(Path(path))
            label.setText(f"{Path(path).name} - {success_text(result)}")
            label.setStyleSheet(self._input_style("valid"))
        except Exception as exc:
            clearer()
            label.setText(f"{Path(path).name} - Invalid file")
            label.setStyleSheet(self._input_style("invalid"))
            logger.warning("Invalid Feature 4 %s file: %s", title, exc)
            QMessageBox.critical(
                self, "Invalid Feature 4 File",
                f"The selected {title.lower()} file is invalid.\n\n"
                f"File: {Path(path).name}\nReason: {exc}",
            )

        self.refresh_status()
        self.gen_btn_update_needed.emit()

    def _load_classrooms(self) -> None:
        self._load_feature4_file(
            "Classrooms", self._classrooms_label,
            self._controller.load_classrooms, self._controller.clear_classrooms,
            lambda count: f"{count} room(s)",
        )

    def _load_time_slots(self) -> None:
        self._load_feature4_file(
            "Time Slots", self._slots_label,
            self._controller.load_time_slots, self._controller.clear_time_slots,
            lambda count: f"{count} slot(s)",
        )

    def _load_proctor_config(self) -> None:
        self._load_feature4_file(
            "Proctor Ratio", self._proctors_label,
            self._controller.load_proctor_config, self._controller.clear_proctor_config,
            lambda config: f"1:{config.students_per_proctor}",
        )
