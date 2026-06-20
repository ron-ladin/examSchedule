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
from src.domain.semester import normalize_semester
from src.domain.time_slot import TimeSlot


class EmptyScheduleImportError(ValueError):
    """Raised when an imported file parses cleanly but contains no schedules.

    Subclasses ValueError so existing ValueError handlers still catch it, while
    callers that want to distinguish "empty" from "malformed" can catch it first.
    """


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


def _normalize_period_key(raw: str) -> str:
    """Convert a display period key like 'SPRING - Aleph' to internal 'SPRI - Aleph'."""
    if " - " in raw:
        semester_part, moed_part = raw.split(" - ", 1)
        try:
            return f"{normalize_semester(semester_part.strip())} - {moed_part.strip()}"
        except ValueError:
            pass
    return raw


def _offering_fingerprint(offering: CourseOffering) -> tuple:
    return (
        offering.program_id,
        offering.year,
        offering.semester,
        offering.requirement,
        offering.student_count,
    )


def _schedule_fingerprint(schedule: Schedule, period: str) -> tuple:
    """Uniquely identify a period schedule by its full content.

    Exported combined schedules are Cartesian products of per-period schedules,
    so the same period schedule is written across many ``Schedule #N`` blocks.
    Fingerprinting by period + assignments + classroom assignments + unassigned
    exams lets the reader keep only the first occurrence of each distinct
    per-period schedule.
    """
    assignments = tuple(
        sorted((cid, d.isoformat()) for cid, d in schedule.assignments.items())
    )
    classrooms = tuple(
        (
            cid,
            tuple(
                (
                    a.room.room_id,
                    a.slot.time.isoformat(),
                    a.date.isoformat(),
                    a.students_assigned,
                    a.proctor_count,
                )
                for a in assigns
            ),
        )
        for cid, assigns in sorted(schedule.classroom_assignments.items())
    )
    unassigned = tuple(sorted(schedule.unassigned_classroom_exams.items()))
    return (period, assignments, classrooms, unassigned)


def _flush(
    result: dict[str, list[Schedule]],
    schedule: Schedule,
    period: str,
    seen: set[tuple],
) -> None:
    if not schedule.assignments:
        return

    fingerprint = _schedule_fingerprint(schedule, period)
    if fingerprint in seen:
        return

    seen.add(fingerprint)
    result.setdefault(period, []).append(schedule)


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
        seen_offerings: dict[str, set[tuple]] = {}
        seen_schedules: set[tuple] = set()

        current_schedule: Schedule | None = None
        current_period: str | None = None
        current_course_id: str | None = None
        current_exam_date: date | None = None
        current_course_offerings: list[CourseOffering] = []

        for line in lines:
            if _SCHEDULE_HEADER.match(line):
                if current_schedule is not None and current_period is not None:
                    _flush(result, current_schedule, current_period, seen_schedules)

                current_schedule = None
                current_period = None
                current_course_id = None
                current_exam_date = None
                current_course_offerings = []
                continue

            if current_schedule is None and current_period is None:
                period_match = _PERIOD_HEADER.match(line)
                if period_match:
                    current_period = _normalize_period_key(period_match.group(1).strip())
                    current_schedule = Schedule(period=_stub_period(current_period))
                continue

            if current_schedule is None:
                continue

            period_match = _PERIOD_HEADER.match(line)
            if period_match:
                if current_period is not None:
                    _flush(result, current_schedule, current_period, seen_schedules)

                current_period = _normalize_period_key(period_match.group(1).strip())
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

                fingerprint = _offering_fingerprint(offering)
                course_seen = seen_offerings.setdefault(current_course_id, set())
                if fingerprint not in course_seen:
                    courses_by_id[current_course_id].offerings.append(offering)
                    course_seen.add(fingerprint)

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
            _flush(result, current_schedule, current_period, seen_schedules)

        return ImportedScheduleData(
            schedules_by_period=result,
            courses_by_id=courses_by_id,
        )
