from datetime import date

import pytest

from src.adapters.file_data_provider import FileDataProvider


VALID_COURSES = """$$$$
Calculus 1
83112
Dr. Erez Scheiner
83101,1,FALL,Obligatory
83102,1,SPRI,Elective
Exam
$$$$
"""

VALID_PERIODS = """$$$$
FALL, Aleph
29-01-2026, 11-03-2026
- 31-01-2026 Shabat
- 02-03-2026, 04-03-2026 Purim
$$$$
"""

VALID_PROGRAMS = "83101, 83102"


def _write_inputs(
    tmp_path,
    courses_text=VALID_COURSES,
    periods_text=VALID_PERIODS,
    programs_text=VALID_PROGRAMS,
) -> FileDataProvider:
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "periods.txt"
    programs_path = tmp_path / "programs.txt"

    courses_path.write_text(courses_text, encoding="utf-8")
    periods_path.write_text(periods_text, encoding="utf-8")
    programs_path.write_text(programs_text, encoding="utf-8")

    return FileDataProvider(
        courses_path=courses_path,
        periods_path=periods_path,
        programs_path=programs_path,
    )


def test_valid_courses_file_returns_course_and_offerings(tmp_path):
    provider = _write_inputs(tmp_path)

    courses = provider.get_courses()

    assert len(courses) == 1
    course = courses[0]
    assert course.id == "83112"
    assert course.name == "Calculus 1"
    assert course.instructor == "Dr. Erez Scheiner"
    assert course.evaluation_type == "Exam"
    assert len(course.offerings) == 2
    assert course.offerings[0].program_id == "83101"
    assert course.offerings[0].year == 1
    assert course.offerings[0].semester == "FALL"
    assert course.offerings[0].requirement == "Obligatory"


def test_course_record_without_required_lines_raises_value_error(tmp_path):
    provider = _write_inputs(
        tmp_path,
        courses_text="""$$$$
Only Name
12345
$$$$
""",
    )

    with pytest.raises(ValueError, match="at least 4 lines"):
        provider.get_courses()


def test_wrong_date_format_in_exam_periods_raises_value_error(tmp_path):
    provider = _write_inputs(
        tmp_path,
        periods_text="""$$$$
FALL, Aleph
2026-01-29, 11-03-2026
$$$$
""",
    )

    with pytest.raises(ValueError):
        provider.get_exam_periods()


def test_spri_semester_is_normalized_in_course_offering(tmp_path):
    provider = _write_inputs(tmp_path)

    course = provider.get_courses()[0]

    assert course.offerings[1].semester == "SPRI"


def test_selected_programs_with_more_than_five_programs_raises_value_error(tmp_path):
    provider = _write_inputs(
        tmp_path,
        programs_text="83101, 83102, 83103, 83104, 83105, 83106",
    )

    with pytest.raises(ValueError, match="up to 5"):
        provider.get_selected_programs()


def test_selected_programs_with_invalid_id_raises_value_error(tmp_path):
    provider = _write_inputs(tmp_path, programs_text="83101, ABCDE")

    with pytest.raises(ValueError, match="Invalid program id"):
        provider.get_selected_programs()


def test_excluded_date_range_is_parsed_into_excluded_dates(tmp_path):
    provider = _write_inputs(tmp_path)

    period = provider.get_exam_periods()[0]

    assert date(2026, 1, 31) in period.excluded_dates
    assert date(2026, 3, 2) in period.excluded_dates
    assert date(2026, 3, 3) in period.excluded_dates
    assert date(2026, 3, 4) in period.excluded_dates
