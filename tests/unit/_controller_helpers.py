"""
Shared fixtures/builders for DesktopController unit tests.

File-writing helpers mirror test_file_data_provider.py patterns; controller
builders assemble in-memory Feature 4 state without touching disk.
"""

from datetime import date, time
from pathlib import Path

from src.controller import DesktopController
from src.domain.classroom import Classroom
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.proctor import ProctorConfig
from src.domain.time_slot import TimeSlot


def _write_courses(path: Path, extra: str = "") -> None:
    path.write_text(
        f"""Calculus
11111
Dr. Cohen
83101, 1, FALL, Obligatory
Exam
$$$$
Algorithms
22222
Dr. Levi
83102, 2, FALL, Elective
Exam
{extra}""",
        encoding="utf-8",
    )


def _write_periods(path: Path) -> None:
    path.write_text(
        """FALL, Aleph
05-01-2026, 09-01-2026
""",
        encoding="utf-8",
    )


def _write_programs(path: Path, content: str = "83101,83102") -> None:
    path.write_text(content, encoding="utf-8")


def _fall_period() -> ExamPeriod:
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 9))],
    )


def _active_feature4_controller(total_capacity: int, student_count: int) -> DesktopController:
    ctrl = DesktopController()
    ctrl._feature4_enabled = True
    ctrl._classrooms = [Classroom("Room 1", total_capacity)]
    ctrl._time_slots = [TimeSlot(time(9, 0))]
    ctrl._proctor_config = ProctorConfig(20)
    # Selected programmes + a loaded period define which offerings are "relevant"
    # for the spec 4.3/4.4 pre-generation checks.
    ctrl._selected_programs = ["83101", "83102"]
    ctrl._exam_periods = [_fall_period()]
    ctrl._courses = [
        Course(
            id="11111",
            name="Calculus",
            instructor="Dr. Cohen",
            evaluation_type="Exam",
            offerings=[
                CourseOffering("83101", 1, "FALL", "Obligatory", student_count)
            ],
        )
    ]
    return ctrl


def _exam_course(student_count, program="83101", course_id="11111"):
    return Course(
        id=course_id,
        name="Calculus",
        instructor="Dr. Cohen",
        evaluation_type="Exam",
        offerings=[CourseOffering(program, 1, "FALL", "Obligatory", student_count)],
    )
