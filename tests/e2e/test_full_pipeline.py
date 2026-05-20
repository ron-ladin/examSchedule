"""
E2E Tests: Full Pipeline
-------------------------
End-to-end tests for the complete pipeline using both synthetic and real data
files. These tests defend the system against regressions in any layer.
"""
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List

import pytest

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.adapters.file_data_provider import FileDataProvider
from src.adapters.text_file_exporter import TextFileExporter
from src.engine.app_controller import AppController
from src.engine.schedule_generator import ScheduleGenerator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REAL_COURSES = PROJECT_ROOT / "data" / "courses.txt"
REAL_PERIODS = PROJECT_ROOT / "data" / "dates.txt"
REAL_PROGRAMS = PROJECT_ROOT / "data" / "programs.txt"


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
    """Parse cross-product output into a list of combined schedules.

    Each combined schedule is {period_label: {course_id: exam_date}}.
    """
    results = []
    current_combined: Dict[str, Dict[str, date]] = {}
    current_period: str | None = None

    line_re = re.compile(
        r"-\s.+\|\s*Course ID:\s*(\d+)\s*\|\s*Date:\s*(\d{2}-\d{2}-\d{4})\s*\|"
    )
    period_re = re.compile(r"^\[(.+)\]$")

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("Schedule #"):
            if current_combined:
                results.append(current_combined)
            current_combined = {}
            current_period = None
        elif period_re.match(line):
            current_period = period_re.match(line).group(1)
            current_combined[current_period] = {}
        elif line.startswith("-") and current_period is not None:
            m = line_re.match(line)
            if m:
                course_id = m.group(1)
                exam_date = datetime.strptime(m.group(2), "%d-%m-%Y").date()
                current_combined[current_period][course_id] = exam_date

    if current_combined:
        results.append(current_combined)

    return results


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


def test_pipeline_completes_quickly_on_real_data(tmp_path):
    if not (REAL_COURSES.exists() and REAL_PERIODS.exists() and REAL_PROGRAMS.exists()):
        pytest.skip("Real data files missing in data/")

    output_path = tmp_path / "schedules.txt"
    controller = _build_controller(REAL_COURSES, REAL_PERIODS, REAL_PROGRAMS, output_path)

    started = time.monotonic()
    controller.run()
    elapsed = time.monotonic() - started

    assert elapsed < 30.0, f"Pipeline took {elapsed:.2f}s — must finish under 30s"
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_pipeline_on_real_data_skips_empty_semester(tmp_path):
    """SPRI has no Exam courses → skipped by controller, not in output."""
    if not (REAL_COURSES.exists() and REAL_PERIODS.exists() and REAL_PROGRAMS.exists()):
        pytest.skip("Real data files missing in data/")

    output_path = tmp_path / "schedules.txt"
    _build_controller(REAL_COURSES, REAL_PERIODS, REAL_PROGRAMS, output_path).run()
    content = output_path.read_text(encoding="utf-8")

    assert "SPRING" not in content


def test_pipeline_on_real_data_produces_period_sub_headers(tmp_path):
    if not (REAL_COURSES.exists() and REAL_PERIODS.exists() and REAL_PROGRAMS.exists()):
        pytest.skip("Real data files missing in data/")

    output_path = tmp_path / "schedules.txt"
    _build_controller(REAL_COURSES, REAL_PERIODS, REAL_PROGRAMS, output_path).run()
    content = output_path.read_text(encoding="utf-8")

    assert "[FALL - Aleph]" in content
    assert "[FALL - Bet]" in content


def test_no_conflicting_courses_share_date_in_real_data(tmp_path):
    if not (REAL_COURSES.exists() and REAL_PERIODS.exists() and REAL_PROGRAMS.exists()):
        pytest.skip("Real data files missing in data/")

    output_path = tmp_path / "schedules.txt"
    data_provider = FileDataProvider(REAL_COURSES, REAL_PERIODS, REAL_PROGRAMS)
    selected_programs = data_provider.get_selected_programs()
    controller = AppController(
        data_provider=data_provider,
        exporter=TextFileExporter(output_path),
        generator=ScheduleGenerator(ExactConflictStrategy(selected_programs)),
        selected_programs=selected_programs,
    )
    controller.run()

    courses_by_id = {c.id: c for c in data_provider.get_courses()}
    strategy = ExactConflictStrategy(selected_programs)

    parsed = _parse_output_schedules(output_path.read_text(encoding="utf-8"))
    assert len(parsed) > 0, "Expected at least one schedule in the output"

    for combined_schedule in parsed:
        for period_label, assignments in combined_schedule.items():
            ids = list(assignments.keys())
            for i, id_a in enumerate(ids):
                for id_b in ids[i + 1:]:
                    if assignments[id_a] != assignments[id_b]:
                        continue
                    a = courses_by_id.get(id_a)
                    b = courses_by_id.get(id_b)
                    assert a is not None and b is not None
                    assert not strategy.is_conflict(a, b), (
                        f"Conflict violation in {period_label}: "
                        f"{id_a} and {id_b} share date {assignments[id_a]}"
                    )


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
    assert fall_aleph_idx != -1 and fall_bet_idx != -1 and spring_idx != -1
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
