"""
Unit Tests: Feature 4 Domain Extensions (Story 2.1 — SCRUM-285..288)
--------------------------------------------------------------------
Covers the new/extended domain models: CourseOffering.student_count,
Classroom, TimeSlot, and ClassroomAssignment. A few checks of each kind:
sanity, edge, negative, boundary. Pure unit tests — no file I/O.
"""

from dataclasses import FrozenInstanceError
from datetime import date, time

import pytest

from src.domain.classroom import Classroom
from src.domain.classroom_assignment import ClassroomAssignment
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.feature4_validator import Feature4Validator
from src.domain.time_slot import TimeSlot


# --- SCRUM-285: CourseOffering.student_count -------------------------------

# student_count defaults to None so existing call sites stay backward-compatible.
def test_student_count_defaults_to_none():
    offering = CourseOffering("83101", 1, "FALL", "Obligatory")
    assert offering.student_count is None


# A student_count can be attached to an offering.
def test_student_count_can_be_set():
    offering = CourseOffering("83101", 1, "FALL", "Obligatory", student_count=80)
    assert offering.student_count == 80


# student_count == 0 is a valid value, distinct from absent/None (spec 2.1.5).
def test_student_count_zero_is_distinct_from_none():
    offering = CourseOffering("83101", 1, "FALL", "Obligatory", student_count=0)
    assert offering.student_count == 0
    assert offering.student_count is not None


# A negative student_count is rejected.
def test_student_count_rejects_negative():
    with pytest.raises(ValueError):
        CourseOffering("83101", 1, "FALL", "Obligatory", student_count=-5)


# --- SCRUM-286: Classroom --------------------------------------------------

# A valid classroom keeps its room id and capacity.
def test_classroom_holds_fields():
    room = Classroom(room_id="A-101", capacity=50)
    assert room.room_id == "A-101"
    assert room.capacity == 50


# Capacity must be a positive integer (spec 2.2.4).
def test_classroom_rejects_zero_capacity():
    with pytest.raises(ValueError):
        Classroom(room_id="A-101", capacity=0)


def test_classroom_rejects_negative_capacity():
    with pytest.raises(ValueError):
        Classroom(room_id="A-101", capacity=-5)


# bool is a subclass of int, but True is not a valid capacity.
def test_classroom_rejects_bool_capacity():
    with pytest.raises(ValueError):
        Classroom(room_id="A-101", capacity=True)


# An empty room id is rejected.
def test_classroom_rejects_empty_room_id():
    with pytest.raises(ValueError):
        Classroom(room_id="   ", capacity=50)


# A non-string room id (e.g. None) yields a clean ValueError, not AttributeError.
def test_classroom_rejects_non_string_room_id():
    with pytest.raises(ValueError):
        Classroom(room_id=None, capacity=50)  # type: ignore[arg-type]


# The classroom is immutable.
def test_classroom_is_immutable():
    room = Classroom(room_id="A-101", capacity=50)
    with pytest.raises(FrozenInstanceError):
        room.capacity = 99


# --- SCRUM-287: TimeSlot ---------------------------------------------------

# A TimeSlot holds a single time point.
def test_time_slot_holds_time():
    slot = TimeSlot(time(9, 0))
    assert slot.time == time(9, 0)


# A time with sub-minute precision is rejected (slots are HH:MM, spec 2.3).
def test_time_slot_rejects_non_whole_minute():
    with pytest.raises(ValueError):
        TimeSlot(time(3, 0, 15))


# A valid ascending sequence with >= 4h gaps passes.
def test_validate_sequence_accepts_valid_slots():
    slots = [TimeSlot(time(9, 0)), TimeSlot(time(13, 0)), TimeSlot(time(19, 0))]
    TimeSlot.validate_sequence(slots)  # should not raise


# Exactly 4 hours apart is allowed (boundary).
def test_validate_sequence_accepts_exact_four_hour_gap():
    TimeSlot.validate_sequence([TimeSlot(time(9, 0)), TimeSlot(time(13, 0))])


# A gap smaller than 4 hours is rejected.
def test_validate_sequence_rejects_small_gap():
    with pytest.raises(ValueError):
        TimeSlot.validate_sequence([TimeSlot(time(9, 0)), TimeSlot(time(11, 0))])


# A non-ascending sequence is rejected.
def test_validate_sequence_rejects_descending():
    with pytest.raises(ValueError):
        TimeSlot.validate_sequence([TimeSlot(time(13, 0)), TimeSlot(time(9, 0))])


