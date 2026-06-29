"""
Unit Tests: ProgrammeCoursesDialog (SRS §2.3.2)
------------------------------------------------
Verifies the per-programme course drill-down dialog renders correctly and
applies Year / Semester filters in real-time.
"""

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

from src.controller import DesktopController
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.ui.programme_courses_dialog import ProgrammeCoursesDialog


_APP: "QApplication | None" = None  # module-level ref prevents CPython GC


def _get_qapp() -> QApplication:
    global _APP
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    _APP = app
    return app


@pytest.fixture(autouse=True)
def _cleanup_programme_dialogs():
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        if isinstance(widget, ProgrammeCoursesDialog):
            widget.close()
            widget.deleteLater()
    app.processEvents()


def _make_controller_with_courses() -> DesktopController:
    """Build a controller pre-loaded with deterministic test courses."""
    ctrl = DesktopController()

    courses = [
        Course(
            id="10001",
            name="Calculus I",
            instructor="Dr. A",
            evaluation_type="Exam",
            offerings=[
                CourseOffering(program_id="83101", year=1, semester="FALL", requirement="Obligatory"),
            ],
        ),
        Course(
            id="10002",
            name="Linear Algebra",
            instructor="Dr. B",
            evaluation_type="Exam",
            offerings=[
                CourseOffering(program_id="83101", year=1, semester="SPRI", requirement="Obligatory"),
            ],
        ),
        Course(
            id="10003",
            name="Data Structures",
            instructor="Dr. C",
            evaluation_type="Project",
            offerings=[
                CourseOffering(program_id="83101", year=2, semester="FALL", requirement="Obligatory"),
                CourseOffering(program_id="83102", year=2, semester="FALL", requirement="Elective"),
            ],
        ),
        Course(
            id="10004",
            name="Algorithms",
            instructor="Dr. D",
            evaluation_type="Exam",
            offerings=[
                CourseOffering(program_id="83101", year=2, semester="SPRI", requirement="Elective"),
            ],
        ),
        Course(
            id="10005",
            name="OS Internals",
            instructor="Dr. E",
            evaluation_type="Attendance",
            offerings=[
                CourseOffering(program_id="83101", year=3, semester="FALL", requirement="Obligatory"),
            ],
        ),
    ]

    ctrl._courses = courses
    return ctrl


def _row_count(dlg: ProgrammeCoursesDialog) -> int:
    return dlg._table.rowCount()


def _cell(dlg: ProgrammeCoursesDialog, row: int, col: int) -> str:
    item = dlg._table.item(row, col)
    return item.text() if item else ""


class TestProgrammeCoursesDialogCreation:
    def test_dialog_opens_without_crash(self):
        _get_qapp()
        ctrl = _make_controller_with_courses()
        dlg = ProgrammeCoursesDialog("83101", ctrl)
        assert dlg is not None
        dlg.close()

    def test_window_title_contains_programme_id(self):
        _get_qapp()
        ctrl = _make_controller_with_courses()
        dlg = ProgrammeCoursesDialog("83101", ctrl)
        assert "83101" in dlg.windowTitle() or "Courses" in dlg.windowTitle()
        dlg.close()

    def test_shows_all_courses_for_programme_by_default(self):
        """83101 has 5 offerings (10001×1, 10002×1, 10003×1, 10004×1, 10005×1)."""
        _get_qapp()
        ctrl = _make_controller_with_courses()
        dlg = ProgrammeCoursesDialog("83101", ctrl)
        assert _row_count(dlg) == 5
        dlg.close()

    def test_excludes_offerings_for_other_programmes(self):
        """83102 only appears on 10003 with one offering."""
        _get_qapp()
        ctrl = _make_controller_with_courses()
        dlg = ProgrammeCoursesDialog("83102", ctrl)
        assert _row_count(dlg) == 1
        dlg.close()

    def test_empty_programme_shows_no_rows(self):
        _get_qapp()
        ctrl = _make_controller_with_courses()
        dlg = ProgrammeCoursesDialog("99999", ctrl)
        assert _row_count(dlg) == 0
        dlg.close()


