"""
Unit tests: ResultsPanel un-placeable-exam banner (SCRUM-390).

The "always place what you can, flag the gap" strategy lets generation succeed
while leaving oversized exams unassigned. The results panel must surface those
gaps honestly: a top-level banner naming each exam left without a room, phrased
by structural-vs-runtime cause when that data is reachable.
"""

import os
import sys
from datetime import date, time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip(
    "PyQt6.QtWidgets",
    reason="PyQt6 native GUI libraries are not available in this environment.",
    exc_type=ImportError,
)

from src.controller import DesktopController
from src.domain.classroom import Classroom
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.proctor import ProctorConfig
from src.domain.schedule import Schedule
from src.domain.time_slot import TimeSlot
from src.ui.results_panel import _ResultsPanel

QApplication = QtWidgets.QApplication


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication(sys.argv)


def _period() -> ExamPeriod:
    return ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 9))])


def _course(student_count: int) -> Course:
    return Course(
        "11111",
        "Calculus",
        "Dr. Cohen",
        "Exam",
        [CourseOffering("83101", 1, "FALL", "Obligatory", student_count)],
    )


def _panel_showing(qapp, schedule: Schedule, course: Course, ctrl) -> _ResultsPanel:
    panel = _ResultsPanel(ctrl)
    panel.load({}, {}, {}, set())
    panel._schedules_by_period = {"FALL - Aleph": [schedule]}
    panel._period_indices = {"FALL - Aleph": 0}
    panel._courses_by_id = {course.id: course}
    panel._refresh_unassigned_banner()
    qapp.processEvents()
    return panel


def test_banner_hidden_when_no_unassigned_exams(qapp):
    ctrl = DesktopController()
    schedule = Schedule(_period(), {"11111": date(2026, 1, 6)})
    panel = _panel_showing(qapp, schedule, _course(50), ctrl)
    assert panel._unassigned_banner.isHidden() is True
    assert panel._unassigned_banner.text() == ""


def test_banner_names_structural_unassigned_exam(qapp):
    """A structurally oversized exam is named with the 'exceeds all room
    capacity' cause via the relevance-aware structural classification."""
    ctrl = DesktopController()
    ctrl._feature4_enabled = True
    ctrl._classrooms = [Classroom("Room 1", 20)]  # 15 usable
    ctrl._time_slots = [TimeSlot(time(9, 0))]
    ctrl._proctor_config = ProctorConfig(20)
    ctrl._selected_programs = ["83101"]
    ctrl._exam_periods = [_period()]
    ctrl._courses = [_course(75)]  # 75 > 15 usable -> structural

    schedule = Schedule(_period(), {}, {}, {"11111": 75})
    panel = _panel_showing(qapp, schedule, _course(75), ctrl)

    text = panel._unassigned_banner.text()
    assert panel._unassigned_banner.isHidden() is False
    assert "1 exam(s) could not be assigned rooms" in text
    assert "Calculus" in text
    assert "exceeds all room capacity" in text


def test_banner_uses_runtime_phrasing_when_not_structural(qapp):
    """An unassigned exam that is not a known structural shortfall is phrased as
    a runtime (no free room/slot) failure."""
    ctrl = DesktopController()  # feature 4 inactive -> no structural ids
    schedule = Schedule(_period(), {}, {}, {"11111": 5})
    panel = _panel_showing(qapp, schedule, _course(5), ctrl)

    text = panel._unassigned_banner.text()
    assert panel._unassigned_banner.isHidden() is False
    assert "no free room/slot" in text
    assert "Calculus" in text


# ── Step 4.2: per-period empty reason replaces "No valid schedules found" ──────


def _empty_panel(qapp, ctrl) -> _ResultsPanel:
    panel = _ResultsPanel(ctrl)
    panel.load({}, {}, {}, set())
    panel._schedules_by_period = {"FALL - Aleph": []}
    panel._period_indices = {"FALL - Aleph": 0}
    panel._update_summary()
    qapp.processEvents()
    return panel


def test_empty_summary_reports_no_relevant_courses(qapp):
    ctrl = DesktopController()
    ctrl._exam_periods = [_period()]
    ctrl._selected_programs = ["83101"]
    ctrl._courses = []  # nothing relevant
    panel = _empty_panel(qapp, ctrl)
    text = panel._summary_lbl.text()
    assert "No valid schedules found." not in text
    assert "No relevant courses" in text


def test_empty_summary_reports_threshold_when_courses_and_dates_exist(qapp):
    ctrl = DesktopController()
    ctrl._exam_periods = [_period()]
    ctrl._selected_programs = ["83101"]
    ctrl._courses = [_course(10)]  # relevant, dates valid -> threshold reason
    panel = _empty_panel(qapp, ctrl)
    assert "spacing (threshold) rules" in panel._summary_lbl.text()


def test_empty_period_card_label_shows_reason(qapp):
    ctrl = DesktopController()
    ctrl._exam_periods = [_period()]
    ctrl._selected_programs = ["83101"]
    ctrl._courses = []
    panel = _ResultsPanel(ctrl)
    panel.load({"FALL - Aleph": []}, {}, {}, set())
    qapp.processEvents()
    card = panel._cards.get("FALL - Aleph")
    assert card is not None
    assert "No relevant courses" in card.empty_label.text()
