"""Feature 4 classroom assignment and pipeline integration tests."""

from datetime import date, time
from queue import Queue

import pytest

from src.controller import _run_generation_process
from src.domain.classroom import Classroom
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.proctor import ProctorConfig
from src.domain.schedule import Schedule
from src.domain.time_slot import TimeSlot
from src.engine.classroom_assigner import (
    ClassroomAssigner,
    _balanced_distribution,
)


def _period() -> ExamPeriod:
    return ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 5))])


def _course(course_id: str, students: int) -> Course:
    return Course(
        course_id,
        f"Course {course_id}",
        "Dr. Test",
        "Exam",
        [CourseOffering("83101", 1, "FALL", "Obligatory", students)],
    )


def test_assigner_splits_exam_across_rooms_and_adds_proctor_counts():
    course = _course("11111", 70)
    schedule = Schedule(_period(), {"11111": date(2026, 1, 5)})

    assigned = ClassroomAssigner.assign(
        schedule,
        [course],
        ["83101"],
        [Classroom("Room 1", 50), Classroom("Room 2", 50)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )

    rooms = assigned.classroom_assignments["11111"]
    assert [(item.room.room_id, item.students_assigned) for item in rooms] == [
        ("Room 1", 35),
        ("Room 2", 35),
    ]
    assert [item.proctor_count for item in rooms] == [2, 2]
    assert all(
        item.students_assigned <= item.room.capacity
        for item in rooms
    )


def test_assigner_skips_non_exam_courses():
    """Spec 4.4: evaluation types other than 'Exam' are never assigned rooms."""
    project = Course(
        "33333",
        "Final Project",
        "Dr. Test",
        "Project",
        [CourseOffering("83101", 1, "FALL", "Obligatory", 30)],
    )
    schedule = Schedule(_period(), {"33333": date(2026, 1, 5)})

    assigned = ClassroomAssigner.assign(
        schedule,
        [project],
        ["83101"],
        [Classroom("Room 1", 50)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )

    assert assigned is not None
    assert "33333" not in assigned.classroom_assignments
    assert "33333" not in assigned.unassigned_classroom_exams


def test_assigner_does_not_mutate_input_schedule():
    """Immutability rule: assign() returns a new Schedule, leaving input intact."""
    course = _course("11111", 30)
    schedule = Schedule(_period(), {"11111": date(2026, 1, 5)})

    assigned = ClassroomAssigner.assign(
        schedule,
        [course],
        ["83101"],
        [Classroom("Room 1", 50)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )

    assert assigned is not schedule
    assert schedule.classroom_assignments == {}
    assert assigned.classroom_assignments["11111"]


def test_assigner_uses_later_slot_when_room_is_already_used():
    courses = [_course("11111", 40), _course("22222", 40)]
    schedule = Schedule(
        _period(),
        {
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 5),
        },
    )

    assigned = ClassroomAssigner.assign(
        schedule,
        courses,
        ["83101"],
        [Classroom("Room 1", 60)],
        [TimeSlot(time(9, 0)), TimeSlot(time(13, 0))],
        ProctorConfig(20),
    )

    used_slots = {
        items[0].slot.time
        for items in assigned.classroom_assignments.values()
    }
    assert used_slots == {time(9, 0), time(13, 0)}


def test_two_exams_in_same_slot_use_different_rooms():
    courses = [_course("11111", 30), _course("22222", 30)]
    schedule = Schedule(
        _period(),
        {
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 5),
        },
    )

    assigned = ClassroomAssigner.assign(
        schedule,
        courses,
        ["83101"],
        [Classroom("Room 1", 40), Classroom("Room 2", 40)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )

    first = assigned.classroom_assignments["11111"][0]
    second = assigned.classroom_assignments["22222"][0]

    assert first.slot == second.slot == TimeSlot(time(9, 0))
    assert first.room.room_id != second.room.room_id


def test_assigner_rejects_schedule_when_no_slot_has_enough_capacity():
    assigned = ClassroomAssigner.assign(
        Schedule(_period(), {"11111": date(2026, 1, 5)}),
        [_course("11111", 50)],
        ["83101"],
        [Classroom("Room 1", 40)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )

    assert assigned is None


def test_assigner_marks_unassigned_exam_when_user_allows_shortfall():
    assigned = ClassroomAssigner.assign(
        Schedule(_period(), {"11111": date(2026, 1, 5)}),
        [_course("11111", 50)],
        ["83101"],
        [Classroom("Room 1", 40)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
        allow_unassigned=True,
    )

    assert assigned is not None
    assert assigned.classroom_assignments["11111"] == []
    assert assigned.unassigned_classroom_exams == {"11111": 50}


def test_generation_process_returns_enriched_schedules_to_ui_boundary():
    result_queue = Queue()
    course = _course("11111", 30)

    _run_generation_process(
        result_queue,
        [course],
        [_period()],
        ["83101"],
        classrooms=[Classroom("Room 1", 40)],
        time_slots=[TimeSlot(time(9, 0))],
        proctor_config=ProctorConfig(20),
    )

    ok, schedules_by_period, _courses, _truncated = result_queue.get_nowait()
    schedule = schedules_by_period["FALL - Aleph"][0]

    assert ok is True
    assignment = schedule.classroom_assignments["11111"][0]
    assert assignment.room.room_id == "Room 1"
    assert assignment.slot.time == time(9, 0)


def test_generation_process_preserves_unassigned_exam_after_soft_warning():
    result_queue = Queue()

    _run_generation_process(
        result_queue,
        [_course("11111", 50)],
        [_period()],
        ["83101"],
        classrooms=[Classroom("Room 1", 40)],
        time_slots=[TimeSlot(time(9, 0))],
        proctor_config=ProctorConfig(20),
        allow_unassigned_classrooms=True,
    )

    ok, schedules_by_period, _courses, _truncated = result_queue.get_nowait()
    schedule = schedules_by_period["FALL - Aleph"][0]

    assert ok is True
    assert schedule.unassigned_classroom_exams == {"11111": 50}


# ── §5: missing StudentCount on a relevant exam fails clearly ─────────────────

def _course_missing_count(course_id: str, program: str = "83101") -> Course:
    return Course(
        course_id,
        f"Course {course_id}",
        "Dr. Test",
        "Exam",
        [CourseOffering(program, 1, "FALL", "Obligatory", None)],
    )


def test_assigner_raises_on_missing_count_for_relevant_exam():
    """A relevant Exam offering with no StudentCount must fail, not become 0."""
    course = _course_missing_count("11111")
    schedule = Schedule(_period(), {"11111": date(2026, 1, 5)})

    with pytest.raises(ValueError, match="Missing StudentCount"):
        ClassroomAssigner.assign(
            schedule,
            [course],
            ["83101"],
            [Classroom("Room 1", 50)],
            [TimeSlot(time(9, 0))],
            ProctorConfig(20),
        )


def test_assigner_ignores_missing_count_on_non_exam_course():
    project = Course(
        "33333",
        "Final Project",
        "Dr. Test",
        "Project",
        [CourseOffering("83101", 1, "FALL", "Obligatory", None)],
    )
    schedule = Schedule(_period(), {"33333": date(2026, 1, 5)})

    assigned = ClassroomAssigner.assign(
        schedule,
        [project],
        ["83101"],
        [Classroom("Room 1", 50)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )

    assert assigned is not None
    assert "33333" not in assigned.classroom_assignments


def test_assigner_ignores_missing_count_in_unselected_programme():
    """Missing count for a programme the user did not select must not fail."""
    course = _course_missing_count("11111", program="83999")
    schedule = Schedule(_period(), {"11111": date(2026, 1, 5)})

    assigned = ClassroomAssigner.assign(
        schedule,
        [course],
        ["83101"],
        [Classroom("Room 1", 50)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )

    # No relevant offering for the selected programme → nothing to assign.
    assert assigned is not None
    assert "11111" in assigned.classroom_assignments
    assert assigned.classroom_assignments["11111"] == []


# ── §6: StudentCount == 0 skips room assignment (spec 4.3) ────────────────────

def test_assigner_skips_room_assignment_for_zero_student_count():
    """StudentCount of exactly 0 keeps the exam date but assigns no room."""
    course = _course("11111", 0)
    schedule = Schedule(_period(), {"11111": date(2026, 1, 5)})

    assigned = ClassroomAssigner.assign(
        schedule,
        [course],
        ["83101"],
        [Classroom("Room 1", 50)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )

    assert assigned is not None
    assert assigned.classroom_assignments["11111"] == []
    assert "11111" not in assigned.unassigned_classroom_exams


# ── §7: heap-exhaustion path of the balanced distribution (spec 4.4) ──────────

def test_assigner_rejects_when_capacity_is_exactly_one_short():
    """Total capacity below the student count rejects the whole schedule."""
    course = _course("11111", 101)
    schedule = Schedule(_period(), {"11111": date(2026, 1, 5)})

    assigned = ClassroomAssigner.assign(
        schedule,
        [course],
        ["83101"],
        [Classroom("Room 1", 50), Classroom("Room 2", 50)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )

    assert assigned is None


def test_assigner_fills_rooms_to_exact_capacity():
    """When the student count equals total capacity every seat is used once."""
    course = _course("11111", 100)
    schedule = Schedule(_period(), {"11111": date(2026, 1, 5)})

    assigned = ClassroomAssigner.assign(
        schedule,
        [course],
        ["83101"],
        [Classroom("Room 1", 50), Classroom("Room 2", 50)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )

    rooms = assigned.classroom_assignments["11111"]
    assert sum(item.students_assigned for item in rooms) == 100
    assert all(item.students_assigned == item.room.capacity for item in rooms)


# ── §8: unknown course id in the schedule (spec 4.4 rejection) ────────────────

def test_assigner_rejects_schedule_with_unknown_course_when_strict():
    """A course id absent from the catalogue rejects the schedule by default."""
    schedule = Schedule(_period(), {"99999": date(2026, 1, 5)})

    assigned = ClassroomAssigner.assign(
        schedule,
        [],
        ["83101"],
        [Classroom("Room 1", 50)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )

    assert assigned is None


def test_assigner_marks_unknown_course_unassigned_when_allowed():
    """With allow_unassigned the unknown course is recorded, not rejected."""
    schedule = Schedule(_period(), {"99999": date(2026, 1, 5)})

    assigned = ClassroomAssigner.assign(
        schedule,
        [],
        ["83101"],
        [Classroom("Room 1", 50)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
        allow_unassigned=True,
    )

    assert assigned is not None
    assert assigned.unassigned_classroom_exams.get("99999") == 0


# ── §9: balanced-distribution contract and heap-exhaustion guard ──────────────

def test_balanced_distribution_splits_imbalanced_rooms_within_capacity():
    """Uneven room sizes still split evenly without exceeding any capacity."""
    rooms = [Classroom("Big", 50), Classroom("Small", 10)]

    distribution = _balanced_distribution(rooms, 40)

    assert distribution is not None
    placed = dict((room.room_id, count) for room, count in distribution)
    assert sum(placed.values()) == 40
    assert all(count <= room.capacity for room, count in distribution)


def test_balanced_distribution_returns_none_when_capacity_insufficient():
    """Below-capacity input returns None so the caller never records 0 rooms."""
    rooms = [Classroom("Room 1", 20), Classroom("Room 2", 10)]

    assert _balanced_distribution(rooms, 40) is None


def test_assigner_leaves_no_silent_empty_assignment_on_distribution_failure():
    """HIGH fix: a None distribution must not record the course with 0 rooms.

    When no slot can host the exam, the course is either rejected (strict) or
    recorded as unassigned — never silently present with an empty room list.
    """
    course = _course("11111", 40)
    schedule = Schedule(_period(), {"11111": date(2026, 1, 5)})

    rejected = ClassroomAssigner.assign(
        schedule,
        [course],
        ["83101"],
        [Classroom("Room 1", 20), Classroom("Room 2", 10)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )
    assert rejected is None

    allowed = ClassroomAssigner.assign(
        schedule,
        [course],
        ["83101"],
        [Classroom("Room 1", 20), Classroom("Room 2", 10)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
        allow_unassigned=True,
    )
    assert allowed is not None
    assert allowed.classroom_assignments["11111"] == []
    assert allowed.unassigned_classroom_exams == {"11111": 40}


# ── H1: multi-offering exam uses primary (largest) offering as representative ──

def test_assigner_uses_primary_offering_for_multi_offering_course():
    """H1 fix: for a course with multiple offerings, exam field must reference
    the offering with the most students, not always offerings[0]."""
    # Two offerings: small first, large second — so offerings[0] is the small one.
    small_offering = CourseOffering("83101", 1, "FALL", "Obligatory", 10)
    large_offering = CourseOffering("83102", 1, "FALL", "Obligatory", 60)

    course = Course(
        "77777",
        "Multi Program Exam",
        "Dr. Test",
        "Exam",
        [small_offering, large_offering],
    )

    period = ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 5))])
    schedule = Schedule(period, {"77777": date(2026, 1, 5)})

    assigned = ClassroomAssigner.assign(
        schedule,
        [course],
        ["83101", "83102"],
        [Classroom("Room 1", 100)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )

    assert assigned is not None
    rooms = assigned.classroom_assignments["77777"]
    assert len(rooms) == 1
    # The representative offering must be the LARGE one (60 students), not small (10)
    assert rooms[0].exam is large_offering, (
        "Expected primary_offering to be the largest offering, "
        f"but got {rooms[0].exam}"
    )
    assert rooms[0].exam is not small_offering
