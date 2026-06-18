"""
E2E Tests: Full Pipeline on synthetic inputs.

Small hand-built inputs assert exact output size and schedule correctness,
including Project-course exclusion, period ordering, and date exclusions
(SCRUM-195). Uses the AppController file path via _build_controller.
"""

from datetime import date

from tests.e2e._pipeline_helpers import _build_controller, _parse_output_schedules


def test_full_pipeline_creates_non_empty_output_file(tmp_path):
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
    programs_path.write_text("83101", encoding="utf-8")

    _build_controller(courses_path, periods_path, programs_path, output_path).run()

    content = output_path.read_text(encoding="utf-8")
    assert output_path.exists()
    assert content.strip()
    assert "Schedule #1:" in content
    assert "[FALL - Aleph]" in content
    assert "Calculus" in content
    assert "Algorithms" in content
    assert "Project Lab" not in content


def test_pipeline_overwrites_output_file_on_rerun(tmp_path):
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
    programs_path.write_text("83101", encoding="utf-8")

    _build_controller(courses_path, periods_path, programs_path, output_path).run()
    first_content = output_path.read_text(encoding="utf-8")

    _build_controller(courses_path, periods_path, programs_path, output_path).run()
    second_content = output_path.read_text(encoding="utf-8")

    assert first_content == second_content
    assert second_content.count("Schedule #1:") == 1


def test_periods_are_sorted_in_output(tmp_path):
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"
    output_path = tmp_path / "schedules.txt"

    courses_path.write_text(
        """FallX
11111
Dr. A
83101, 1, FALL, Obligatory
Exam
$$$$
SpringX
22222
Dr. B
83101, 1, SPRI, Obligatory
Exam
""",
        encoding="utf-8",
    )
    periods_path.write_text(
        """SPRI, Aleph
05-03-2026, 06-03-2026
$$$$
FALL, Bet
10-02-2026, 11-02-2026
$$$$
FALL, Aleph
05-01-2026, 06-01-2026
""",
        encoding="utf-8",
    )
    programs_path.write_text("83101", encoding="utf-8")

    _build_controller(courses_path, periods_path, programs_path, output_path).run()
    content = output_path.read_text(encoding="utf-8")

    fall_aleph_idx = content.find("[FALL - Aleph]")
    fall_bet_idx = content.find("[FALL - Bet]")
    spring_idx = content.find("[SPRING - Aleph]")

    assert fall_aleph_idx != -1
    assert fall_bet_idx != -1
    assert spring_idx != -1
    assert fall_aleph_idx < fall_bet_idx < spring_idx


def test_all_project_courses_yields_no_valid_schedules(tmp_path):
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"
    output_path = tmp_path / "schedules.txt"

    courses_path.write_text(
        """Lab A
11111
Dr. A
83101, 1, FALL, Obligatory
Project
$$$$
Lab B
22222
Dr. B
83101, 1, FALL, Obligatory
Project
""",
        encoding="utf-8",
    )
    periods_path.write_text(
        """FALL, Aleph
05-01-2026, 09-01-2026
""",
        encoding="utf-8",
    )
    programs_path.write_text("83101", encoding="utf-8")

    _build_controller(courses_path, periods_path, programs_path, output_path).run()
    content = output_path.read_text(encoding="utf-8")

    assert "No valid schedules found." in content
    assert "Lab A" not in content
    assert "Lab B" not in content


# ---------------------------------------------------------------------------
# SCRUM-195: Full schedule-generation output correctness.
# ---------------------------------------------------------------------------

