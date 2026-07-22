"""Feature 4 classroom assignment and pipeline integration tests."""

from datetime import date, time
from queue import Queue

import pytest

import src.domain.classroom as classroom_module
from src.controller import _run_generation_process
from src.domain.classroom import Classroom
from src.domain.classroom_assignment import ClassroomAssignment
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.proctor import ProctorConfig
from src.domain.schedule import Schedule
from src.domain.time_slot import TimeSlot
from src.engine.classroom_assigner import (
    ClassroomAssigner,
    _balanced_distribution,
    _room_combinations_by_capacity,
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


def _set_occupancy(monkeypatch: pytest.MonkeyPatch, ratio: float) -> None:
    """Set the exam-room occupancy ratio for the duration of one test.

    Supports both implementations used in this branch: the newer float ratio
    constant and the older numerator/denominator constants.
    """
    if hasattr(classroom_module, "EXAM_ROOM_CAPACITY_RATIO"):
        monkeypatch.setattr(classroom_module, "EXAM_ROOM_CAPACITY_RATIO", ratio)
        return

    monkeypatch.setattr(
        classroom_module,
        "EXAM_ROOM_CAPACITY_NUMERATOR",
        int(ratio * 100),
    )
    monkeypatch.setattr(classroom_module, "EXAM_ROOM_CAPACITY_DENOMINATOR", 100)


@pytest.mark.parametrize(
    ("ratio", "expected_capacity"),
    [
        (1.0, 100),
        (0.75, 75),
        (0.50, 50),
    ],
)
def test_classroom_usable_capacity_follows_configured_occupancy(
    monkeypatch: pytest.MonkeyPatch,
    ratio: float,
    expected_capacity: int,
):
    """Effective capacity is floor(capacity * occupancy_ratio)."""
    _set_occupancy(monkeypatch, ratio)

    assert Classroom("Room 1", 100).usable_capacity == expected_capacity


@pytest.mark.parametrize(
    ("ratio", "student_count"),
    [
        (1.0, 100),
        (0.75, 75),
        (0.50, 50),
    ],
)
def test_assigner_allows_students_up_to_configured_usable_capacity(
    monkeypatch: pytest.MonkeyPatch,
    ratio: float,
    student_count: int,
):
    """A room may be filled up to, but not beyond, its usable capacity."""
    _set_occupancy(monkeypatch, ratio)
    course = _course("11111", student_count)
    schedule = Schedule(_period(), {"11111": date(2026, 1, 5)})

    assigned = ClassroomAssigner.assign(
        schedule,
        [course],
        ["83101"],
        [Classroom("Room 1", 100)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )

    assert assigned is not None
    rooms = assigned.classroom_assignments["11111"]
    assert len(rooms) == 1
    assert rooms[0].students_assigned == student_count
    assert rooms[0].students_assigned <= rooms[0].room.usable_capacity


@pytest.mark.parametrize(
    ("ratio", "student_count"),
    [
        (1.0, 101),
        (0.75, 76),
        (0.50, 51),
    ],
)
def test_assigner_rejects_students_above_configured_usable_capacity(
    monkeypatch: pytest.MonkeyPatch,
    ratio: float,
    student_count: int,
):
    """One room with capacity 100 rejects one student above its usable capacity."""
    _set_occupancy(monkeypatch, ratio)
    course = _course("11111", student_count)
    schedule = Schedule(_period(), {"11111": date(2026, 1, 5)})

    assigned = ClassroomAssigner.assign(
        schedule,
        [course],
        ["83101"],
        [Classroom("Room 1", 100)],
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
    )

    assert assigned is None


def test_classroom_assignment_rejects_students_above_usable_capacity(
    monkeypatch: pytest.MonkeyPatch,
):
    """The domain object also enforces the effective-capacity invariant."""
    _set_occupancy(monkeypatch, 0.75)

    with pytest.raises(ValueError, match="usable capacity"):
        ClassroomAssignment(
            exam=CourseOffering("83101", 1, "FALL", "Obligatory", 76),
            room=Classroom("Room 1", 100),
            slot=TimeSlot(time(9, 0)),
            date=date(2026, 1, 5),
            students_assigned=76,
            proctor_count=4,
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
        item.students_assigned <= item.room.usable_capacity
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

    result = result_queue.get_nowait()
    schedules_by_period = result.schedules_by_period
    schedule = schedules_by_period["FALL - Aleph"][0]

    assert result.success is True
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

    result = result_queue.get_nowait()
    schedules_by_period = result.schedules_by_period
    schedule = schedules_by_period["FALL - Aleph"][0]

    assert result.success is True
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

def test_assigner_rejects_when_usable_capacity_is_exactly_one_short():
    """Total usable capacity below the student count rejects the whole schedule."""
    course = _course("11111", 75)
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


def test_assigner_fills_rooms_to_exact_usable_capacity():
    """When the student count equals total usable capacity every allowed seat is used."""
    course = _course("11111", 74)
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
    assert sum(item.students_assigned for item in rooms) == 74
    assert all(item.students_assigned == item.room.usable_capacity for item in rooms)


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
    """Uneven room sizes still split evenly without exceeding usable capacity."""
    rooms = [Classroom("Big", 50), Classroom("Small", 10)]

    distribution = _balanced_distribution(rooms, 40)

    assert distribution is not None
    placed = dict((room.room_id, count) for room, count in distribution)
    assert sum(placed.values()) == 40
    assert all(count <= room.usable_capacity for room, count in distribution)


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


# ── Large classroom variant generation must stay lazy ────────────────────────

def _variant_signature(schedule: Schedule) -> tuple:
    return tuple(
        (
            course_id,
            tuple(
                (assignment.room.room_id, assignment.students_assigned, assignment.slot.time)
                for assignment in assignments
            ),
        )
        for course_id, assignments in sorted(schedule.classroom_assignments.items())
    )


def test_assign_variants_samples_large_classroom_file_lazily(monkeypatch):
    """Regression: many rooms must not force all classroom combinations up front."""
    _set_occupancy(monkeypatch, 1.0)
    course = _course("11111", 2)
    schedule = Schedule(_period(), {"11111": date(2026, 1, 5)})
    rooms = [Classroom(f"Room {index:04d}", 1) for index in range(1000)]

    variants = []
    iterator = ClassroomAssigner.assign_variants(
        schedule,
        [course],
        ["83101"],
        rooms,
        [TimeSlot(time(9, 0))],
        ProctorConfig(20),
        max_options_per_day=None,
        max_options_per_schedule=None,
    )
    for _ in range(25):
        variants.append(next(iterator))

    assert len(variants) == 25
    assert len({_variant_signature(variant) for variant in variants}) == 25
    assert all(
        sum(
            assignment.students_assigned
            for assignment in variant.classroom_assignments["11111"]
        ) == 2
        for variant in variants
    )


def test_assign_variants_defaults_bound_large_room_variant_enumeration(monkeypatch):
    """SCRUM-454: default variant generation must cap day and schedule output."""
    _set_occupancy(monkeypatch, 1.0)
    rooms = [Classroom(f"Room {index:02d}", 1) for index in range(50)]
    slots = [TimeSlot(time(9, 0))]
    proctors = ProctorConfig(20)

    one_day_period = ExamPeriod(
        "FALL",
        "Aleph",
        [(date(2026, 1, 5), date(2026, 1, 5))],
    )
    one_day_course = _course("11111", 20)
    one_day_schedule = Schedule(one_day_period, {"11111": date(2026, 1, 5)})

    one_day_variants = list(
        ClassroomAssigner.assign_variants(
            one_day_schedule,
            [one_day_course],
            ["83101"],
            rooms,
            slots,
            proctors,
        )
    )

    assert len(one_day_variants) <= 20

    multi_day_period = ExamPeriod(
        "FALL",
        "Aleph",
        [(date(2026, 1, 5), date(2026, 1, 7))],
    )
    multi_day_courses = [
        _course("11111", 20),
        _course("22222", 20),
        _course("33333", 20),
    ]
    multi_day_schedule = Schedule(
        multi_day_period,
        {
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 6),
            "33333": date(2026, 1, 7),
        },
    )

    schedule_variants = list(
        ClassroomAssigner.assign_variants(
            multi_day_schedule,
            multi_day_courses,
            ["83101"],
            rooms,
            slots,
            proctors,
        )
    )

    assert len(schedule_variants) <= 500


def test_stateful_variant_worker_continues_next_block_without_rebuild(monkeypatch):
    """Auto Variants block 2 should continue from block 1, not restart + skip."""
    _set_occupancy(monkeypatch, 1.0)
    import src.engine.generation_workers as generation_workers

    course = _course("11111", 2)
    schedule = Schedule(_period(), {"11111": date(2026, 1, 5)})
    rooms = [Classroom(f"Room {index}", 1) for index in range(10)]
    states: dict[tuple, dict] = {}
    build_calls = 0
    original_builder = generation_workers._build_variant_iterator

    def counting_builder(*args, **kwargs):
        nonlocal build_calls
        build_calls += 1
        return original_builder(*args, **kwargs)

    monkeypatch.setattr(
        generation_workers,
        "_build_variant_iterator",
        counting_builder,
    )

    first_queue = Queue()
    generation_workers._run_classroom_variants_from_state(
        first_queue,
        states,
        "FALL - Aleph",
        schedule,
        [course],
        ["83101"],
        cap=3,
        offset=0,
        classrooms=rooms,
        time_slots=[TimeSlot(time(9, 0))],
        proctor_config=ProctorConfig(20),
    )
    first = first_queue.get_nowait()

    second_queue = Queue()
    generation_workers._run_classroom_variants_from_state(
        second_queue,
        states,
        "FALL - Aleph",
        schedule,
        [course],
        ["83101"],
        cap=3,
        offset=3,
        classrooms=rooms,
        time_slots=[TimeSlot(time(9, 0))],
        proctor_config=ProctorConfig(20),
    )
    second = second_queue.get_nowait()

    first_batch = first.schedules_by_period["FALL - Aleph"]
    second_batch = second.schedules_by_period["FALL - Aleph"]

    assert first.success is True
    assert second.success is True
    assert build_calls == 1
    assert len(first_batch) == 3
    assert len(second_batch) == 3
    assert {
        _variant_signature(variant)
        for variant in first_batch
    }.isdisjoint({_variant_signature(variant) for variant in second_batch})


def test_large_exam_that_requires_many_rooms_does_not_recurse_forever(monkeypatch):
    """Regression: 1,000 tiny rooms must not crash variant generation."""
    _set_occupancy(monkeypatch, 1.0)
    rooms = [Classroom(f"Room {index:04d}", 1) for index in range(1000)]
    course = _course("99999", 999)
    schedule = Schedule(_period(), {"99999": date(2026, 1, 5)})

    variants = list(
        ClassroomAssigner.assign_variants(
            schedule,
            [course],
            ["83101"],
            rooms,
            [TimeSlot(time(9, 0))],
            ProctorConfig(20),
            max_options_per_schedule=2,
        )
    )

    assert len(variants) == 1
    assert len(variants[0].classroom_assignments["99999"]) == 999


def test_room_combinations_sort_rooms_defensively_for_capacity_pruning(monkeypatch):
    """Unsorted rooms must not break capacity-pruned combination generation."""
    _set_occupancy(monkeypatch, 1.0)
    rooms = [
        Classroom("Small", 10),
        Classroom("Large", 90),
        Classroom("Medium", 20),
    ]

    combinations = list(
        _room_combinations_by_capacity(
            rooms,
            size=2,
            student_count=100,
        )
    )

    assert combinations
    assert any(
        {room.room_id for room in combo} == {"Large", "Small"}
        for combo in combinations
    )


def test_stateful_variant_worker_logs_and_self_heals_stale_offset(caplog, monkeypatch):
    """A stale pagination offset must rebuild safely instead of crashing."""
    _set_occupancy(monkeypatch, 1.0)
    import logging
    import src.engine.generation_workers as generation_workers

    course = _course("11111", 2)
    schedule = Schedule(_period(), {"11111": date(2026, 1, 5)})
    rooms = [Classroom(f"Room {index}", 1) for index in range(10)]
    states: dict[tuple, dict] = {}

    first_queue = Queue()
    generation_workers._run_classroom_variants_from_state(
        first_queue,
        states,
        "FALL - Aleph",
        schedule,
        [course],
        ["83101"],
        cap=3,
        offset=0,
        classrooms=rooms,
        time_slots=[TimeSlot(time(9, 0))],
        proctor_config=ProctorConfig(20),
    )
    first = first_queue.get_nowait()
    assert first.success is True

    caplog.set_level(logging.WARNING, logger="src.engine.generation_workers")

    second_queue = Queue()
    generation_workers._run_classroom_variants_from_state(
        second_queue,
        states,
        "FALL - Aleph",
        schedule,
        [course],
        ["83101"],
        cap=2,
        offset=4,
        classrooms=rooms,
        time_slots=[TimeSlot(time(9, 0))],
        proctor_config=ProctorConfig(20),
    )
    second = second_queue.get_nowait()

    assert second.success is True
    assert "Stale classroom variant pagination state detected" in caplog.text
    assert second.schedules_by_period["FALL - Aleph"]
