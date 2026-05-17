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
from typing import Dict, List, Tuple

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


# Parses an output schedule file into {period_key: [ {course_id: date}, ... ]}.
# Each schedule entry line looks like:
#   - <name> | Course ID: 12345 | Date: DD-MM-YYYY | Instructor: ...
def _parse_output_schedules(content: str) -> Dict[str, List[Dict[str, date]]]:
    schedules_by_period: Dict[str, List[Dict[str, date]]] = {}
    current_semester = None
    current_moed = None
    current_schedule: Dict[str, date] = {}
    in_schedule = False

    line_re = re.compile(
        r"-\s.+\|\s*Course ID:\s*(\d+)\s*\|\s*Date:\s*(\d{2}-\d{2}-\d{4})\s*\|"
    )

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("=== SEMESTER:"):
            current_semester = line.replace("=== SEMESTER:", "").replace("===", "").strip()
        elif line.startswith("--- Moed:"):
            current_moed = line.replace("--- Moed:", "").replace("---", "").strip()
        elif line.startswith("Schedule #"):
            if in_schedule and current_schedule:
                key = f"{current_semester} - {current_moed}"
                schedules_by_period.setdefault(key, []).append(current_schedule)
            current_schedule = {}
            in_schedule = True
        elif in_schedule and line.startswith("-"):
            m = line_re.match(line)
            if m:
                course_id = m.group(1)
                exam_date = datetime.strptime(m.group(2), "%d-%m-%Y").date()
                current_schedule[course_id] = exam_date
        elif not line and in_schedule:
            if current_schedule:
                key = f"{current_semester} - {current_moed}"
                schedules_by_period.setdefault(key, []).append(current_schedule)
            current_schedule = {}
            in_schedule = False

    if in_schedule and current_schedule:
        key = f"{current_semester} - {current_moed}"
        schedules_by_period.setdefault(key, []).append(current_schedule)

    return schedules_by_period

# This integration test checks the entire app workflow from start to finish.
    # It reads mock files, runs the scheduler, and creates a final text schedule report.
def test_full_pipeline_creates_non_empty_output_file(tmp_path):
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"
    output_path = tmp_path / "schedules.txt"

    # We add 2 exam courses (Calculus, Algorithms) and 1 non-exam project course (Project Lab)
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

    # Connect all components together (Data Provider -> Strategy -> Generator -> Controller)
    data_provider = FileDataProvider(courses_path, periods_path, programs_path)
    selected_programs = data_provider.get_selected_programs()
    conflict_strategy = ExactConflictStrategy(selected_programs)
    generator = ScheduleGenerator(conflict_strategy)
    exporter = TextFileExporter(output_path)
    controller = AppController(
        data_provider=data_provider,
        exporter=exporter,
        generator=generator,
        selected_programs=selected_programs,
    )

    # Start the app execution   
    controller.run()

    content = output_path.read_text(encoding="utf-8")
    # Assertions: Verify the output file exists, has content, and formats headers cleanly
    assert output_path.exists()
    assert content.strip()
    assert "=== SEMESTER: FALL ===" in content
    assert "Schedule #1:" in content
    # Check that exam courses are included, but evaluation types like "Project" are filtered out
    assert "Calculus" in content
    assert "Algorithms" in content
    assert "Project Lab" not in content

#  This integration test verifies end-to-end mapping requirement.
    # It makes sure that if the text database files contain the raw short string "SPRI",
    # the final system output dynamically rewrites and maps it cleanly to "SPRING".
def test_full_pipeline_displays_spri_as_spring(tmp_path):
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"
    output_path = tmp_path / "schedules.txt"

    courses_path.write_text(
        """Linear Algebra
44444
Dr. Spring
83101, 1, SPRING, Obligatory
Exam
""",
        encoding="utf-8",
    )
    # The file contains the raw term "SPRI"
    periods_path.write_text(
        """SPRI, Aleph
01-03-2026, 02-03-2026
""",
        encoding="utf-8",
    )
    programs_path.write_text("83101", encoding="utf-8")

    data_provider = FileDataProvider(courses_path, periods_path, programs_path)
    selected_programs = data_provider.get_selected_programs()
    controller = AppController(
        data_provider=data_provider,
        exporter=TextFileExporter(output_path),
        generator=ScheduleGenerator(ExactConflictStrategy(selected_programs)),
        selected_programs=selected_programs,
    )

    controller.run()

    content = output_path.read_text(encoding="utf-8")

    # Assertions: Verify that "SPRING" is visible and the ugly raw "SPRI" is hidden
    assert "=== SEMESTER: SPRING ===" in content
    assert "=== SEMESTER: SPRI ===" not in content


