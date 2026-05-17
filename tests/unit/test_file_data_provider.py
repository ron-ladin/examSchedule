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
from datetime import date

import pytest

from src.adapters.file_data_provider import FileDataProvider

# This is a helper function that creates three temporary text files 
    # (courses.txt, dates.txt, programs.txt) filled with correct mock data to use in the tests.
def _write_valid_files(tmp_path):
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"

    courses_path.write_text(
        """Calculus
11111
Dr. Cohen
83101, 1, SPRI, Obligatory
Exam
$$$$
Algorithms
22222
Dr. Levi
83102, 2, FALL, Elective
Exam
""",
        encoding="utf-8",
    )
    periods_path.write_text(
        """SPRI, Aleph
01-03-2026, 05-03-2026
- 03-03-2026, 04-03-2026
$$$$
FALL, Bet
05-01-2026, 07-01-2026
""",
        encoding="utf-8",
    )
    programs_path.write_text("83101,83102", encoding="utf-8")

    return courses_path, periods_path, programs_path

#  This tests the main success path. It makes sure that when given properly formatted files,
    # the provider reads them and converts them into correct Python objects with correct values.
def test_file_data_provider_loads_courses_periods_and_programs(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    provider = FileDataProvider(courses_path, periods_path, programs_path)

    courses = provider.get_courses()
    periods = provider.get_exam_periods()
    selected_programs = provider.get_selected_programs()

# Verify that IDs, semesters, excluded ranges, and programs match the files exactly
    assert [course.id for course in courses] == ["11111", "22222"]
    assert courses[0].offerings[0].semester == "SPRI"
    assert periods[0].semester == "SPRI"
    assert date(2026, 3, 3) in periods[0].excluded_dates
    assert date(2026, 3, 4) in periods[0].excluded_dates
    assert selected_programs == ["83101", "83102"]

#  This tests data validation. If a course record is missing rows (malformed),
    # the system must protect itself by raising a ValueError instead of parsing bad data.
def test_course_reader_rejects_malformed_course_record(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    courses_path.write_text("Calculus\n11111\nDr. Cohen\n", encoding="utf-8")
    provider = FileDataProvider(courses_path, periods_path, programs_path)

    with pytest.raises(ValueError):
        provider.get_courses()

#  This checks date validation. The system expects DD-MM-YYYY format. 
    # If the file uses YYY-MM-DD instead, it should catch the mistake and raise a ValueError.
def test_exam_period_reader_rejects_wrong_date_format(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    periods_path.write_text(
        """FALL, Aleph
2026-01-05, 2026-01-07
""",
        encoding="utf-8",
    )
    provider = FileDataProvider(courses_path, periods_path, programs_path)

    with pytest.raises(ValueError):
        provider.get_exam_periods()

#  This checks a business limit constraint. The system allows a maximum of 5 active programs.
    # If the file contains 6 programs, it violates the rule and must throw a ValueError.
def test_program_reader_rejects_more_than_five_programs(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    programs_path.write_text("11111,22222,33333,44444,55555,66666", encoding="utf-8")
    provider = FileDataProvider(courses_path, periods_path, programs_path)

    with pytest.raises(ValueError):
        provider.get_selected_programs()

#  This checks string format rules. Academic program codes must be numbers and exactly 5 digits.
    # If a program code contains text letters like "ABC", it is invalid and triggers a ValueError.
def test_program_reader_rejects_non_five_digit_program(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    programs_path.write_text("83101,ABC", encoding="utf-8")
    provider = FileDataProvider(courses_path, periods_path, programs_path)

    with pytest.raises(ValueError):
        provider.get_selected_programs()


# A course with several offerings must produce multiple CourseOffering objects
def test_course_with_multiple_offerings(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    courses_path.write_text(
        """Physics
11111
Prof. Newton
83101, 1, FALL, Obligatory
83102, 1, FALL, Obligatory
83108, 2, FALL, Elective
Exam
""",
        encoding="utf-8",
    )
    provider = FileDataProvider(courses_path, periods_path, programs_path)
    courses = provider.get_courses()

    assert len(courses) == 1
    assert len(courses[0].offerings) == 3


# 4-digit course id must be rejected — protects against typos in source data
def test_course_reader_rejects_invalid_course_id(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    courses_path.write_text(
        """Calculus
1234
Dr. Cohen
83101, 1, FALL, Obligatory
Exam
""",
        encoding="utf-8",
    )
    provider = FileDataProvider(courses_path, periods_path, programs_path)

    with pytest.raises(ValueError):
        provider.get_courses()


# Duplicate course IDs across records must be caught
def test_course_reader_rejects_duplicate_course_ids(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    courses_path.write_text(
        """Calculus
11111
Dr. Cohen
83101, 1, FALL, Obligatory
Exam
$$$$
Algebra
11111
Dr. Levi
83101, 1, FALL, Obligatory
Exam
""",
        encoding="utf-8",
    )
    provider = FileDataProvider(courses_path, periods_path, programs_path)

    with pytest.raises(ValueError):
        provider.get_courses()


# Invalid evaluation type must be rejected
def test_course_reader_rejects_invalid_evaluation_type(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    courses_path.write_text(
        """Calculus
11111
Dr. Cohen
83101, 1, FALL, Obligatory
Quiz
""",
        encoding="utf-8",
    )
    provider = FileDataProvider(courses_path, periods_path, programs_path)

    with pytest.raises(ValueError):
        provider.get_courses()


# Invalid requirement type must be rejected
def test_course_reader_rejects_invalid_requirement(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    courses_path.write_text(
        """Calculus
11111
Dr. Cohen
83101, 1, FALL, Mandatory
Exam
""",
        encoding="utf-8",
    )
    provider = FileDataProvider(courses_path, periods_path, programs_path)

    with pytest.raises(ValueError):
        provider.get_courses()


# Year out of range must be rejected (only 1-4 valid)
def test_course_reader_rejects_invalid_year(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    courses_path.write_text(
        """Calculus
11111
Dr. Cohen
83101, 7, FALL, Obligatory
Exam
""",
        encoding="utf-8",
    )
    provider = FileDataProvider(courses_path, periods_path, programs_path)

    with pytest.raises(ValueError):
        provider.get_courses()


# The aliases "SPRING" and "SUMMER" should be stored normalized as "SPRI"/"SUMM"
def test_spring_alias_normalized_to_spri(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    courses_path.write_text(
        """Lab
11111
Dr. T
83101, 1, SPRING, Obligatory
Exam
""",
        encoding="utf-8",
    )
    provider = FileDataProvider(courses_path, periods_path, programs_path)
    courses = provider.get_courses()
    assert courses[0].offerings[0].semester == "SPRI"


# Period with reversed dates (end before start) must be rejected
def test_exam_period_reader_rejects_reversed_date_range(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    periods_path.write_text(
        """FALL, Aleph
07-01-2026, 05-01-2026
""",
        encoding="utf-8",
    )
    provider = FileDataProvider(courses_path, periods_path, programs_path)

    with pytest.raises(ValueError):
        provider.get_exam_periods()


# Invalid moed must be rejected
def test_exam_period_reader_rejects_invalid_moed(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    periods_path.write_text(
        """FALL, NotAMoed
05-01-2026, 07-01-2026
""",
        encoding="utf-8",
    )
    provider = FileDataProvider(courses_path, periods_path, programs_path)

    with pytest.raises(ValueError):
        provider.get_exam_periods()


# Single excluded date (not a range) must be parsed correctly
def test_exam_period_reader_parses_single_excluded_date(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    periods_path.write_text(
        """FALL, Aleph
05-01-2026, 09-01-2026
- 07-01-2026
""",
        encoding="utf-8",
    )
    provider = FileDataProvider(courses_path, periods_path, programs_path)
    periods = provider.get_exam_periods()

    assert date(2026, 1, 7) in periods[0].excluded_dates
    assert date(2026, 1, 5) not in periods[0].excluded_dates


# Empty programs file must be rejected
def test_program_reader_rejects_empty_programs(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    programs_path.write_text("", encoding="utf-8")
    provider = FileDataProvider(courses_path, periods_path, programs_path)

    with pytest.raises(ValueError):
        provider.get_selected_programs()


# Duplicate program IDs must be rejected
def test_program_reader_rejects_duplicate_programs(tmp_path):
    courses_path, periods_path, programs_path = _write_valid_files(tmp_path)
    programs_path.write_text("83101,83101", encoding="utf-8")
    provider = FileDataProvider(courses_path, periods_path, programs_path)

    with pytest.raises(ValueError):
        provider.get_selected_programs()