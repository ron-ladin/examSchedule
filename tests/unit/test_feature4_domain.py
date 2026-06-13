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
from src.domain.course_offering import CourseOffering
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
    room = Classroom(room_id="A-101", capacity=100)
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


# students_assigned may equal capacity (boundary) but not exceed it (spec 6.2.4).
def test_classroom_assignment_allows_full_room():
    ClassroomAssignment(
        exam=CourseOffering("83101", 1, "FALL", "Obligatory"),
        room=Classroom(room_id="A-101", capacity=50),
        slot=TimeSlot(time(9, 0)),
        date=date(2026, 6, 1),
        students_assigned=50,
        proctor_count=3,
    )


def test_classroom_assignment_rejects_overfilled_room():
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
