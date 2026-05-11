"""
Unit Tests: FileDataProvider
------------------------------
Tests for parsing logic in FileDataProvider.

Test cases to implement:
    1. Valid courses.txt → correct Course and CourseOffering objects returned.
    2. Missing $$$$ separator in courses.txt → raises appropriate error or skips record.
    3. Wrong date format in exam_periods.txt → raises ValueError.
    4. "SPRI" in semester field → mapped to "SPRING" in CourseOffering.
    5. selected_programs.txt with > 5 programs → raises ValueError.
    6. selected_programs.txt with non-5-digit entry → raises ValueError.
    7. Excluded date range in exam_periods.txt → parsed into excluded_dates set correctly.

Notes:
    - Use tmp_path pytest fixture to create temporary input files.
    - Write minimal valid file content as strings in each test.
    - Import FileDataProvider from src.adapters.file_data_provider.
"""
from pathlib import Path
from datetime import date
import pytest
from src.adapters.file_data_provider import FileDataProvider
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
def write_courses_file(path: Path):
    path.write_text(
        "Calculus\n"
        "11111\n"
        "Dr. Cohen\n"
        "12345,1,FALL,Obligatory\n"
        "Exam\n"
        "$$$$\n"
        "History\n"
        "22222\n"
        "Dr. Levi\n"
        "54321,2,SPRI,Elective\n"
        "Exam\n"
        "$$$$\n"
    )
def write_exam_period_file(path: Path):
    path.write_text(
        "FALL,Aleph\n"
        "01-01-2025,31-01-2025\n"
        "- 05-01-2025\n"
        "- 10-01-2025,12-01-2025\n"
        "$$$$\n"
    )
def write_programs_file(path: Path):
    path.write_text("12345,54321")
@pytest.fixture
def provider(tmp_path):
    courses_file = tmp_path / "courses.txt"
    periods_file = tmp_path / "exam_periods.txt"
    programs_file = tmp_path / "selected_programs.txt"
    write_courses_file(courses_file)
    write_exam_period_file(periods_file)
    write_programs_file(programs_file)
    return FileDataProvider(courses_file, periods_file, programs_file)
def test_get_courses(provider):
    courses = provider.get_courses()
    assert len(courses) == 2
    assert courses[0].id == "11111"
    assert courses[0].name == "Calculus"
    assert isinstance(courses[0].offerings[0], CourseOffering)
def test_get_exam_periods(provider):
    periods = provider.get_exam_periods()
    assert len(periods) == 1
    p = periods[0]
    assert p.semester == "FALL"
    assert p.moed == "Aleph"
    assert p.date_ranges[0][0] == date(2025, 1, 1)
    assert p.date_ranges[0][1] == date(2025, 1, 31)
    assert date(2025, 1, 5) in p.excluded_dates
def test_get_selected_programs(provider):
    programs = provider.get_selected_programs()
    assert programs == ["12345", "54321"]