"""
E2E Tests: Full user flow through DesktopController.

Covers the happy path (load -> select -> generate -> export) and the
full-generation behaviour that supersedes the old Load More flow
(SCRUM-172 / 179 / 180 / 181).
"""

from src.controller import DesktopController


def test_desktop_controller_happy_path_load_generate_export(tmp_path):
    """
    E2E happy path for the desktop controller flow:
    load files -> select programmes -> generate schedules -> export result.
    """
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    output_path = tmp_path / "desktop_schedules.txt"

    courses_path.write_text(
        """Calculus
11111
Dr. Cohen
83101, 1, FALL, Obligatory
Exam
$$$$
Algorithms
22222
Dr. Levi
83101, 1, FALL, Obligatory
Exam
$$$$
Project Lab
33333
Dr. Katz
83101, 1, FALL, Obligatory
Project
""",
        encoding="utf-8",
    )

    periods_path.write_text(
        """FALL, Aleph
05-01-2026, 06-01-2026
""",
        encoding="utf-8",
    )

    controller = DesktopController()

    course_count = controller.load_courses(courses_path)
    period_count = controller.load_periods(periods_path)
    controller.set_selected_programs(["83101"])

    schedules_by_period, _courses_by_id, truncated = controller.generate()

    assert course_count == 3
    assert period_count == 1
    assert truncated == set()
    assert "FALL - Aleph" in schedules_by_period
    assert len(schedules_by_period["FALL - Aleph"]) == 2

    controller.export(schedules_by_period, output_path)

    content = output_path.read_text(encoding="utf-8")

    assert output_path.exists()
    assert "Schedule #1:" in content
    assert "[FALL - Aleph]" in content
    assert "Calculus" in content
    assert "Algorithms" in content
    assert "Project Lab" not in content
    assert "Course ID: 11111" in content
    assert "Course ID: 22222" in content


def test_desktop_full_generation_replaces_load_more_flow(tmp_path):
    """
    The original task described a Load More flow after RESULT_CAP.

    Current desktop behavior generates all schedules up front. Therefore this
    E2E test verifies the updated behavior:
    - all schedules are returned in one generation call,
    - no period is marked as truncated,
    - no Load More state remains active after generation.
    """
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"

    courses_path.write_text(
        """Calculus
11111
Dr. Cohen
83101, 1, FALL, Obligatory
Exam
$$$$
Algorithms
22222
Dr. Levi
83101, 1, FALL, Obligatory
Exam
$$$$
Physics
33333
Dr. Bar
83101, 1, FALL, Obligatory
Exam
""",
        encoding="utf-8",
    )

    periods_path.write_text(
        """FALL, Aleph
05-01-2026, 31-01-2026
""",
        encoding="utf-8",
    )

    controller = DesktopController()
    controller.load_courses(courses_path)
    controller.load_periods(periods_path)
    controller.set_selected_programs(["83101"])

    schedules_by_period, _courses_by_id, truncated = controller.generate()

    period_key = "FALL - Aleph"
    period = controller.get_exam_periods()[0]
    valid_dates_count = len(period.get_valid_dates())

    expected_count = (
        valid_dates_count
        * (valid_dates_count - 1)
        * (valid_dates_count - 2)
    )

    assert valid_dates_count == 23
    assert truncated == set()
    assert period_key in schedules_by_period
    assert len(schedules_by_period[period_key]) == expected_count

    assert controller.has_more_schedules(period_key) is False
    assert controller.has_any_more_schedules() is False
    assert controller.load_more_schedules(period_key) == []
