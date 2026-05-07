"""
Infrastructure Adapter: FileDataProvider
-----------------------------------------
Implements IDataProvider by reading data from text files.

Constructor args:
    - courses_path  (Path) : path to courses file
    - periods_path  (Path) : path to exam periods file
    - programs_path (Path) : path to selected programs file

Methods to implement:

    get_courses() -> List[Course]
        Parses courses file ($$$$-separated records).
        Each record structure:
            $$$$
            <Course Name>
            <5-digit Course ID>
            <Instructor Name>
            <program_id>,<year>,<semester>,<requirement>  ← one or more lines
            <Evaluation>
        Keeps semester values in the same format as the input files:
        "FALL", "SPRI", or "SUMM".
        Returns a list of Course objects with their offerings populated.

    get_exam_periods() -> List[ExamPeriod]
        Parses exam periods file ($$$$-separated records).
        Each record structure:
            $$$$
            <Semester>,<Moed>
            <StartDate>, <EndDate>
            <ExcludedDate or Range> <Optional Comment>
        Uses datetime.strptime() with format "%d-%m-%Y" for all date parsing.
        Excluded entries may be a single date or a "start, end comment" range.

    get_selected_programs() -> List[str]
        Parses selected programs file (comma-separated 5-digit IDs on one line).
        Validates that each entry is exactly 5 digits.
        Raises ValueError if count > 5 or any entry is not a valid program ID.

Notes:
    - Use pathlib.Path for all file access — never os.path.
    - Use logging for warnings (e.g., skipped records) — no print().
    - All parsing logic belongs here, not in domain classes.
"""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Tuple

import logging

from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.interfaces.i_data_provider import IDataProvider


logger = logging.getLogger(__name__)