# An out-of-order slot in the middle is reported as an ordering error.
def test_validate_sequence_rejects_unsorted_middle():
    slots = [TimeSlot(time(9, 0)), TimeSlot(time(6, 0)), TimeSlot(time(13, 0))]
    with pytest.raises(ValueError, match="ascending"):
        TimeSlot.validate_sequence(slots)


# More than 3 slots per day is rejected (spec 2.3.3).
def test_validate_sequence_rejects_more_than_three_slots():
    slots = [
        TimeSlot(time(6, 0)),
        TimeSlot(time(10, 0)),
        TimeSlot(time(14, 0)),
        TimeSlot(time(18, 0)),
    ]
    with pytest.raises(ValueError):
        TimeSlot.validate_sequence(slots)


# Empty and single-slot sequences are trivially valid.
def test_validate_sequence_allows_empty_and_single():
    TimeSlot.validate_sequence([])
    TimeSlot.validate_sequence([TimeSlot(time(9, 0))])


# --- SCRUM-288: ClassroomAssignment ----------------------------------------

# An assignment carries the exam, room, slot, date, students, and proctor count.
def test_classroom_assignment_holds_fields():
    offering = CourseOffering("83101", 1, "FALL", "Obligatory", student_count=80)
    room = Classroom(room_id="A-101", capacity=120)
    slot = TimeSlot(time(9, 0))
    assignment = ClassroomAssignment(
        exam=offering,
        room=room,
        slot=slot,
        date=date(2026, 6, 1),
        students_assigned=80,
        proctor_count=4,
    )

    assert assignment.exam is offering
    assert assignment.room is room
    assert assignment.slot is slot
    assert assignment.date == date(2026, 6, 1)
    assert assignment.students_assigned == 80
    assert assignment.proctor_count == 4


# students_assigned may equal usable capacity (boundary) but not exceed it.
def test_classroom_assignment_allows_full_usable_room():
    ClassroomAssignment(
        exam=CourseOffering("83101", 1, "FALL", "Obligatory"),
        room=Classroom(room_id="A-101", capacity=100),
        slot=TimeSlot(time(9, 0)),
        date=date(2026, 6, 1),
        students_assigned=75,
        proctor_count=4,
    )


def test_classroom_assignment_rejects_overfilled_usable_room():
    with pytest.raises(ValueError):
        ClassroomAssignment(
            exam=CourseOffering("83101", 1, "FALL", "Obligatory"),
            room=Classroom(room_id="A-101", capacity=50),
            slot=TimeSlot(time(9, 0)),
            date=date(2026, 6, 1),
            students_assigned=51,
            proctor_count=3,
        )


# A negative student count is rejected.
def test_classroom_assignment_rejects_negative_students():
    with pytest.raises(ValueError):
        ClassroomAssignment(
            exam=CourseOffering("83101", 1, "FALL", "Obligatory"),
            room=Classroom(room_id="A-101", capacity=50),
            slot=TimeSlot(time(9, 0)),
            date=date(2026, 6, 1),
            students_assigned=-1,
            proctor_count=1,
        )


# A negative proctor count is rejected.
def test_classroom_assignment_rejects_negative_proctor_count():
    with pytest.raises(ValueError):
        ClassroomAssignment(
            exam=CourseOffering("83101", 1, "FALL", "Obligatory"),
            room=Classroom(room_id="A-101", capacity=50),
            slot=TimeSlot(time(9, 0)),
            date=date(2026, 6, 1),
            students_assigned=10,
            proctor_count=-1,
        )


# bool is a subclass of int, but is not a valid count for either field.
def test_classroom_assignment_rejects_bool_students():
    with pytest.raises(ValueError):
        ClassroomAssignment(
            exam=CourseOffering("83101", 1, "FALL", "Obligatory"),
            room=Classroom(room_id="A-101", capacity=50),
            slot=TimeSlot(time(9, 0)),
            date=date(2026, 6, 1),
            students_assigned=True,
            proctor_count=1,
        )


def test_classroom_assignment_rejects_bool_proctor_count():
    with pytest.raises(ValueError):
        ClassroomAssignment(
            exam=CourseOffering("83101", 1, "FALL", "Obligatory"),
            room=Classroom(room_id="A-101", capacity=50),
            slot=TimeSlot(time(9, 0)),
            date=date(2026, 6, 1),
            students_assigned=10,
            proctor_count=True,
        )


# The assignment is immutable.
def test_classroom_assignment_is_immutable():
    assignment = ClassroomAssignment(
        exam=CourseOffering("83101", 1, "FALL", "Obligatory"),
        room=Classroom(room_id="A-101", capacity=100),
        slot=TimeSlot(time(9, 0)),
        date=date(2026, 6, 1),
        students_assigned=20,
        proctor_count=2,
    )
    with pytest.raises(FrozenInstanceError):
        assignment.proctor_count = 3


