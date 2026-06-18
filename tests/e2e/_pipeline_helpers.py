"""
Shared builders/parsers for full-pipeline E2E tests.

Assembles an AppController from file paths and parses the cross-product text
output back into structured schedules for correctness assertions.
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