class FileDataProvider(IDataProvider):
    MAX_SELECTED_PROGRAMS = 5
    DATE_FORMAT = "%d-%m-%Y"

    def __init__(
        self,
        courses_path: Path,
        periods_path: Path,
        programs_path: Path,
    ):
        self.courses_path = Path(courses_path)
        self.periods_path = Path(periods_path)
        self.programs_path = Path(programs_path)

    def get_courses(self) -> List[Course]:
        records = self._read_records(self.courses_path)
        courses: List[Course] = []

        for record in records:
            try:
                courses.append(self._parse_course_record(record))
            except ValueError as error:
                logger.warning("Skipping invalid course record %s: %s", record, error)

        return courses

    def get_exam_periods(self) -> List[ExamPeriod]:
        records = self._read_records(self.periods_path)
        periods: List[ExamPeriod] = []

        for record in records:
            try:
                periods.append(self._parse_exam_period_record(record))
            except ValueError as error:
                logger.warning("Skipping invalid exam period record %s: %s", record, error)

        return periods

    def get_selected_programs(self) -> List[str]:
        content = self.programs_path.read_text(encoding="utf-8").strip()

        programs = [
            item.strip()
            for item in content.split(",")
            if item.strip()
        ]

        if len(programs) > self.MAX_SELECTED_PROGRAMS:
            raise ValueError("You can select up to 5 programs only.")

        for program_id in programs:
            if not self._is_valid_program_id(program_id):
                raise ValueError(f"Invalid program id: {program_id}")

        return programs

    def _read_records(self, file_path: Path) -> List[List[str]]:
        content = file_path.read_text(encoding="utf-8")
        raw_records = content.split("$$$$")

        records: List[List[str]] = []

        for raw_record in raw_records:
            lines = [
                line.strip()
                for line in raw_record.splitlines()
                if line.strip()
            ]

            if lines:
                records.append(lines)

        return records

    def _parse_course_record(self, record: List[str]) -> Course:
        if len(record) < 4:
            raise ValueError("Course record must contain at least 4 lines.")

        course_name = record[0]
        course_id = record[1]
        instructor = record[2]
        evaluation_type = record[-1]

        if not self._is_valid_course_id(course_id):
            raise ValueError(f"Invalid course id: {course_id}")

        if evaluation_type not in {"Exam", "Project", "Attendance"}:
            raise ValueError(f"Invalid evaluation type: {evaluation_type}")

        course = Course(
            id=course_id,
            name=course_name,
            instructor=instructor,
            evaluation_type=evaluation_type,
        )

        offering_lines = record[3:-1]

        for line in offering_lines:
            course.add_offering(self._parse_course_offering(line))

        return course

    def _parse_course_offering(self, line: str) -> CourseOffering:
        parts = [
            part.strip()
            for part in line.split(",")
        ]

        if len(parts) != 4:
            raise ValueError(f"Invalid course offering line: {line}")

        program_id, year_text, semester, requirement = parts

        if not self._is_valid_program_id(program_id):
            raise ValueError(f"Invalid program id in offering: {program_id}")

        if not year_text.isdigit():
            raise ValueError(f"Invalid year in offering: {year_text}")

        year = int(year_text)

        if year not in {1, 2, 3, 4}:
            raise ValueError(f"Year must be one of 1, 2, 3, 4: {year}")

        if semester not in {"FALL", "SPRI", "SUMM"}:
            raise ValueError(f"Invalid semester: {semester}")

        if requirement not in {"Obligatory", "Elective"}:
            raise ValueError(f"Invalid requirement: {requirement}")

        return CourseOffering(
            program_id=program_id,
            year=year,
            semester=semester,
            requirement=requirement,
        )

    def _parse_exam_period_record(self, record: List[str]) -> ExamPeriod:
        if len(record) < 2:
            raise ValueError("Exam period record must contain at least 2 lines.")

        semester, moed = self._parse_period_header(record[0])
        start_date, end_date = self._parse_date_range(record[1])

        excluded_dates: List[date] = []

        for line in record[2:]:
            excluded_dates.extend(self._parse_excluded_dates(line))

        return ExamPeriod(
            semester=semester,
            moed=moed,
            date_ranges=[(start_date, end_date)],
            excluded_dates=excluded_dates,
        )

    def _parse_period_header(self, line: str) -> Tuple[str, str]:
        parts = [
            part.strip()
            for part in line.split(",")
        ]

        if len(parts) != 2:
            raise ValueError(f"Invalid exam period header: {line}")

        semester, moed = parts

        if semester not in {"FALL", "SPRI", "SUMM"}:
            raise ValueError(f"Invalid semester in exam period: {semester}")

        if moed not in {"Aleph", "Bet", "Gimel"}:
            raise ValueError(f"Invalid moed: {moed}")

        return semester, moed

    def _parse_excluded_dates(self, line: str) -> List[date]:
        clean_line = line.strip()

        if clean_line.startswith("-"):
            clean_line = clean_line[1:].strip()

        if not clean_line:
            return []

        if "," in clean_line:
            start_date, end_date = self._parse_date_range(clean_line)
            return self._build_date_list(start_date, end_date)

        first_token = clean_line.split()[0]
        return [self._parse_date(first_token)]

    def _parse_date_range(self, line: str) -> Tuple[date, date]:
        parts = [
            part.strip()
            for part in line.split(",")
        ]

        if len(parts) != 2:
            raise ValueError(f"Invalid date range: {line}")

        start_date = self._parse_date(parts[0])

        end_token = parts[1].split()[0]
        end_date = self._parse_date(end_token)

        if start_date > end_date:
            raise ValueError(f"Start date must be before or equal to end date: {line}")

        return start_date, end_date

    def _parse_date(self, value: str) -> date:
        return datetime.strptime(value, self.DATE_FORMAT).date()

    def _build_date_list(self, start_date: date, end_date: date) -> List[date]:
        dates: List[date] = []
        current_date = start_date

        while current_date <= end_date:
            dates.append(current_date)
            current_date += timedelta(days=1)

        return dates

    def _is_valid_program_id(self, program_id: str) -> bool:
        return len(program_id) == 5 and program_id.isdigit()

    def _is_valid_course_id(self, course_id: str) -> bool:
        return len(course_id) == 5 and course_id.isdigit()