# Run the FULL pipeline using the real data files in data/ — the realistic end-to-end test.
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


# Real data has a SPRI period with no exam courses → "No valid schedules found." should appear.
def test_pipeline_on_real_data_shows_no_valid_schedules_for_empty_period(tmp_path):
    if not (REAL_COURSES.exists() and REAL_PERIODS.exists() and REAL_PROGRAMS.exists()):
        pytest.skip("Real data files missing in data/")

    output_path = tmp_path / "schedules.txt"
    _build_controller(REAL_COURSES, REAL_PERIODS, REAL_PROGRAMS, output_path).run()
    content = output_path.read_text(encoding="utf-8")

    assert "No valid schedules found." in content


# Real data should produce both FALL and SPRING semester headers in output
def test_pipeline_on_real_data_produces_semester_and_moed_headers(tmp_path):
    if not (REAL_COURSES.exists() and REAL_PERIODS.exists() and REAL_PROGRAMS.exists()):
        pytest.skip("Real data files missing in data/")

    output_path = tmp_path / "schedules.txt"
    _build_controller(REAL_COURSES, REAL_PERIODS, REAL_PROGRAMS, output_path).run()
    content = output_path.read_text(encoding="utf-8")

    assert "=== SEMESTER: FALL ===" in content
    assert "=== SEMESTER: SPRING ===" in content
    assert "--- Moed: Aleph ---" in content
    assert "--- Moed: Bet ---" in content


# CRITICAL CORRECTNESS INVARIANT: in every yielded schedule, no two conflicting courses
# share a date. This is the heart of what the system promises.
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
    total_schedules = sum(len(v) for v in parsed.values())
    assert total_schedules > 0, "Expected at least one schedule in the output"

    for period_key, schedules in parsed.items():
        for schedule in schedules:
            ids = list(schedule.keys())
            for i, id_a in enumerate(ids):
                for id_b in ids[i + 1:]:
                    if schedule[id_a] != schedule[id_b]:
                        continue
                    a = courses_by_id.get(id_a)
                    b = courses_by_id.get(id_b)
                    assert a is not None and b is not None
                    assert not strategy.is_conflict(a, b), (
                        f"Conflict violation in {period_key}: "
                        f"{id_a} and {id_b} share date {schedule[id_a]}"
                    )


