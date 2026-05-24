"""
Reader: CourseFileReader
-------------------------
Reads the courses file and converts each course record into a Course object.

Responsible only for:
    - Reading CourseDB.txt
    - Parsing course records
    - Creating Course and CourseOffering objects
    - Validating course-related input
"""

from pathlib import Path
from typing import List

from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.semester import normalize_semester


class CourseFileReader:
    VALID_REQUIREMENTS = {
        "obligatory": "Obligatory",
        "elective": "Elective",
    }

    VALID_EVALUATIONS = {
        "exam": "Exam",
        "project": "Project",
        "attendance": "Attendance",
    }

    VALID_YEARS = {1, 2, 3, 4}

    def __init__(self, courses_path: Path):
        self.courses_path = Path(courses_path)

    def read(self) -> List[Course]:
        records = self._read_records()
        courses: List[Course] = []

        for record in records:
            courses.append(self._parse_course_record(record))

        self._validate_unique_course_ids(courses)

        return courses

    def _validate_unique_course_ids(self, courses: List[Course]) -> None:
        seen_ids = set()

        for course in courses:
            if course.id in seen_ids:
                raise ValueError(f"Duplicate course id found: {course.id}")
            seen_ids.add(course.id)

    def _read_records(self) -> List[List[str]]:
        content = self.courses_path.read_text(encoding="utf-8")
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

        if not records:
            raise ValueError(f"No course records found in file: {self.courses_path}")

        return records

    def _parse_course_record(self, record: List[str]) -> Course:
        if len(record) < 5:
            raise ValueError(f"Course record must contain at least 5 lines: {record}")

        course_name = record[0]
        course_id = record[1]
        instructor = record[2]
        evaluation_type = self._normalize_evaluation_type(record[-1])

        if not self._is_valid_course_id(course_id):
            raise ValueError(f"Invalid course id: {course_id}")

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

        if year not in self.VALID_YEARS:
            raise ValueError(f"Year must be one of 1, 2, 3, 4: {year}")

        semester = normalize_semester(semester)
        requirement = self._normalize_requirement(requirement)

        return CourseOffering(
            program_id=program_id,
            year=year,
            semester=semester,
            requirement=requirement,
        )

    def _normalize_requirement(self, requirement: str) -> str:
        key = requirement.strip().lower()

        if key not in self.VALID_REQUIREMENTS:
            raise ValueError(f"Invalid requirement: {requirement}")

        return self.VALID_REQUIREMENTS[key]

    def _normalize_evaluation_type(self, evaluation_type: str) -> str:
        key = evaluation_type.strip().lower()

        if key not in self.VALID_EVALUATIONS:
            raise ValueError(f"Invalid evaluation type: {evaluation_type}")

        return self.VALID_EVALUATIONS[key]

    def _is_valid_program_id(self, program_id: str) -> bool:
        return len(program_id) == 5 and program_id.isdigit()

    def _is_valid_course_id(self, course_id: str) -> bool:
        return len(course_id) == 5 and course_id.isdigit()
