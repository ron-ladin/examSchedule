"""
Proctor report dialog (spec 4.6 GUI view).

Shows the proctor report for the currently displayed schedule(s) in a read-only
view and lets the user export it to a .txt file. The report text is built by the
controller (src.engine.proctor_report); this dialog is presentation only.
"""

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class ProctorReportDialog(QDialog):
    """Read-only proctor report view with a .txt export action (spec 4.6)."""

    def __init__(self, report_text: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Proctor Report")
        self.resize(560, 520)
        self._report_text = report_text

        layout = QVBoxLayout(self)

        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        self._view.setPlainText(report_text)
        self._view.setStyleSheet("font-family: monospace; font-size: 12px;")
        layout.addWidget(self._view)

        buttons = QHBoxLayout()
        buttons.addStretch()

        export_btn = QPushButton("⬇  Export .txt")
        export_btn.clicked.connect(self._on_export)
        buttons.addWidget(export_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)

        layout.addLayout(buttons)

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