# Synthetic scenario: 3 obligatory courses in same program/year/semester must all
# get different dates in every schedule
def test_three_obligatory_courses_get_three_different_dates(tmp_path):
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"
    output_path = tmp_path / "schedules.txt"

    courses_path.write_text(
        """Calc
11111
Dr. A
83101, 1, FALL, Obligatory
Exam
$$$$
Algebra
22222
Dr. B
83101, 1, FALL, Obligatory
Exam
$$$$
Physics
33333
Dr. C
83101, 1, FALL, Obligatory
Exam
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

    parsed = _parse_output_schedules(content)
    schedules = parsed.get("FALL - Aleph", [])
    assert len(schedules) > 0
    for s in schedules:
        dates = set(s.values())
        assert len(dates) == 3, f"All 3 obligatory courses must have unique dates: {s}"


# Synthetic scenario: 3 elective courses can all share the same date
def test_three_elective_courses_can_share_date(tmp_path):
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"
    output_path = tmp_path / "schedules.txt"

    courses_path.write_text(
        """Art
11111
Dr. A
83101, 1, FALL, Elective
Exam
$$$$
Music
22222
Dr. B
83101, 1, FALL, Elective
Exam
$$$$
Drama
33333
Dr. C
83101, 1, FALL, Elective
Exam
""",
        encoding="utf-8",
    )
    periods_path.write_text(
        """FALL, Aleph
05-01-2026, 05-01-2026
""",
        encoding="utf-8",
    )
    programs_path.write_text("83101", encoding="utf-8")

    _build_controller(courses_path, periods_path, programs_path, output_path).run()
    parsed = _parse_output_schedules(output_path.read_text(encoding="utf-8"))
    schedules = parsed.get("FALL - Aleph", [])
    assert len(schedules) == 1
    only = schedules[0]
    assert len(only) == 3
    assert len(set(only.values())) == 1  # all 3 on the SAME date


# Edge case: Saturday at start of range must never be assigned an exam
def test_saturday_never_assigned_in_output(tmp_path):
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
    # Range spans a Saturday (10-Jan-2026)
    periods_path.write_text(
        """FALL, Aleph
09-01-2026, 11-01-2026
""",
        encoding="utf-8",
    )
    programs_path.write_text("83101", encoding="utf-8")

    _build_controller(courses_path, periods_path, programs_path, output_path).run()
    parsed = _parse_output_schedules(output_path.read_text(encoding="utf-8"))

    for schedules in parsed.values():
        for s in schedules:
            for d in s.values():
                assert d.weekday() != 5
                assert d != date(2026, 1, 10)


# Edge case: a period whose only valid date is Saturday → no schedules can be produced
def test_period_with_only_saturday_produces_no_schedules(tmp_path):
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
    # 10-Jan-2026 is Saturday — the ONLY date in the range
    periods_path.write_text(
        """FALL, Aleph
10-01-2026, 10-01-2026
""",
        encoding="utf-8",
    )
    programs_path.write_text("83101", encoding="utf-8")

    _build_controller(courses_path, periods_path, programs_path, output_path).run()
    content = output_path.read_text(encoding="utf-8")
    assert "No valid schedules found." in content


# Edge case: validation must catch a selected program that doesn't exist in any course
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
    # 99999 doesn't appear in any course offering
    programs_path.write_text("99999", encoding="utf-8")

    controller = _build_controller(courses_path, periods_path, programs_path, output_path)
    with pytest.raises(ValueError):
        controller.run()


# Edge case: duplicate exam period (same semester + moed twice) must be rejected
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


# Edge case: a course in a different semester than the period must NOT appear in output
def test_course_in_other_semester_excluded_from_period(tmp_path):
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"
    output_path = tmp_path / "schedules.txt"

    courses_path.write_text(
        """FallExam
11111
Dr. A
83101, 1, FALL, Obligatory
Exam
$$$$
SpringExam
22222
Dr. B
83101, 1, SPRI, Obligatory
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
    assert "FallExam" in content
    assert "SpringExam" not in content


# Excluded date range in the file must remove ALL dates inside it from the output
def test_excluded_date_range_in_period_removed_from_output(tmp_path):
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
    # Range 12-16 Jan but exclude 13-15 → only 12 and 16 should ever appear
    periods_path.write_text(
        """FALL, Aleph
12-01-2026, 16-01-2026
- 13-01-2026, 15-01-2026
""",
        encoding="utf-8",
    )
    programs_path.write_text("83101", encoding="utf-8")

    _build_controller(courses_path, periods_path, programs_path, output_path).run()
    parsed = _parse_output_schedules(output_path.read_text(encoding="utf-8"))

    used_dates = set()
    for schedules in parsed.values():
        for s in schedules:
            used_dates.update(s.values())

    assert date(2026, 1, 13) not in used_dates
    assert date(2026, 1, 14) not in used_dates
    assert date(2026, 1, 15) not in used_dates
    assert used_dates.issubset({date(2026, 1, 12), date(2026, 1, 16)})


# Output file should be re-creatable: running twice overwrites cleanly without corruption
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
    # Confirm the file was truly rewritten (not appended)
    assert second_content.count("=== SEMESTER: FALL ===") == 1


# Periods should appear in canonical order in the output: FALL → SPRING → SUMMER
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
    # Reverse order in the file: SPRI Aleph first, then FALL Bet, then FALL Aleph
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

    # Output must be FALL/Aleph, FALL/Bet, SPRING/Aleph in that order
    fall_aleph_idx = content.find("=== SEMESTER: FALL ===\n--- Moed: Aleph ---")
    fall_bet_idx = content.find("=== SEMESTER: FALL ===\n--- Moed: Bet ---")
    spring_idx = content.find("=== SEMESTER: SPRING ===")
    assert fall_aleph_idx != -1 and fall_bet_idx != -1 and spring_idx != -1
    assert fall_aleph_idx < fall_bet_idx < spring_idx