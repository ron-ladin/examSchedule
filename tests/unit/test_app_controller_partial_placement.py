"""
Integration Tests: AppController — partial classroom placement (SCRUM-390).

Strategy "Always place what you can, flag the gap": a single exam that is
structurally too large for any room arrangement must NOT blank the whole
solution space. Generation should still succeed for the placeable exams and
flag the oversized one in ``unassigned_classroom_exams`` — automatically,
without the caller flipping the manual ``allow_unassigned_classrooms`` toggle.

Uses the real ScheduleGenerator + ExactConflictStrategy + ClassroomAssigner
through AppController. No PyQt, no QApplication, no file I/O.
"""

from datetime import date, time

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.domain.classroom import Classroom
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.proctor import ProctorConfig
from src.domain.time_slot import TimeSlot
from src.engine.app_controller import AppController
from src.engine.schedule_generator import ScheduleGenerator

from tests.unit._app_controller_helpers import FakeDataProvider, FakeExporter

_BIG_COURSE_ID = "10004"
_SMALL_COURSE_ID = "10002"


def _exam(course_id, name, program_id, year, student_count):
    course = Course(
        id=course_id,
        name=name,
        instructor="Dr. Test",
        evaluation_type="Exam",
    )
    course.add_offering(
        CourseOffering(
            program_id=program_id,
            year=year,
            semester="FALL",
            requirement="Obligatory",
            student_count=student_count,
        )
    )
    return course


def _build_controller(allow_unassigned: bool) -> tuple[AppController, FakeExporter]:
    # One auditorium: usable capacity 0.75 * 250 = 187.
    # BIG exam (400) cannot fit; SMALL exam (35) fits comfortably.
    big = _exam(_BIG_COURSE_ID, "Advanced Materials", "83109", 3, 400)
    small = _exam(_SMALL_COURSE_ID, "Database Systems", "83104", 2, 35)
    selected_programs = ["83109", "83104"]

    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 9))],  # Mon–Fri, 5 weekdays
    )

    exporter = FakeExporter()
    controller = AppController(
        data_provider=FakeDataProvider([big, small], [period]),
        exporter=exporter,
        generator=ScheduleGenerator(
            conflict_strategy=ExactConflictStrategy(selected_programs=selected_programs)
        ),
        selected_programs=selected_programs,
        classrooms=[Classroom("Auditorium 101", 250)],
        time_slots=[TimeSlot(time(9, 0))],
        proctor_config=ProctorConfig(20),
        allow_unassigned_classrooms=allow_unassigned,
    )
    return controller, exporter


def _all_schedules(exporter: FakeExporter):
    return [
        schedule
        for schedules in exporter.materialized_schedules.values()
        for schedule in schedules
    ]


# Core regression: with the manual toggle OFF, an oversized exam used to drop
# every schedule. The new policy must still yield schedules.
def test_oversized_exam_does_not_blank_solution_space():
    controller, exporter = _build_controller(allow_unassigned=False)

    controller.run()

    schedules = _all_schedules(exporter)
    assert schedules, "oversized exam blanked the entire solution space"


# The placeable exam is fully room-mapped; the oversized one is flagged unassigned.
def test_oversized_exam_is_isolated_and_flagged():
    controller, exporter = _build_controller(allow_unassigned=False)

    controller.run()

    schedules = _all_schedules(exporter)
    assert schedules

    for schedule in schedules:
        # The 400-student exam cannot be placed: flagged, never room-mapped.
        assert _BIG_COURSE_ID in schedule.unassigned_classroom_exams
        assert schedule.unassigned_classroom_exams[_BIG_COURSE_ID] == 400
        assert not schedule.classroom_assignments.get(_BIG_COURSE_ID)

        # The 35-student exam is fully assigned a room.
        assert schedule.classroom_assignments.get(_SMALL_COURSE_ID)
        assert _SMALL_COURSE_ID not in schedule.unassigned_classroom_exams
