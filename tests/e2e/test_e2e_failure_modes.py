"""
E2E Tests: Full Pipeline failure modes.

Each test feeds invalid input (missing/unknown programme, duplicate period,
missing/malformed files) and asserts the run fails without leaving output.
"""

import pytest

from tests.e2e._pipeline_helpers import _build_controller


def test_selected_program_must_exist_in_courses(tmp_path):
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"
    output_path = tmp_path / "schedules.txt"

    courses_path.write_text(
        """X
11111
Dr. A
83101, 1, FALL, Obligatory
Exam
""",
        encoding="utf-8",
    )
    periods_path.write_text(
        """FALL, Aleph
05-01-2026, 06-01-2026
""",
        encoding="utf-8",
    )
    programs_path.write_text("99999", encoding="utf-8")

    controller = _build_controller(courses_path, periods_path, programs_path, output_path)

    with pytest.raises(ValueError):
        controller.run()


def test_duplicate_exam_period_is_rejected(tmp_path):
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"
    output_path = tmp_path / "schedules.txt"

    courses_path.write_text(
        """X
11111
Dr. A
83101, 1, FALL, Obligatory
Exam
""",
        encoding="utf-8",
    )
    periods_path.write_text(
        """FALL, Aleph
05-01-2026, 06-01-2026
$$$$
FALL, Aleph
07-01-2026, 08-01-2026
""",
        encoding="utf-8",
    )
    programs_path.write_text("83101", encoding="utf-8")

    controller = _build_controller(courses_path, periods_path, programs_path, output_path)

    with pytest.raises(ValueError):
        controller.run()


def test_e2e_missing_courses_file_fails_without_creating_output(tmp_path):
    """
    E2E error handling:
    missing input file should fail safely and must not create an output file.
    """
    courses_path = tmp_path / "missing_courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"
    output_path = tmp_path / "schedules.txt"

    periods_path.write_text(
        """FALL, Aleph
05-01-2026, 06-01-2026
""",
        encoding="utf-8",
    )
    programs_path.write_text("83101", encoding="utf-8")

    controller = _build_controller(
        courses_path,
        periods_path,
        programs_path,
        output_path,
    )

    with pytest.raises((FileNotFoundError, ValueError, OSError)):
        controller.run()

    assert not output_path.exists()


def test_e2e_malformed_courses_file_fails_without_creating_output(tmp_path):
    """
    E2E error handling:
    malformed courses input should fail safely and must not create an output file.
    """
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"
    output_path = tmp_path / "schedules.txt"

    courses_path.write_text(
        """Calculus
11111
Dr. Cohen
""",
        encoding="utf-8",
    )
    periods_path.write_text(
        """FALL, Aleph
05-01-2026, 06-01-2026
""",
        encoding="utf-8",
    )
    programs_path.write_text("83101", encoding="utf-8")

    controller = _build_controller(
        courses_path,
        periods_path,
        programs_path,
        output_path,
    )

    with pytest.raises(ValueError):
        controller.run()

    assert not output_path.exists()


def test_e2e_malformed_exam_periods_file_fails_without_creating_output(tmp_path):
    """
    E2E error handling:
    malformed exam-period input should fail safely and must not create output.
    """
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"
    output_path = tmp_path / "schedules.txt"

    courses_path.write_text(
        """Calculus
11111
Dr. Cohen
83101, 1, FALL, Obligatory
Exam
""",
        encoding="utf-8",
    )
    periods_path.write_text(
        """FALL, Aleph
2026-01-05, 2026-01-06
""",
        encoding="utf-8",
    )
    programs_path.write_text("83101", encoding="utf-8")

    controller = _build_controller(
        courses_path,
        periods_path,
        programs_path,
        output_path,
    )

    with pytest.raises(ValueError):
        controller.run()

    assert not output_path.exists()
