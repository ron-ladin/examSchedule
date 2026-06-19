"""Feature4Card — optional classroom-assignment input card (spec §4.1–4.4)."""

import logging
from pathlib import Path

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)

_SLOTS_PLACEHOLDER = "08:00, 12:00, 16:00"
_PROCTORS_PLACEHOLDER = "1:30"


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

        # 300 ms debounce timers so text-field validation fires after the user
        # pauses typing rather than on every keystroke.
        self._slots_timer = QTimer(self)
        self._slots_timer.setSingleShot(True)
        self._slots_timer.setInterval(300)
        self._slots_timer.timeout.connect(self._commit_slots_text)

        self._proctors_timer = QTimer(self)
        self._proctors_timer.setSingleShot(True)
        self._proctors_timer.setInterval(300)
        self._proctors_timer.timeout.connect(self._commit_proctors_text)

        self._build_ui()
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
            "Load a classrooms file, then enter or browse time slots and proctor ratio. "
            "All three inputs are required for generation."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:11px; color:#64748B; background:transparent;")
        vl.addWidget(desc)

        # ── Classrooms row — Browse file only (spec §4.1) ───────────────────
        self._classrooms_label = QLabel("Missing")
        self._classrooms_label.setWordWrap(True)
        self._classrooms_label.setStyleSheet(self._input_style("missing"))

        self._load_classrooms_btn = QPushButton("Browse")
        self._load_classrooms_btn.setFixedWidth(120)
        self._load_classrooms_btn.setEnabled(self._controller.feature4_enabled)
        self._load_classrooms_btn.clicked.connect(self._load_classrooms)

        crow = QHBoxLayout()
        crow.addWidget(self._row_title("Classrooms"))
        crow.addWidget(self._load_classrooms_btn)
        crow.addWidget(self._classrooms_label, 1)
        vl.addLayout(crow)

        # ── Time Slots row — manual text OR file browse ─────────────────────
        self._slots_edit = QLineEdit()
        self._slots_edit.setPlaceholderText(_SLOTS_PLACEHOLDER)
        self._slots_edit.setMaximumWidth(200)
        self._slots_edit.setToolTip(
            "Manual input: up to 3 time slots per day, HH:MM format (24h), "
            "ascending, at least 4h apart"
        )
        self._slots_edit.textChanged.connect(lambda _: self._slots_timer.start())

        self._load_slots_btn = QPushButton("Browse")
        self._load_slots_btn.setFixedWidth(120)
        self._load_slots_btn.setEnabled(self._controller.feature4_enabled)
        self._load_slots_btn.clicked.connect(self._load_time_slots)

        self._slots_label = QLabel("Missing")
        self._slots_label.setWordWrap(True)
        self._slots_label.setStyleSheet(self._input_style("missing"))

        srow = QHBoxLayout()
        srow.addWidget(self._row_title("Time Slots"))
        srow.addWidget(self._slots_edit)
        srow.addWidget(self._load_slots_btn)
        srow.addWidget(self._slots_label, 1)
        vl.addLayout(srow)

        # ── Proctor Ratio row — manual text OR file browse ──────────────────
        self._proctors_edit = QLineEdit()
        self._proctors_edit.setPlaceholderText(_PROCTORS_PLACEHOLDER)
        self._proctors_edit.setMaximumWidth(120)
        self._proctors_edit.setToolTip(
            "Manual input: proctor-to-student ratio in the form 1:X (e.g. 1:30)"
        )
        self._proctors_edit.textChanged.connect(lambda _: self._proctors_timer.start())

        self._load_proctors_btn = QPushButton("Browse")
        self._load_proctors_btn.setFixedWidth(120)
        self._load_proctors_btn.setEnabled(self._controller.feature4_enabled)
        self._load_proctors_btn.clicked.connect(self._load_proctor_config)

        self._proctors_label = QLabel("Missing")
        self._proctors_label.setWordWrap(True)
        self._proctors_label.setStyleSheet(self._input_style("missing"))

        prow = QHBoxLayout()
        prow.addWidget(self._row_title("Proctor Ratio"))
        prow.addWidget(self._proctors_edit)
        prow.addWidget(self._load_proctors_btn)
        prow.addWidget(self._proctors_label, 1)
        vl.addLayout(prow)

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

    def _set_feature4_input_controls_enabled(self, enabled: bool) -> None:
        self._load_classrooms_btn.setEnabled(enabled)
        self._load_slots_btn.setEnabled(enabled)
        self._load_proctors_btn.setEnabled(enabled)

    def _on_toggled(self, checked: bool) -> None:
        # Spec 4.3: Feature 4 cannot be enabled while the currently loaded
        # courses have Exam offerings without a StudentCount. Snap the toggle
        # back off and explain, instead of failing silently with a blocked
        # Generate button.
        if checked and self._controller.feature4_missing_student_counts():
            self._toggle.blockSignals(True)
            self._toggle.setChecked(False)
            self._toggle.blockSignals(False)
            self._controller.set_feature4_enabled(False)
            self._set_feature4_input_controls_enabled(False)
            self.refresh_status()
            self.gen_btn_update_needed.emit()

            QMessageBox.critical(
                self,
                "Cannot Enable Feature 4",
                "Feature 4 cannot be enabled because the currently loaded courses "
                "have Exam offerings without a StudentCount (spec 4.3).\n\n"
                "Load a courses file where every exam course has a StudentCount, "
                "then enable Feature 4.",
            )
            return

        self._controller.set_feature4_enabled(checked)
        self._set_feature4_input_controls_enabled(checked)
        self.refresh_status()
        self.gen_btn_update_needed.emit()

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

    # ── Classrooms: Browse file only (spec §4.1) ────────────────────────────

    def _load_classrooms(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Classrooms File",
            "",
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return

        try:
            count = self._controller.load_classrooms(Path(path))
            if count == 0:
                # §2.2.6: 0 valid rooms → show inline error, Generate stays blocked
                self._controller.clear_classrooms()
                self._classrooms_label.setText("No valid rooms in file")
                self._classrooms_label.setStyleSheet(self._input_style("invalid"))
                logger.warning("Classrooms file contained no valid rooms: %s", path)
            else:
                self._classrooms_label.setText(f"{Path(path).name} — {count} room(s)")
                self._classrooms_label.setStyleSheet(self._input_style("valid"))

        except Exception as exc:
            self._controller.clear_classrooms()
            self._classrooms_label.setText(f"{Path(path).name} — Invalid file")
            self._classrooms_label.setStyleSheet(self._input_style("invalid"))
            logger.warning("Invalid classrooms file: %s", exc)

            QMessageBox.critical(
                self,
                "Invalid Classrooms File",
                f"The selected classrooms file is invalid.\n\n"
                f"File: {Path(path).name}\nReason: {exc}",
            )

        self.refresh_status()
        self.gen_btn_update_needed.emit()

    # ── Time Slots: Browse file OR manual text input ────────────────────────

    def _load_time_slots(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Time Slots File",
            "",
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return

        try:
            count = self._controller.load_time_slots(Path(path))
            if count == 0:
                self._controller.clear_time_slots()
                self._slots_label.setText("No valid slots in file")
                self._slots_label.setStyleSheet(self._input_style("invalid"))
            else:
                self._slots_label.setText(f"{Path(path).name} — {count} slot(s)")
                self._slots_label.setStyleSheet(self._input_style("valid"))

        except Exception as exc:
            self._controller.clear_time_slots()
            self._slots_label.setText(f"{Path(path).name} — Invalid file")
            self._slots_label.setStyleSheet(self._input_style("invalid"))
            logger.warning("Invalid slots file: %s", exc)

            QMessageBox.critical(
                self,
                "Invalid Time Slots File",
                f"The selected time slots file is invalid.\n\n"
                f"File: {Path(path).name}\nReason: {exc}",
            )

        self.refresh_status()
        self.gen_btn_update_needed.emit()

    def _commit_slots_text(self) -> None:
        """Parse and validate the slots text field after the debounce delay."""
        try:
            text = self._slots_edit.text().strip()
            if not text:
                self._controller.clear_time_slots()
                self._slots_label.setText("Missing")
                self._slots_label.setStyleSheet(self._input_style("missing"))
            else:
                try:
                    count = self._controller.set_time_slots_from_text(text)
                    self._slots_label.setText(f"Manual input — {count} slot(s)")
                    self._slots_label.setStyleSheet(self._input_style("valid"))
                except ValueError:
                    self._controller.clear_time_slots()
                    self._slots_label.setText("Invalid — check format & gaps")
                    self._slots_label.setStyleSheet(self._input_style("invalid"))

            self.refresh_status()
            self.gen_btn_update_needed.emit()

        except Exception:
            logger.exception("Unexpected error in _commit_slots_text")

    # ── Proctor Ratio: Browse file OR manual text input ─────────────────────

    def _load_proctor_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Proctor Ratio File",
            "",
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return

        try:
            config = self._controller.load_proctor_config(Path(path))
            self._proctors_label.setText(
                f"{Path(path).name} — 1:{config.students_per_proctor}"
            )
            self._proctors_label.setStyleSheet(self._input_style("valid"))

        except Exception as exc:
            self._controller.clear_proctor_config()
            self._proctors_label.setText(f"{Path(path).name} — Invalid file")
            self._proctors_label.setStyleSheet(self._input_style("invalid"))
            logger.warning("Invalid proctor ratio file: %s", exc)

            QMessageBox.critical(
                self,
                "Invalid Proctor Ratio File",
                f"The selected proctor ratio file is invalid.\n\n"
                f"File: {Path(path).name}\nReason: {exc}",
            )

        self.refresh_status()
        self.gen_btn_update_needed.emit()

    def _commit_proctors_text(self) -> None:
        """Parse and validate the proctor ratio text field after debounce."""
        try:
            text = self._proctors_edit.text().strip()
            if not text:
                self._controller.clear_proctor_config()
                self._proctors_label.setText("Missing")
                self._proctors_label.setStyleSheet(self._input_style("missing"))
            else:
                try:
                    config = self._controller.set_proctor_config_from_text(text)
                    self._proctors_label.setText(
                        f"Manual input — 1:{config.students_per_proctor}"
                    )
                    self._proctors_label.setStyleSheet(self._input_style("valid"))
                except ValueError:
                    self._controller.clear_proctor_config()
                    self._proctors_label.setText("Invalid — use 1:X format")
                    self._proctors_label.setStyleSheet(self._input_style("invalid"))

            self.refresh_status()
            self.gen_btn_update_needed.emit()

        except Exception:
            logger.exception("Unexpected error in _commit_proctors_text")
