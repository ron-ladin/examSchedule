import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip(
    "PyQt6.QtWidgets",
    reason="PyQt6 native GUI libraries are not available in this environment.",
    exc_type=ImportError,
)
QApplication = QtWidgets.QApplication
QLabel = QtWidgets.QLabel
QTableWidget = QtWidgets.QTableWidget

from src.ui.proctor_report_dialog import ProctorReportDialog


def _get_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


VALID_REPORT = (
    "=== FALL - Aleph ===\n"
    "29-01-2026\n"
    "  09:00\n"
    "    Physics 1 (83102)\n"
    "      Room 101: 150/250 | Proctors: 8\n"
    "  13:00\n"
    "    Chemistry (83101)\n"
    "      Lab 2: 40/60 | Proctors: 2\n"
    "\n"
    "=== SPRING - Bet ===\n"
    "05-02-2026\n"
    "  09:00\n"
    "    Algorithms (83108)\n"
    "      Hall A: 75/100 | Proctors: 4"
)


def test_proctor_report_dialog_parses_valid_report():
    periods = ProctorReportDialog._parse_report(VALID_REPORT)

    assert [period["title"] for period in periods] == ["FALL - Aleph", "SPRING - Bet"]
    assert len(periods[0]["rows"]) == 2
    first = periods[0]["rows"][0]
    assert first["date"] == "29-01-2026"
    assert first["time"] == "09:00"
    assert first["course"] == "Physics 1 (83102)"
    assert first["room"] == "Room 101"
    assert first["assigned"] == 150
    assert first["capacity"] == 250
    assert first["usage"] == "150/250"
    assert first["proctors"] == 8


def test_proctor_report_dialog_summary_values_and_multiple_periods():
    assert ProctorReportDialog._report_summary(VALID_REPORT) == (
        ("2", "Periods"),
        ("2", "Exam dates"),
        ("3", "Room assignments"),
        ("14", "Proctor positions"),
    )


def test_proctor_report_dialog_groups_rows_by_exam_period():
    app = _get_qapp()
    dialog = ProctorReportDialog(
        "=== FALL - Aleph ===\n"
        "29-01-2026\n"
        "  09:00\n"
        "    Physics 1 (83102)\n"
        "      Room 101: 150/250 | Proctors: 8"
    )
    tables = dialog.findChildren(QTableWidget)

    assert len(tables) == 1
    assert tables[0].rowCount() == 1
    assert tables[0].item(0, 2).text() == "Physics 1 (83102)"

    dialog.close()
    app.processEvents()


def test_proctor_report_dialog_empty_or_malformed_input_does_not_crash():
    app = _get_qapp()
    dialog = ProctorReportDialog("not a valid report")

    assert dialog.findChildren(QTableWidget) == []
    assert dialog._view.isHidden() is False
    assert dialog._view.toPlainText() == "not a valid report"
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert any("No room assignments are available" in text for text in labels)

    dialog.close()
    app.processEvents()