class TestProgrammeCoursesDialogFilters:
    def test_year_filter_year1(self):
        """Year 1 has 2 offerings for 83101: Calculus I (FALL) and Linear Algebra (SPRI)."""
        _get_qapp()
        ctrl = _make_controller_with_courses()
        dlg = ProgrammeCoursesDialog("83101", ctrl)
        dlg._year_combo.setCurrentText("Year 1")
        assert _row_count(dlg) == 2
        dlg.close()

    def test_year_filter_year2(self):
        """Year 2 has 2 offerings for 83101: Data Structures (FALL) and Algorithms (SPRI)."""
        _get_qapp()
        ctrl = _make_controller_with_courses()
        dlg = ProgrammeCoursesDialog("83101", ctrl)
        dlg._year_combo.setCurrentText("Year 2")
        assert _row_count(dlg) == 2
        dlg.close()

    def test_year_filter_year3(self):
        """Year 3 has 1 offering for 83101: OS Internals."""
        _get_qapp()
        ctrl = _make_controller_with_courses()
        dlg = ProgrammeCoursesDialog("83101", ctrl)
        dlg._year_combo.setCurrentText("Year 3")
        assert _row_count(dlg) == 1
        dlg.close()

    def test_semester_filter_fall(self):
        """FALL semester for 83101: Calculus I (Y1), Data Structures (Y2), OS Internals (Y3)."""
        _get_qapp()
        ctrl = _make_controller_with_courses()
        dlg = ProgrammeCoursesDialog("83101", ctrl)
        dlg._sem_combo.setCurrentText("FALL")
        assert _row_count(dlg) == 3
        dlg.close()

    def test_semester_filter_spring(self):
        """SPRING semester for 83101: Linear Algebra (Y1), Algorithms (Y2)."""
        _get_qapp()
        ctrl = _make_controller_with_courses()
        dlg = ProgrammeCoursesDialog("83101", ctrl)
        dlg._sem_combo.setCurrentText("SPRING")
        assert _row_count(dlg) == 2
        dlg.close()

    def test_combined_year_and_semester_filter(self):
        """Year 2 + FALL for 83101: only Data Structures."""
        _get_qapp()
        ctrl = _make_controller_with_courses()
        dlg = ProgrammeCoursesDialog("83101", ctrl)
        dlg._year_combo.setCurrentText("Year 2")
        dlg._sem_combo.setCurrentText("FALL")
        assert _row_count(dlg) == 1
        assert _cell(dlg, 0, 1) == "Data Structures"
        dlg.close()

    def test_all_filters_restore_full_count(self):
        _get_qapp()
        ctrl = _make_controller_with_courses()
        dlg = ProgrammeCoursesDialog("83101", ctrl)
        dlg._year_combo.setCurrentText("Year 1")
        dlg._sem_combo.setCurrentText("FALL")
        assert _row_count(dlg) == 1
        dlg._year_combo.setCurrentText("All Years")
        dlg._sem_combo.setCurrentText("All Semesters")
        assert _row_count(dlg) == 5
        dlg.close()


class TestProgrammeCoursesDialogTableContent:
    def test_columns_populated_correctly(self):
        """Check that Course ID, Name, Year, Semester, Req, Eval columns are populated."""
        _get_qapp()
        ctrl = _make_controller_with_courses()
        dlg = ProgrammeCoursesDialog("83101", ctrl)
        dlg._year_combo.setCurrentText("Year 1")
        dlg._sem_combo.setCurrentText("FALL")

        assert _row_count(dlg) == 1
        assert _cell(dlg, 0, 0) == "10001"
        assert _cell(dlg, 0, 1) == "Calculus I"
        assert _cell(dlg, 0, 2) == "1"
        assert _cell(dlg, 0, 3) == "FALL"
        assert _cell(dlg, 0, 4) == "Obligatory"
        assert _cell(dlg, 0, 5) == "Exam"
        dlg.close()

    def test_elective_requirement_shown(self):
        """Algorithms is Elective — verify the column says Elective."""
        _get_qapp()
        ctrl = _make_controller_with_courses()
        dlg = ProgrammeCoursesDialog("83101", ctrl)
        dlg._year_combo.setCurrentText("Year 2")
        dlg._sem_combo.setCurrentText("SPRING")

        assert _row_count(dlg) == 1
        assert _cell(dlg, 0, 4) == "Elective"
        dlg.close()
