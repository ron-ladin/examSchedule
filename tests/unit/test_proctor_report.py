"""Tests for the spec 4.6 proctor report builder and controller wiring."""

from datetime import date, time

from src.domain.classroom import Classroom
from src.domain.classroom_assignment import ClassroomAssignment
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.domain.time_slot import TimeSlot
from src.engine.proctor_report import build_proctor_report


def _period() -> ExamPeriod:
    return ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 9))])


def _offering() -> CourseOffering:
    return CourseOffering("83101", 1, "FALL", "Obligatory", 35)


def _courses() -> dict[str, Course]:
    return {
        "11111": Course("11111", "Physics 1", "Dr. A", "Exam", [_offering()]),
        "22222": Course("22222", "Calculus 1", "Dr. B", "Exam", [_offering()]),
    }


def test_report_follows_spec_structure():
    # Arrange
    room = Classroom("Room 201", 40)
    assignment = ClassroomAssignment(
        exam=_offering(),
        room=room,
        slot=TimeSlot(time(9, 0)),
        date=date(2026, 1, 5),
        students_assigned=35,
        proctor_count=2,
    )
    schedule = Schedule(
        _period(),
        {"11111": date(2026, 1, 5)},
        {"11111": [assignment]},
    )

    # Act
    report = build_proctor_report(schedule, _courses())

    # Assert
    assert "05-01-2026" in report
    assert "  09:00" in report
    assert "    Physics 1 (11111)" in report
    assert "      Room 201: 35/40 | Proctors: 2" in report


def test_report_orders_dates_and_slots_chronologically():
    early = ClassroomAssignment(
        exam=_offering(),
        room=Classroom("Room 201", 40),
        slot=TimeSlot(time(9, 0)),
        date=date(2026, 1, 5),
        students_assigned=35,
        proctor_count=2,
    )
    late = ClassroomAssignment(
        exam=_offering(),
        room=Classroom("Room 202", 60),
        slot=TimeSlot(time(13, 0)),
        date=date(2026, 1, 5),
        students_assigned=35,
        proctor_count=2,
    )
    schedule = Schedule(
        _period(),
        {"11111": date(2026, 1, 5), "22222": date(2026, 1, 5)},
        {"11111": [late], "22222": [early]},
    )

    report = build_proctor_report(schedule, _courses())

    assert report.index("09:00") < report.index("13:00")


def test_report_for_schedule_without_assignments():
    schedule = Schedule(_period(), {"11111": date(2026, 1, 5)})

    report = build_proctor_report(schedule, _courses())

    assert report == "No room assignments for this schedule."
