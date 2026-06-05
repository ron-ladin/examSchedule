"""
E2E Tests: File Parsing + Schedule Generation Integration
---------------------------------------------------------
SCRUM-192.

These tests verify that temporary input files are parsed through FileDataProvider
and then used by the real AppController, ScheduleGenerator, ExactConflictStrategy,
and TextFileExporter pipeline.

No PyQt imports.
No UI tests.
"""

import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.adapters.file_data_provider import FileDataProvider
from src.adapters.text_file_exporter import TextFileExporter
from src.engine.app_controller import AppController
from src.engine.schedule_generator import ScheduleGenerator


def _build_controller(
    courses_path: Path,
    periods_path: Path,
    programs_path: Path,
    output_path: Path,
) -> AppController:
    data_provider = FileDataProvider(courses_path, periods_path, programs_path)
    selected_programs = data_provider.get_selected_programs()

    return AppController(
        data_provider=data_provider,
        exporter=TextFileExporter(output_path),
        generator=ScheduleGenerator(ExactConflictStrategy(selected_programs)),
        selected_programs=selected_programs,
    )


def _parse_output_schedules(content: str) -> List[Dict[str, Dict[str, date]]]:
    """
    Parse exported schedules into:
    [
        {
            "FALL - Aleph": {
                "11111": date(...),
                "22222": date(...),
            }
        }
    ]
    """
    results: List[Dict[str, Dict[str, date]]] = []
    current_schedule: Dict[str, Dict[str, date]] = {}
    current_period: str | None = None

    period_re = re.compile(r"^\[(.+)\]$")
    line_re = re.compile(
        r"-\s.+\|\s*Course ID:\s*(\d+)\s*\|\s*Date:\s*(\d{2}-\d{2}-\d{4})\s*\|"
    )

    for raw_line in content.splitlines():
        line = raw_line.strip()

        if line.startswith("Schedule #"):
            if current_schedule:
                results.append(current_schedule)

            current_schedule = {}
            current_period = None
            continue

        period_match = period_re.match(line)
        if period_match:
            current_period = period_match.group(1)
            current_schedule[current_period] = {}
            continue

        if line.startswith("-") and current_period is not None:
            line_match = line_re.match(line)

            if line_match:
                course_id = line_match.group(1)
                exam_date = datetime.strptime(line_match.group(2), "%d-%m-%Y").date()
                current_schedule[current_period][course_id] = exam_date

    if current_schedule:
        results.append(current_schedule)

    return results


def test_parsed_files_generate_expected_conflict_free_schedules(tmp_path):
    """
    SCRUM-192.

    File parsing + generation integration:
    two obligatory courses in the same programme/year/semester must be placed on
    different dates after being parsed from text files.
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
$$$$
Algorithms
22222
Dr. Levi
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

    content = output_path.read_text(encoding="utf-8")
    parsed = _parse_output_schedules(content)

    assert content.count("Schedule #") == 2
    assert len(parsed) == 2
    assert "[FALL - Aleph]" in content

    expected = {
        (
            ("11111", date(2026, 1, 5)),
            ("22222", date(2026, 1, 6)),
        ),
        (
            ("11111", date(2026, 1, 6)),
            ("22222", date(2026, 1, 5)),
        ),
    }

    actual = set()

    for combined_schedule in parsed:
        assignments = combined_schedule["FALL - Aleph"]

        assert set(assignments) == {"11111", "22222"}
        assert assignments["11111"] != assignments["22222"]

        actual.add(tuple(sorted(assignments.items())))

    assert actual == expected


def test_parsed_excluded_dates_affect_generation(tmp_path):
    """
    SCRUM-192.

    Excluded dates parsed from dates.txt must be removed from the dates that the
    generator may use.
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
05-01-2026, 07-01-2026
- 06-01-2026
""",
        encoding="utf-8",
    )

    programs_path.write_text("83101", encoding="utf-8")

    _build_controller(courses_path, periods_path, programs_path, output_path).run()

    content = output_path.read_text(encoding="utf-8")
    parsed = _parse_output_schedules(content)

    assert content.count("Schedule #") == 2
    assert len(parsed) == 2

    used_dates = {
        assignments["11111"]
        for combined_schedule in parsed
        for assignments in combined_schedule.values()
    }

    assert used_dates == {
        date(2026, 1, 5),
        date(2026, 1, 7),
    }
    assert date(2026, 1, 6) not in used_dates


def test_selected_program_file_filters_irrelevant_courses(tmp_path):
    """
    SCRUM-192.

    The selected programmes file should control which parsed courses participate
    in generation. Courses from programmes that were not selected must not appear
    in exported schedules.
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
$$$$
Physics
22222
Dr. Levi
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

    programs_path.write_text("83101", encoding="utf-8")

    _build_controller(courses_path, periods_path, programs_path, output_path).run()

    content = output_path.read_text(encoding="utf-8")
    parsed = _parse_output_schedules(content)

    assert content.count("Schedule #") == 2
    assert len(parsed) == 2

    assert "Calculus" in content
    assert "Course ID: 11111" in content

    assert "Physics" not in content
    assert "Course ID: 22222" not in content

    for combined_schedule in parsed:
        assignments = combined_schedule["FALL - Aleph"]
        assert set(assignments) == {"11111"}