def test_small_input_produces_exact_expected_schedules(tmp_path):
    """Integration test: small input, exact output size, exact schedule correctness."""
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"
    output_path = tmp_path / "schedules.txt"

    courses_path.write_text(
        """Math 1
11111
Dr. A
83101, 1, FALL, Obligatory
Exam
$$$$
Physics 1
22222
Dr. B
83101, 1, FALL, Obligatory
Exam
$$$$
Intro to Software
33333
Dr. C
83102, 1, FALL, Obligatory
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

    programs_path.write_text("83101, 83102", encoding="utf-8")

    _build_controller(courses_path, periods_path, programs_path, output_path).run()

    content = output_path.read_text(encoding="utf-8")
    parsed = _parse_output_schedules(content)

    assert content.count("Schedule #") == 4
    assert len(parsed) == 4
    assert "[FALL - Aleph]" in content

    expected = {
        (
            ("11111", date(2026, 1, 5)),
            ("22222", date(2026, 1, 6)),
            ("33333", date(2026, 1, 5)),
        ),
        (
            ("11111", date(2026, 1, 5)),
            ("22222", date(2026, 1, 6)),
            ("33333", date(2026, 1, 6)),
        ),
        (
            ("11111", date(2026, 1, 6)),
            ("22222", date(2026, 1, 5)),
            ("33333", date(2026, 1, 5)),
        ),
        (
            ("11111", date(2026, 1, 6)),
            ("22222", date(2026, 1, 5)),
            ("33333", date(2026, 1, 6)),
        ),
    }

    actual = set()

    for combined_schedule in parsed:
        assignments = combined_schedule["FALL - Aleph"]

        assert set(assignments) == {"11111", "22222", "33333"}
        assert assignments["11111"] != assignments["22222"]
        assert assignments["33333"] in {date(2026, 1, 5), date(2026, 1, 6)}

        actual.add(tuple(sorted(assignments.items())))

    assert actual == expected


def test_small_input_ignores_saturday_and_excluded_dates(tmp_path):
    """Integration test: schedules must not use Saturdays or explicitly excluded dates."""
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"
    output_path = tmp_path / "schedules.txt"

    courses_path.write_text(
        """Math 1
11111
Dr. A
83101, 1, FALL, Obligatory
Exam
$$$$
Physics 1
22222
Dr. B
83101, 1, FALL, Obligatory
Exam
$$$$
History
33333
Dr. C
83101, 2, FALL, Obligatory
Exam
""",
        encoding="utf-8",
    )

    periods_path.write_text(
        """FALL, Aleph
09-01-2026, 12-01-2026
- 11-01-2026 Holiday
""",
        encoding="utf-8",
    )

    programs_path.write_text("83101", encoding="utf-8")

    _build_controller(courses_path, periods_path, programs_path, output_path).run()

    content = output_path.read_text(encoding="utf-8")
    parsed = _parse_output_schedules(content)

    assert content.count("Schedule #") == 4
    assert len(parsed) == 4
    assert "[FALL - Aleph]" in content

    valid_dates = {date(2026, 1, 9), date(2026, 1, 12)}
    forbidden_dates = {date(2026, 1, 10), date(2026, 1, 11)}

    expected = {
        (
            ("11111", date(2026, 1, 9)),
            ("22222", date(2026, 1, 12)),
            ("33333", date(2026, 1, 9)),
        ),
        (
            ("11111", date(2026, 1, 9)),
            ("22222", date(2026, 1, 12)),
            ("33333", date(2026, 1, 12)),
        ),
        (
            ("11111", date(2026, 1, 12)),
            ("22222", date(2026, 1, 9)),
            ("33333", date(2026, 1, 9)),
        ),
        (
            ("11111", date(2026, 1, 12)),
            ("22222", date(2026, 1, 9)),
            ("33333", date(2026, 1, 12)),
        ),
    }

    actual = set()

    for combined_schedule in parsed:
        assignments = combined_schedule["FALL - Aleph"]

        assert set(assignments) == {"11111", "22222", "33333"}
        assert assignments["11111"] != assignments["22222"]
        assert set(assignments.values()).issubset(valid_dates)
        assert forbidden_dates.isdisjoint(assignments.values())

        actual.add(tuple(sorted(assignments.items())))

    assert actual == expected
