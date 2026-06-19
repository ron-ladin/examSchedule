"""Parse a generated schedules.txt file back into Schedule domain objects."""

import re
from dataclasses import dataclass
from datetime import date, time as dt_time
from pathlib import Path

from src.domain.classroom import Classroom
from src.domain.classroom_assignment import ClassroomAssignment
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.domain.time_slot import TimeSlot


@dataclass(frozen=True)
class ImportedScheduleData:
    """Imported schedule data plus course metadata parsed from the file."""

    schedules_by_period: dict[str, list[Schedule]]
    courses_by_id: dict[str, Course]


_SCHEDULE_HEADER = re.compile(r"^Schedule #\d+:\s*$")
_PERIOD_HEADER = re.compile(r"^\s+\[(.+)\]\s*$")

_ENTRY_LINE = re.compile(
    r"^\s+-\s+(?P<name>.*?)\s+\|\s+Course ID:\s+(?P<id>\S+)"
    r"\s+\|\s+Date:\s+(?P<date>\d{2}-\d{2}-\d{4})"
    r"\s+\|\s+Instructor:\s+(?P<instructor>.+?)\s*$"
)

_OFFERING_LINE = re.compile(
    r"^\s+Offering:\s+Program:\s+(?P<program>\S*)"
    r"\s+\|\s+Year:\s+(?P<year>\d+)"
    r"\s+\|\s+Semester:\s+(?P<semester>\S+)"
    r"\s+\|\s+Requirement:\s+(?P<requirement>.+?)"
    r"\s+\|\s+Students:\s+(?P<students>\d*)\s*$"
)

_CLASSROOM_LINE = re.compile(
    r"^\s+Slot:\s+(?P<slot>\d{2}:\d{2})"
    r"\s+\|\s+Room:\s+(?P<room>.+?)"
    r"\s+\|\s+Capacity:\s+(?P<students>\d+)\s*/\s*(?P<capacity>\d+)"
    r"\s+\|\s+Proctors:\s+(?P<proctors>\d+)\s*$"
)

_UNASSIGNED_LINE = re.compile(
    r"^\s+Unassigned classroom students:\s+(?P<count>\d+)\s*$"
)


def _parse_date(text: str) -> date:
    day, month, year = text.split("-")
    return date(int(year), int(month), int(day))


def _parse_time(text: str) -> dt_time:
    hour, minute = text.split(":")
    return dt_time(int(hour), int(minute))


def _parse_optional_int(text: str) -> int | None:
    text = text.strip()
    return int(text) if text else None


def _stub_period(key: str) -> ExamPeriod:
    """Build a minimal ExamPeriod from a period key string like 'FALL - Aleph'."""
    if " - " in key:
        semester, moed = key.split(" - ", 1)
    else:
        semester, moed = key, ""

    return ExamPeriod(
        semester=semester.strip(),
        moed=moed.strip(),
        date_ranges=[],
    )


def _flush(
    result: dict[str, list[Schedule]],
    schedule: Schedule,
    period: str,
) -> None:
    if schedule.assignments:
        result.setdefault(period, []).append(schedule)


def _same_offering(left: CourseOffering, right: CourseOffering) -> bool:
    return (
        left.program_id == right.program_id
        and left.year == right.year
        and left.semester == right.semester
        and left.requirement == right.requirement
        and left.student_count == right.student_count
    )


