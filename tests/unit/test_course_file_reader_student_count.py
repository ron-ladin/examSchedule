"""
Unit Tests: CourseFileReader StudentCount extension (SCRUM-289, Feature 4 §2.1)
------------------------------------------------------------------------------
Covers only the new optional 5th offering field (StudentCount). Sanity, edge,
negative and boundary checks; uses tmp_path to write a temporary courses file.
"""

import pytest

from src.adapters.readers.course_file_reader import CourseFileReader


# Helper: wrap offering lines in a single valid Exam course record.
def _course_file(tmp_path, *offering_lines):
    body = "\n".join(offering_lines)
    content = f"$$$$\nPhysics 1\n83102\nProf. O. Some\n{body}\nExam\n$$$$"
    path = tmp_path / "courses.txt"
    path.write_text(content, encoding="utf-8")
    return path


def _first_offering(courses):
    return courses[0].offerings[0]


# --- Sanity checks ---------------------------------------------------------

# A 5-field offering line parses the StudentCount.
def test_parses_student_count(tmp_path):
    courses = CourseFileReader(_course_file(tmp_path, "83101, 1, FALL, Obligatory, 80")).read()
    assert _first_offering(courses).student_count == 80


# --- Edge cases ------------------------------------------------------------

# A 4-field line stays backward-compatible: student_count is None.
def test_missing_field_is_none(tmp_path):
    courses = CourseFileReader(_course_file(tmp_path, "83101, 1, FALL, Obligatory")).read()
    assert _first_offering(courses).student_count is None


# StudentCount 0 is valid and distinct from absent (§2.1.5 / §7.5).
def test_zero_student_count_is_valid(tmp_path):
    courses = CourseFileReader(_course_file(tmp_path, "83101, 1, FALL, Obligatory, 0")).read()
    offering = _first_offering(courses)
    assert offering.student_count == 0
    assert offering.student_count is not None


# A course may mix 4-field and 5-field offering lines.
def test_mixed_offering_lines(tmp_path):
    courses = CourseFileReader(
        _course_file(
            tmp_path,
            "83101, 1, FALL, Obligatory, 80",
            "83102, 1, FALL, Obligatory",
        )
    ).read()
    counts = [o.student_count for o in courses[0].offerings]
    assert counts == [80, None]


# --- Negative checks -------------------------------------------------------

# A negative StudentCount is rejected.
def test_rejects_negative_student_count(tmp_path):
    with pytest.raises(ValueError):
        CourseFileReader(_course_file(tmp_path, "83101, 1, FALL, Obligatory, -5")).read()


# A non-integer StudentCount is rejected.
@pytest.mark.parametrize("bad", ["abc", "8.5"])
def test_rejects_non_integer_student_count(tmp_path, bad):
    with pytest.raises(ValueError):
        CourseFileReader(_course_file(tmp_path, f"83101, 1, FALL, Obligatory, {bad}")).read()


# A 6-field offering line is rejected.
def test_rejects_too_many_fields(tmp_path):
    with pytest.raises(ValueError):
        CourseFileReader(_course_file(tmp_path, "83101, 1, FALL, Obligatory, 80, extra")).read()
