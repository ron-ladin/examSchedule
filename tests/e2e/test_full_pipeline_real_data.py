"""
E2E Tests: Full Pipeline against the real data/ files.

These tests skip when the bundled data files are absent. They guard timing,
semester skipping, period sub-headers, and conflict-freedom on real input.
"""

import time

import pytest

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.adapters.file_data_provider import FileDataProvider
from src.adapters.text_file_exporter import TextFileExporter
from src.engine.app_controller import AppController
from src.engine.schedule_generator import ScheduleGenerator

from tests.e2e._pipeline_helpers import (
    REAL_COURSES,
    REAL_PERIODS,
    REAL_PROGRAMS,
    _build_controller,
    _parse_output_schedules,
)


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
