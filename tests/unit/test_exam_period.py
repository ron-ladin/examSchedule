"""
Unit Tests: ExamPeriod
-----------------------
Tests for ExamPeriod.get_valid_dates() logic.

Test cases to implement:
    1. Dates within range and not excluded → included in result.
    2. Dates in excluded_dates set         → NOT included in result.
    3. Weekend dates (Friday/Saturday)     → NOT included in result.
    4. Dates outside date_ranges           → NOT included in result.
    5. Excluded date ranges (start, end)   → all dates in range excluded.
    6. Empty date_ranges                   → returns empty list.

Notes:
    - Build ExamPeriod objects directly — no file parsing.
    - Use datetime.date objects for all date comparisons.
    - Import ExamPeriod from src.domain.exam_period.
"""
from datetime import date
from pathlib import Path
import pytest
from datetime import date
from src.domain.exam_period import ExamPeriod
from src.adapters.file_data_provider import FileDataProvider
def write_periods(path: Path):
    path.write_text(
        "FALL,Aleph\n"
        "01-01-2025,31-01-2025\n"
        "- 05-01-2025\n"
        "- 10-01-2025,12-01-2025\n"
        "$$$$\n"
    )
def write_courses(path: Path):
    path.write_text(
        "Course One\n"
        "11111\n"
        "Instructor FALL\n"
        "12345,1,FALL,Obligatory\n"
        "Exam\n"
        "$$$$\n"
    )
def write_programs(path: Path):
    path.write_text("12345")
@pytest.fixture
def provider(tmp_path):
    courses = tmp_path / "courses.txt"
    periods = tmp_path / "periods.txt"
    programs = tmp_path / "programs.txt"
    write_courses(courses)
    write_periods(periods)
    write_programs(programs)
    return FileDataProvider(courses, periods, programs)
def test_get_courses(provider):
    courses = provider.get_courses()
    assert len(courses) == 1
    assert courses[0].id == "11111"
    assert courses[0].offerings[0].program_id == "12345"
def test_get_exam_periods(provider):
    periods = provider.get_exam_periods()
    assert len(periods) == 1
    p = periods[0]
    assert p.semester == "FALL"
    assert p.moed == "Aleph"
    assert p.date_ranges[0] == (date(2025,1,1), date(2025,1,31))
    assert date(2025,1,5) in p.excluded_dates
    assert date(2025,1,11) in p.excluded_dates  # מה-range
def test_get_selected_programs(provider):
    assert provider.get_selected_programs() == ["12345"]
