"""Feature 4 classroom assignment and pipeline integration tests."""

from datetime import date, time
from queue import Queue

from src.controller import _run_generation_process
from src.domain.classroom import Classroom
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.proctor import ProctorConfig
from src.domain.schedule import Schedule
from src.domain.time_slot import TimeSlot
from src.engine.classroom_assigner import ClassroomAssigner


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
        item.students_assigned <= int(item.room.capacity * 0.75)
        for item in rooms
    )


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