class ScheduleFileReader:
    """Read a schedules.txt output file into Schedule objects."""

    def read(self, path: Path) -> dict[str, list[Schedule]]:
        """
        Backward-compatible reader.

        Returns only the schedules by period, as before.
        Use read_with_metadata() when the caller also needs course metadata.
        """
        return self.read_with_metadata(path).schedules_by_period

    def read_with_metadata(self, path: Path) -> ImportedScheduleData:
        """
        Read schedules and course metadata from an exported schedules.txt file.

        Supported exported lines:
            - Course Name | Course ID: 12345 | Date: DD-MM-YYYY | Instructor: ...
            Offering: Program: 83108 | Year: 1 | Semester: FALL | Requirement: Obligatory | Students: 80
            Slot: HH:MM | Room: ... | Capacity: students/capacity | Proctors: N
            Unassigned classroom students: N
        """
        lines = Path(path).read_text(encoding="utf-8").splitlines()

        result: dict[str, list[Schedule]] = {}
        courses_by_id: dict[str, Course] = {}

        current_schedule: Schedule | None = None
        current_period: str | None = None
        current_course_id: str | None = None
        current_exam_date: date | None = None
        current_course_offerings: list[CourseOffering] = []

        for line in lines:
            if _SCHEDULE_HEADER.match(line):
                if current_schedule is not None and current_period is not None:
                    _flush(result, current_schedule, current_period)

                current_schedule = None
                current_period = None
                current_course_id = None
                current_exam_date = None
                current_course_offerings = []
                continue

            if current_schedule is None and current_period is None:
                period_match = _PERIOD_HEADER.match(line)
                if period_match:
                    current_period = period_match.group(1).strip()
                    current_schedule = Schedule(period=_stub_period(current_period))
                continue

            if current_schedule is None:
                continue

            period_match = _PERIOD_HEADER.match(line)
            if period_match:
                if current_period is not None:
                    _flush(result, current_schedule, current_period)

                current_period = period_match.group(1).strip()
                current_schedule = Schedule(period=_stub_period(current_period))
                current_course_id = None
                current_exam_date = None
                current_course_offerings = []
                continue

            entry_match = _ENTRY_LINE.match(line)
            if entry_match:
                current_course_id = entry_match.group("id").strip()
                course_name = entry_match.group("name").strip()
                instructor = entry_match.group("instructor").strip()
                current_exam_date = _parse_date(entry_match.group("date"))
                current_course_offerings = []

                current_schedule.assignments[current_course_id] = current_exam_date

                courses_by_id.setdefault(
                    current_course_id,
                    Course(
                        id=current_course_id,
                        name=course_name,
                        instructor=instructor,
                        evaluation_type="Exam",
                        offerings=[],
                    ),
                )
                continue

            offering_match = _OFFERING_LINE.match(line)
            if offering_match and current_course_id is not None:
                offering = CourseOffering(
                    program_id=offering_match.group("program").strip(),
                    year=int(offering_match.group("year")),
                    semester=offering_match.group("semester").strip(),
                    requirement=offering_match.group("requirement").strip(),
                    student_count=_parse_optional_int(offering_match.group("students")),
                )

                course = courses_by_id[current_course_id]
                if not any(_same_offering(existing, offering) for existing in course.offerings):
                    course.offerings.append(offering)

                current_course_offerings.append(offering)
                continue

            classroom_match = _CLASSROOM_LINE.match(line)
            if (
                classroom_match
                and current_course_id is not None
                and current_exam_date is not None
            ):
                students_assigned = int(classroom_match.group("students"))
                room_capacity = int(classroom_match.group("capacity"))
                proctor_count = int(classroom_match.group("proctors"))

                assignment_offering = (
                    current_course_offerings[0]
                    if current_course_offerings
                    else CourseOffering(
                        program_id="",
                        year=0,
                        semester=current_schedule.period.semester,
                        requirement="",
                        student_count=students_assigned,
                    )
                )

                assignment = ClassroomAssignment(
                    exam=assignment_offering,
                    room=Classroom(
                        room_id=classroom_match.group("room").strip(),
                        capacity=room_capacity,
                    ),
                    slot=TimeSlot(_parse_time(classroom_match.group("slot"))),
                    date=current_exam_date,
                    students_assigned=students_assigned,
                    proctor_count=proctor_count,
                )

                current_schedule.classroom_assignments.setdefault(
                    current_course_id,
                    [],
                ).append(assignment)
                continue

            unassigned_match = _UNASSIGNED_LINE.match(line)
            if unassigned_match and current_course_id is not None:
                current_schedule.unassigned_classroom_exams[current_course_id] = int(
                    unassigned_match.group("count")
                )
                continue

        if current_schedule is not None and current_period is not None:
            _flush(result, current_schedule, current_period)

        return ImportedScheduleData(
            schedules_by_period=result,
            courses_by_id=courses_by_id,
        )