# --- SCRUM-390: Feature4Validator.unplaceable_exams ------------------------
# Pre-flight analytics: list every exam whose single-session student count
# structurally exceeds the combined usable capacity of all rooms, so the engine
# can route only those exams through the unassigned fallback instead of blanking
# the whole solution space.


def _exam(course_id, name, *offerings):
    """Build an Exam course from (program_id, year, semester, requirement, count)."""
    return Course(
        id=course_id,
        name=name,
        instructor="Dr. Test",
        evaluation_type="Exam",
        offerings=[CourseOffering(*o) for o in offerings],
    )


# An exam larger than the combined usable capacity is flagged with full detail.
def test_unplaceable_exams_flags_oversized_exam():
    rooms = [Classroom("A-1", 40), Classroom("A-2", 60)]  # usable 30 + 45 = 75
    courses = [_exam("10004", "Advanced Materials", ("83109", 3, "FALL", "Obligatory", 400))]

    result = Feature4Validator.unplaceable_exams(courses, rooms)

    assert len(result) == 1
    entry = result[0]
    assert entry.course_id == "10004"
    assert entry.name == "Advanced Materials"
    assert entry.student_count == 400
    assert entry.max_usable_capacity == 75
    # DTO is also tuple-compatible (course_id, name, student_count, max_usable_capacity).
    assert tuple(entry) == ("10004", "Advanced Materials", 400, 75)


# When every exam fits within combined usable capacity, nothing is flagged.
def test_unplaceable_exams_empty_when_capacity_suffices():
    rooms = [Classroom("A-1", 40), Classroom("A-2", 60)]  # usable 75
    courses = [_exam("100", "Small Exam", ("83101", 1, "FALL", "Obligatory", 50))]

    assert Feature4Validator.unplaceable_exams(courses, rooms) == []


# Boundary: an exam exactly equal to combined usable capacity IS placeable
# (the check is a strict ">").
def test_unplaceable_exams_boundary_equal_capacity_is_placeable():
    rooms = [Classroom("A-1", 40), Classroom("A-2", 60)]  # usable 75
    courses = [_exam("100", "Exactly Fits", ("83101", 1, "FALL", "Obligatory", 75))]

    assert Feature4Validator.unplaceable_exams(courses, rooms) == []


# Non-exam courses (Project/Attendance) never need rooms and are never flagged.
def test_unplaceable_exams_ignores_non_exam_courses():
    rooms = [Classroom("A-1", 40)]  # usable 30
    project = Course(
        id="200",
        name="Huge Project",
        instructor="Dr. Test",
        evaluation_type="Project",
        offerings=[CourseOffering("83101", 1, "FALL", "Obligatory", 9999)],
    )

    assert Feature4Validator.unplaceable_exams([project], rooms) == []


# Offerings of the same exam in the same semester are one session: their counts
# are summed (worst case across programmes) before the capacity comparison.
def test_unplaceable_exams_sums_offerings_in_same_semester():
    rooms = [Classroom("A-1", 40), Classroom("A-2", 60)]  # usable 75
    courses = [
        _exam(
            "300",
            "Two Programmes",
            ("83101", 1, "FALL", "Obligatory", 40),
            ("83102", 1, "FALL", "Obligatory", 40),
        )
    ]

    result = Feature4Validator.unplaceable_exams(courses, rooms)

    assert len(result) == 1
    assert result[0].student_count == 80
    assert result[0].max_usable_capacity == 75


# Different semesters are distinct sessions and must NOT be summed together.
def test_unplaceable_exams_does_not_sum_across_semesters():
    rooms = [Classroom("A-1", 40), Classroom("A-2", 60)]  # usable 75
    courses = [
        _exam(
            "400",
            "Fall And Spring",
            ("83101", 1, "FALL", "Obligatory", 60),
            ("83101", 1, "SPRI", "Obligatory", 60),
        )
    ]

    # 60 (FALL) and 60 (SPRI) are each <= 75; summing would wrongly flag 120.
    assert Feature4Validator.unplaceable_exams(courses, rooms) == []


# A missing StudentCount contributes zero to the structural pre-flight total
# (the strict per-offering count rule is enforced later, at assignment time).
def test_unplaceable_exams_treats_missing_count_as_zero():
    rooms = [Classroom("A-1", 40)]  # usable 30
    courses = [_exam("500", "No Count", ("83101", 1, "FALL", "Obligatory"))]

    assert Feature4Validator.unplaceable_exams(courses, rooms) == []
