"""
Proctor report dialog (spec 4.6 GUI view).

Shows the proctor report for the currently displayed schedule(s) in a read-only
view and lets the user export it to a .txt file. The report text is built by the
controller (src.engine.proctor_report); this dialog is presentation only.
"""

import re
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_PERIOD_HEADER_RE = re.compile(r"===.*===")
_DATE_LINE_RE = re.compile(r"\d{2}-\d{2}-\d{4}")
_TIME_LINE_RE = re.compile(r"\d{2}:\d{2}")
_PROCTOR_COUNT_RE = re.compile(r"Proctors:\s*(\d+)")
_ROOM_LINE_RE = re.compile(
    r"^(?P<room>.+):\s*(?P<assigned>\d+)/(?P<capacity>\d+)\s*\|\s*"
    r"Proctors:\s*(?P<proctors>\d+)$"
)

_PRIMARY_COLOR = "#0755B5"
_TEXT_COLOR = "#172033"


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
            QFrame#periodCard {
                background: #FFFFFF; border: 1px solid #DCE5F0;
                border-radius: 12px;
            }
            QScrollArea {
                background: transparent; border: none;
            }
            QTableWidget {
                background: #FFFFFF; color: $TEXT_COLOR;
                border: 1px solid #E2E8F0; border-radius: 8px;
                gridline-color: #E8EEF7;
                selection-background-color: #DBEAFE;
                selection-color: $TEXT_COLOR;
            }
            QHeaderView::section {
                background: #F8FAFC; color: #475569;
                border: none; border-right: 1px solid #E2E8F0;
                border-bottom: 1px solid #E2E8F0;
                padding: 7px 6px; font-size: 11px; font-weight: 700;
            }
            QTableWidget::item {
                padding: 5px; border-bottom: 1px solid #F1F5F9;
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
        self._view.setVisible(False)

        self._report_area = self._build_visual_report(report_text)
        layout.addWidget(self._report_area, 1)

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
    def _parse_report(report_text: str) -> list[dict]:
        periods: list[dict] = []
        current_period: dict | None = None
        current_date = ""
        current_time = ""
        current_course = ""

        for raw_line in report_text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue

            if _PERIOD_HEADER_RE.fullmatch(stripped):
                title = stripped.strip("= ").strip()
                current_period = {"title": title, "rows": []}
                periods.append(current_period)
                current_date = ""
                current_time = ""
                current_course = ""
                continue

            if current_period is None:
                current_period = {"title": "Selected schedule", "rows": []}
                periods.append(current_period)

            if _DATE_LINE_RE.fullmatch(stripped):
                current_date = stripped
                current_time = ""
                current_course = ""
                continue

            if _TIME_LINE_RE.fullmatch(stripped):
                current_time = stripped
                current_course = ""
                continue

            room_match = _ROOM_LINE_RE.fullmatch(stripped)
            if room_match:
                assigned = int(room_match.group("assigned"))
                capacity = int(room_match.group("capacity"))
                proctors = int(room_match.group("proctors"))
                current_period["rows"].append(
                    {
                        "date": current_date,
                        "time": current_time,
                        "course": current_course,
                        "room": room_match.group("room"),
                        "assigned": assigned,
                        "capacity": capacity,
                        "usage": f"{assigned}/{capacity}",
                        "proctors": proctors,
                    }
                )
                continue

            if current_time:
                current_course = stripped

        return periods

    def _build_visual_report(self, report_text: str) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        periods = self._parse_report(report_text)
        rendered_any = False
        for period in periods:
            rows = period["rows"]
            if not rows:
                continue
            content_layout.addWidget(self._period_table_card(period["title"], rows))
            rendered_any = True

        if not rendered_any:
            empty = QLabel(
                "No room assignments are available for the selected schedule.\n"
                "Generate with classroom assignments to review proctor coverage here."
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            empty.setStyleSheet(
                "background:#FFFFFF; color:#64748B; border:1px solid #DCE5F0;"
                "border-radius:12px; padding:32px; font-size:13px;"
            )
            content_layout.addWidget(empty)

        content_layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _period_table_card(self, title: str, rows: list[dict]) -> QFrame:
        card = QFrame()
        card.setObjectName("periodCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        total_proctors = sum(row["proctors"] for row in rows)
        total_students = sum(row["assigned"] for row in rows)
        date_count = len({row["date"] for row in rows})

        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"font-size:16px; font-weight:800; color:{_PRIMARY_COLOR}; border:none;"
        )
        layout.addWidget(title_label)

        helper = QLabel(
            f"{date_count} exam date(s), {len(rows)} room assignment(s), "
            f"{total_students} seated student(s), {total_proctors} proctor position(s)."
        )
        helper.setWordWrap(True)
        helper.setStyleSheet("font-size:12px; color:#64748B; border:none;")
        layout.addWidget(helper)

        table = QTableWidget(len(rows), 8)
        table.setHorizontalHeaderLabels(
            [
                "Date",
                "Time",
                "Course",
                "Room",
                "Students",
                "Capacity",
                "Usage",
                "Proctors",
            ]
        )
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setMinimumHeight(min(360, 70 + len(rows) * 34))

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for col in (4, 5, 6, 7):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        for row_index, row in enumerate(rows):
            values = [
                row["date"],
                row["time"],
                row["course"],
                row["room"],
                str(row["assigned"]),
                str(row["capacity"]),
                row["usage"],
                str(row["proctors"]),
            ]
            for col_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col_index in (4, 5, 6, 7):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                    )
                if col_index == 7:
                    item.setForeground(QColor(_PRIMARY_COLOR))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                table.setItem(row_index, col_index, item)

        table.resizeRowsToContents()
        layout.addWidget(table)
        return card

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
