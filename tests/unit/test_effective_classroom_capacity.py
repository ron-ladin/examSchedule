"""Unit tests for effective classroom capacity policy.

These tests verify that Feature 4 uses the configured
EXAM_ROOM_CAPACITY_RATIO instead of raw physical room capacity.
"""

from datetime import date, time

import pytest

import src.domain.classroom as classroom_module
from src.domain.classroom import Classroom
from src.domain.classroom_assignment import ClassroomAssignment
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.feature4_validator import Feature4Validator
from src.domain.proctor import ProctorConfig
from src.domain.schedule import Schedule
from src.domain.time_slot import TimeSlot
from src.engine.classroom_assigner import ClassroomAssigner, _balanced_distribution


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


def test_classroom_usable_capacity_uses_configured_ratio():
    room = Classroom("Room 1", 100)

    expected = int(room.capacity * classroom_module.EXAM_ROOM_CAPACITY_RATIO)

    assert room.usable_capacity == expected


@pytest.mark.parametrize("ratio", [1.0, 0.75, 0.5])
def test_classroom_usable_capacity_changes_when_ratio_changes(monkeypatch, ratio):
    monkeypatch.setattr(classroom_module, "EXAM_ROOM_CAPACITY_RATIO", ratio)

    room = Classroom("Room 1", 100)

    assert room.usable_capacity == int(100 * ratio)


@pytest.mark.parametrize("ratio", [1.0, 0.75, 0.5])
def test_classroom_assignment_allows_up_to_usable_capacity(monkeypatch, ratio):
    monkeypatch.setattr(classroom_module, "EXAM_ROOM_CAPACITY_RATIO", ratio)

    room = Classroom("Room 1", 100)
    allowed_students = room.usable_capacity

    assignment = ClassroomAssignment(
        exam=CourseOffering("83101", 1, "FALL", "Obligatory", allowed_students),
        room=room,
        slot=TimeSlot(time(9, 0)),
        date=date(2026, 1, 5),
        students_assigned=allowed_students,
        proctor_count=1,
    )

    assert assignment.students_assigned == allowed_students


@pytest.mark.parametrize("ratio", [0.75, 0.5])
def test_classroom_assignment_rejects_above_usable_capacity(monkeypatch, ratio):
    monkeypatch.setattr(classroom_module, "EXAM_ROOM_CAPACITY_RATIO", ratio)

    room = Classroom("Room 1", 100)

    with pytest.raises(ValueError, match="usable capacity"):
        ClassroomAssignment(
            exam=CourseOffering("83101", 1, "FALL", "Obligatory"),
            room=room,
            slot=TimeSlot(time(9, 0)),
            date=date(2026, 1, 5),
            students_assigned=room.usable_capacity + 1,
            proctor_count=1,
        )


@pytest.mark.parametrize("ratio", [1.0, 0.75, 0.5])
def test_balanced_distribution_never_exceeds_usable_capacity(monkeypatch, ratio):
    monkeypatch.setattr(classroom_module, "EXAM_ROOM_CAPACITY_RATIO", ratio)

    rooms = [Classroom("Room 1", 100), Classroom("Room 2", 100)]
    student_count = rooms[0].usable_capacity + 1

    distribution = _balanced_distribution(rooms, student_count)

    assert distribution is not None
    assert sum(placed for _room, placed in distribution) == student_count
    assert all(placed <= room.usable_capacity for room, placed in distribution)


@pytest.mark.parametrize("ratio", [0.75, 0.5])
def test_balanced_distribution_rejects_single_room_above_usable_capacity(
    monkeypatch,
    ratio,
):
    monkeypatch.setattr(classroom_module, "EXAM_ROOM_CAPACITY_RATIO", ratio)

    room = Classroom("Room 1", 100)

    distribution = _balanced_distribution([room], room.usable_capacity + 1)

    assert distribution is None


@pytest.mark.parametrize("ratio", [1.0, 0.75, 0.5])
def test_assigner_respects_configured_usable_capacity(monkeypatch, ratio):
    monkeypatch.setattr(classroom_module, "EXAM_ROOM_CAPACITY_RATIO", ratio)

    rooms = [Classroom("Room 1", 100), Classroom("Room 2", 100)]
    student_count = rooms[0].usable_capacity + 1
    course = _course("11111", student_count)
    schedule = Schedule(_period(), {"11111": date(2026, 1, 5)})

    assigned = ClassroomAssigner.assign(
        schedule,
        [course],
        ["83101"],
        rooms,
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )

    assert assigned is not None
    assignments = assigned.classroom_assignments["11111"]

    assert sum(item.students_assigned for item in assignments) == student_count
    assert all(
        item.students_assigned <= item.room.usable_capacity
        for item in assignments
    )


@pytest.mark.parametrize("ratio", [0.75, 0.5])
def test_assigner_rejects_when_total_usable_capacity_is_insufficient(
    monkeypatch,
    ratio,
):
    monkeypatch.setattr(classroom_module, "EXAM_ROOM_CAPACITY_RATIO", ratio)

    room = Classroom("Room 1", 100)
    course = _course("11111", room.usable_capacity + 1)
    schedule = Schedule(_period(), {"11111": date(2026, 1, 5)})

    assigned = ClassroomAssigner.assign(
        schedule,
        [course],
        ["83101"],
        [room],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )

    assert assigned is None


@pytest.mark.parametrize("ratio", [1.0, 0.75, 0.5])
def test_feature4_validator_capacity_shortfall_uses_same_usable_capacity(
    monkeypatch,
    ratio,
):
    monkeypatch.setattr(classroom_module, "EXAM_ROOM_CAPACITY_RATIO", ratio)

    room = Classroom("Room 1", 100)
    largest_exam = room.usable_capacity + 1

    result = Feature4Validator.capacity_shortfall(
        courses=[_course("11111", largest_exam)],
        selected_programs=["83101"],
        exam_periods=[_period()],
        classrooms=[room],
        is_active=True,
    )

    assert result == (room.usable_capacity, largest_exam)
