"""
Proctor report dialog (spec 4.6 GUI view).

Shows the proctor report for the currently displayed schedule(s) in a read-only
view and lets the user export it to a .txt file. The report text is built by the
controller (src.engine.proctor_report); this dialog is presentation only.
"""

import re
from pathlib import Path

from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QSyntaxHighlighter
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

_PERIOD_HEADER_RE = re.compile(r"===.*===")
_DATE_LINE_RE = re.compile(r"\d{2}-\d{2}-\d{4}")
_TIME_LINE_RE = re.compile(r"\d{2}:\d{2}")
_PROCTOR_COUNT_RE = re.compile(r"Proctors:\s*(\d+)")

_PRIMARY_COLOR = "#0755B5"
_TEXT_COLOR = "#172033"


class _ReportHighlighter(QSyntaxHighlighter):
    """Add visual hierarchy without changing the exportable text."""

    def __init__(self, document) -> None:
        super().__init__(document)
        self._period = self._format(_PRIMARY_COLOR, bold=True, background="#EAF2FF")
        self._date = self._format(_TEXT_COLOR, bold=True)
        self._time = self._format("#7C3AED", bold=True)
        self._course = self._format("#334155", bold=True)
        self._room = self._format("#047857")
        self._proctors = self._format("#B45309", bold=True)

    @staticmethod
    def _format(
        colour: str, *, bold: bool = False, background: str | None = None
    ) -> QTextCharFormat:
        text_format = QTextCharFormat()
        text_format.setForeground(QColor(colour))
        if bold:
            text_format.setFontWeight(QFont.Weight.Bold)
        if background:
            text_format.setBackground(QColor(background))
        return text_format

    def highlightBlock(self, text: str) -> None:
        stripped = text.strip()
        if _PERIOD_HEADER_RE.fullmatch(stripped):
            self.setFormat(0, len(text), self._period)
        elif _DATE_LINE_RE.fullmatch(stripped):
            self.setFormat(0, len(text), self._date)
        elif _TIME_LINE_RE.fullmatch(stripped):
            self.setFormat(0, len(text), self._time)
        elif text.startswith("      ") and "| Proctors:" in text:
            self.setFormat(0, len(text), self._room)
            match = _PROCTOR_COUNT_RE.search(text)
            if match:
                self.setFormat(
                    match.start(),
                    match.end() - match.start(),
                    self._proctors,
                )
        elif text.startswith("    "):
            self.setFormat(0, len(text), self._course)


class ProctorReportDialog(QDialog):
    """Read-only proctor report view with a .txt export action (spec 4.6)."""

    def __init__(self, report_text: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Proctor Report")
        self.setMinimumSize(720, 580)
        self.resize(780, 680)
        self._report_text = report_text
        self.setStyleSheet(
            """
            QDialog { background: #F4F7FB; color: $TEXT_COLOR; }
            QFrame#reportHeader {
                background: #FFFFFF; border: 1px solid #DCE5F0;
                border-radius: 14px;
            }
            QFrame#summaryCard {
                background: #EFF6FF; border: 1px solid #BFDBFE;
                border-radius: 10px;
            }
            QPlainTextEdit {
                background: #FFFFFF; color: $TEXT_COLOR;
                border: 1px solid #DCE5F0; border-radius: 12px;
                padding: 14px; selection-background-color: #BFDBFE;
                selection-color: $TEXT_COLOR;
            }
            QPushButton {
                min-height: 38px; padding: 0 18px; border-radius: 8px;
                font-size: 12px; font-weight: 700;
            }
            QPushButton#exportButton {
                background: $PRIMARY_COLOR; color: #FFFFFF;
                border: 1px solid $PRIMARY_COLOR;
            }
            QPushButton#exportButton:hover { background: #06499B; }
            QPushButton#closeButton {
                background: #FFFFFF; color: #475569;
                border: 1px solid #CBD5E1;
            }
            QPushButton#closeButton:hover { background: #F8FAFC; }
            """
            .replace("$PRIMARY_COLOR", _PRIMARY_COLOR)
            .replace("$TEXT_COLOR", _TEXT_COLOR)
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        header = QFrame()
        header.setObjectName("reportHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 15, 18, 15)
        header_layout.setSpacing(5)

        title = QLabel("Proctor assignment review")
        title.setStyleSheet(
            f"font-size:20px; font-weight:800; color:{_TEXT_COLOR}; border:none;"
        )
        header_layout.addWidget(title)

        subtitle = QLabel(
            "Review each exam date, time slot, room capacity and required "
            "number of proctors before exporting the report."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size:12px; color:#64748B; border:none;")
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        summary_row = QHBoxLayout()
        summary_row.setSpacing(9)
        for value, label in self._report_summary(report_text):
            summary_row.addWidget(self._summary_card(value, label))
        layout.addLayout(summary_row)

        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        self._view.setPlainText(report_text)
        self._view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(10)
        self._view.setFont(font)
        self._highlighter = _ReportHighlighter(self._view.document())
        layout.addWidget(self._view, 1)

        buttons = QHBoxLayout()
        hint = QLabel("The downloaded file contains the complete report.")
        hint.setStyleSheet("font-size:11px; color:#64748B;")
        buttons.addWidget(hint)
        buttons.addStretch()

        export_btn = QPushButton("Download .txt")
        export_btn.setObjectName("exportButton")
        export_btn.setToolTip("Save this proctor report to your computer")
        export_btn.clicked.connect(self._on_export)
        self._export_btn = export_btn
        buttons.addWidget(export_btn)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("closeButton")
        close_btn.clicked.connect(self.accept)
        self._close_btn = close_btn
        buttons.addWidget(close_btn)

        layout.addLayout(buttons)

    @staticmethod
    def _report_summary(report_text: str) -> tuple[tuple[str, str], ...]:
        lines = report_text.splitlines()
        periods = sum(
            _PERIOD_HEADER_RE.fullmatch(line.strip()) is not None
            for line in lines
        )
        dates = sum(
            _DATE_LINE_RE.fullmatch(line.strip()) is not None
            for line in lines
        )
        rooms = sum("| Proctors:" in line for line in lines)
        proctors = sum(
            int(match.group(1))
            for match in _PROCTOR_COUNT_RE.finditer(report_text)
        )
        return (
            (str(periods), "Periods"),
            (str(dates), "Exam dates"),
            (str(rooms), "Room assignments"),
            (str(proctors), "Proctor positions"),
        )

    @staticmethod
    def _summary_card(value: str, label: str) -> QFrame:
        card = QFrame()
        card.setObjectName("summaryCard")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        card_layout.setSpacing(7)

        value_label = QLabel(value)
        value_label.setStyleSheet(
            f"font-size:17px; font-weight:800; color:{_PRIMARY_COLOR}; border:none;"
        )
        text_label = QLabel(label)
        text_label.setStyleSheet(
            "font-size:10px; font-weight:600; color:#475569; border:none;"
        )
        card_layout.addWidget(value_label)
        card_layout.addWidget(text_label)
        card_layout.addStretch()
        return card

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Proctor Report",
            "proctor_report.txt",
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return
        try:
            Path(path).write_text(self._report_text, encoding="utf-8")
            QMessageBox.information(self, "Exported", f"Proctor report saved to:\n{path}")
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Export Error",
                f"Could not write the proctor report file.\n\nReason: {exc}",
            )
