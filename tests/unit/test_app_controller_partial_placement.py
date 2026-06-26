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
from src.domain.feature4_validator import Feature4Validator
from src.domain.partial_placement_policy import (
    PartialPlacementPolicy,
    PlacementFailureReason,
)
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


def _make_controller(
    courses,
    selected_programs,
    classrooms,
    *,
    allow_unassigned,
    date_ranges,
    time_slots=None,
) -> tuple[AppController, FakeExporter]:
    """Wire a real ScheduleGenerator + ClassroomAssigner through AppController."""
    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=date_ranges,
    )

    exporter = FakeExporter()
    controller = AppController(
        data_provider=FakeDataProvider(courses, [period]),
        exporter=exporter,
        generator=ScheduleGenerator(
            conflict_strategy=ExactConflictStrategy(selected_programs=selected_programs)
        ),
        selected_programs=selected_programs,
        classrooms=classrooms,
        time_slots=time_slots or [TimeSlot(time(9, 0))],
        proctor_config=ProctorConfig(20),
        allow_unassigned_classrooms=allow_unassigned,
    )
    return controller, exporter


def _build_controller(allow_unassigned: bool) -> tuple[AppController, FakeExporter]:
    # One auditorium: usable capacity 0.75 * 250 = 187.
    # BIG exam (400) cannot fit; SMALL exam (35) fits comfortably.
    big = _exam(_BIG_COURSE_ID, "Advanced Materials", "83109", 3, 400)
    small = _exam(_SMALL_COURSE_ID, "Database Systems", "83104", 2, 35)
    selected_programs = ["83109", "83104"]

    return _make_controller(
        [big, small],
        selected_programs,
        [Classroom("Auditorium 101", 250)],
        allow_unassigned=allow_unassigned,
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 9))],  # Mon–Fri, 5 weekdays
    )


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


# --- Scenario A: two oversized exams + one normal exam ---------------------
# Both structurally oversized exams must be flagged, the normal exam stays
# fully assigned, and schedules are still produced.
_SECOND_BIG_COURSE_ID = "10005"


def test_scenario_a_two_oversized_exams_and_one_normal():
    # One auditorium: usable capacity 187. Both 400 and 350 exceed it; 35 fits.
    big_one = _exam(_BIG_COURSE_ID, "Advanced Materials", "83109", 3, 400)
    big_two = _exam(_SECOND_BIG_COURSE_ID, "Quantum Mechanics", "83110", 3, 350)
    small = _exam(_SMALL_COURSE_ID, "Database Systems", "83104", 2, 35)
    selected_programs = ["83109", "83110", "83104"]

    controller, exporter = _make_controller(
        [big_one, big_two, small],
        selected_programs,
        [Classroom("Auditorium 101", 250)],
        allow_unassigned=False,  # automatic structural routing, no manual toggle
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 9))],
    )

    controller.run()

    schedules = _all_schedules(exporter)
    assert schedules, "oversized exams blanked the entire solution space"

    for schedule in schedules:
        for big_id, count in ((_BIG_COURSE_ID, 400), (_SECOND_BIG_COURSE_ID, 350)):
            assert schedule.unassigned_classroom_exams.get(big_id) == count
            assert not schedule.classroom_assignments.get(big_id)

        assert schedule.classroom_assignments.get(_SMALL_COURSE_ID)
        assert _SMALL_COURSE_ID not in schedule.unassigned_classroom_exams


# --- Scenario B: runtime assignment failure -------------------------------
# Capacity is structurally sufficient for each exam, but two same-day exams
# cannot both occupy the single room in the single time slot. The exam that
# cannot be placed must follow the RUNTIME path, not the STRUCTURAL one.
_RUNTIME_COURSE_A = "20001"
_RUNTIME_COURSE_B = "20002"


def test_scenario_b_runtime_failure_follows_runtime_path():
    # One room: usable capacity 75. Each 50-student exam fits alone (50 <= 75),
    # so neither is a structural shortfall. But one room in one slot cannot hold
    # two distinct same-day exams, forcing a runtime assignment failure.
    rooms = [Classroom("Room 1", 100)]
    exam_a = _exam(_RUNTIME_COURSE_A, "Algorithms", "83201", 2, 50)
    exam_b = _exam(_RUNTIME_COURSE_B, "Operating Systems", "83202", 2, 50)
    selected_programs = ["83201", "83202"]

    # Sanity: neither exam is structurally un-placeable.
    structural = Feature4Validator.unplaceable_exams([exam_a, exam_b], rooms)
    assert structural == []

    controller, exporter = _make_controller(
        [exam_a, exam_b],
        selected_programs,
        rooms,
        allow_unassigned=True,  # manual toggle enables flagging runtime failures
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 5))],  # single day → same date
    )

    controller.run()

    schedules = _all_schedules(exporter)
    assert schedules

    structural_ids = frozenset(exam.course_id for exam in structural)
    saw_runtime_unassigned = False
    for schedule in schedules:
        for course_id in schedule.unassigned_classroom_exams:
            reason = PartialPlacementPolicy.classify(course_id, structural_ids)
            assert reason is PlacementFailureReason.RUNTIME_ASSIGNMENT_FAILURE
            saw_runtime_unassigned = True

    assert saw_runtime_unassigned, "expected a runtime assignment failure to be flagged"
