"""
Unit tests: _MemoryExporter sorting + CLI settings flow
-------------------------------------------------------
Regression coverage for the lazy-generation fix that moved CLI sorting out of
AppController and into _MemoryExporter.

Before this fix:
  - AppController applied SortingEngine.sort, but that path was removed to keep
    generation lazy.
  - main.py still built _MemoryExporter with settings=None, so when running the
    CLI with --settings the configured sort was silently ignored.

These tests pin the new contract:
  - _MemoryExporter applies the configured sort when settings.sorting has rules.
  - Sorting works with a cap set (only the capped page is sorted).
  - Sorting does NOT force full materialisation beyond the capped page.
  - main._run_cli passes the loaded settings into _MemoryExporter, so CLI
    --settings sorting is not silently dropped.
"""

from datetime import date
from pathlib import Path

import main
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.domain.settings import Settings
from src.domain.sorting import SortCriterion, SortingConfig, SortRule
from src.domain.threshold import ThresholdSettings
from src.engine.generation_workers import _MemoryExporter

PROGRAM = "83101"
SEMESTER = "FALL"

BASE_PERIOD = ExamPeriod(
    semester=SEMESTER,
    moed="Aleph",
    date_ranges=[(date(2026, 1, 4), date(2026, 1, 31))],
)


def _mandatory(course_id: str) -> Course:
    course = Course(
        id=course_id,
        name=f"Course {course_id}",
        instructor="Prof. X",
        evaluation_type="Exam",
    )
    course.add_offering(
        CourseOffering(
            program_id=PROGRAM, year=1, semester=SEMESTER, requirement="Obligatory"
        )
    )
    return course


def _schedule(assignments: dict) -> Schedule:
    return Schedule(period=BASE_PERIOD, assignments=assignments)


def _sort_by_min_days_settings() -> Settings:
    """Settings whose only sort rule ranks descending by min mandatory gap."""
    return Settings(
        thresholds=ThresholdSettings(),
        sorting=SortingConfig(
            rules=(
                SortRule(priority=1, criterion=SortCriterion.SORT_MIN_DAYS_MANDATORY),
            )
        ),
    )


# ---------------------------------------------------------------------------
# _MemoryExporter applies SortingEngine.sort when settings.sorting exists
# ---------------------------------------------------------------------------


def test_exporter_sorts_when_settings_has_sorting_rules():
    courses_by_id = {"11111": _mandatory("11111"), "22222": _mandatory("22222")}

    wide = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 15)})  # gap 10
    medium = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 10)})  # gap 5
    narrow = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 7)})  # gap 2

    exporter = _MemoryExporter(
        settings=_sort_by_min_days_settings(), selected_programs=[PROGRAM]
    )

    # Provide them in a deliberately unsorted order.
    exporter.export_schedules({"FALL|Aleph": iter([narrow, wide, medium])}, courses_by_id)

    assert exporter.schedules_by_period["FALL|Aleph"] == [wide, medium, narrow]


def test_exporter_preserves_order_when_no_sorting_rules():
    courses_by_id = {"11111": _mandatory("11111"), "22222": _mandatory("22222")}
    narrow = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 7)})
    wide = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 15)})

    # settings=None means no sort rules -> insertion order is preserved.
    exporter = _MemoryExporter(settings=None, selected_programs=[PROGRAM])
    exporter.export_schedules({"FALL|Aleph": iter([narrow, wide])}, courses_by_id)

    assert exporter.schedules_by_period["FALL|Aleph"] == [narrow, wide]


def test_exporter_sorts_only_the_capped_page():
    courses_by_id = {"11111": _mandatory("11111"), "22222": _mandatory("22222")}
    wide = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 15)})  # gap 10
    medium = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 10)})  # gap 5
    narrow = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 7)})  # gap 2

    exporter = _MemoryExporter(
        cap=2, settings=_sort_by_min_days_settings(), selected_programs=[PROGRAM]
    )
    exporter.export_schedules(
        {"FALL|Aleph": iter([narrow, medium, wide])}, courses_by_id
    )

    page = exporter.schedules_by_period["FALL|Aleph"]
    assert len(page) == 2
    # The page is the first `cap` items (narrow, medium) sorted descending.
    assert page == [medium, narrow]
    assert exporter.has_more_by_period["FALL|Aleph"] is True


def test_exporter_sorting_does_not_materialise_beyond_capped_page():
    """Sorting must not pull the whole (possibly unbounded) generator.

    With cap=N the exporter reads at most N+1 items (the +1 is the look-ahead
    that decides has_more). A generator that explodes after that proves sorting
    never forced full materialisation.
    """
    courses_by_id = {"11111": _mandatory("11111"), "22222": _mandatory("22222")}

    advanced = 0

    def exploding_gen():
        nonlocal advanced
        gaps = [7, 3, 9, 5]
        for index, gap in enumerate(gaps):
            advanced += 1
            yield _schedule(
                {"11111": date(2026, 1, 5), "22222": date(2026, 1, 5 + gap)}
            )
            if index >= 2:  # cap(2) + 1 look-ahead already yielded
                raise AssertionError("generator advanced beyond the capped page")

    exporter = _MemoryExporter(
        cap=2, settings=_sort_by_min_days_settings(), selected_programs=[PROGRAM]
    )
    exporter.export_schedules({"FALL|Aleph": exploding_gen()}, courses_by_id)

    assert len(exporter.schedules_by_period["FALL|Aleph"]) == 2
    assert advanced == 3  # cap + one look-ahead, never the full stream


# ---------------------------------------------------------------------------
# main._run_cli passes the loaded settings into _MemoryExporter
# ---------------------------------------------------------------------------


def _write_min_inputs(tmp_path: Path) -> dict[str, Path]:
    programs = tmp_path / "programs.txt"
    programs.write_text("83101", encoding="utf-8")

    courses = tmp_path / "courses.txt"
    courses.write_text(
        "Calculus\n11111\nDr. Cohen\n83101, 1, FALL, Obligatory\nExam\n",
        encoding="utf-8",
    )

    periods = tmp_path / "periods.txt"
    periods.write_text("FALL, Aleph\n05-01-2026, 06-01-2026\n", encoding="utf-8")

    settings = tmp_path / "settings.txt"
    settings.write_text(
        "THRESHOLD\n"
        "MIN_DAYS_BETWEEN_MANDATORY_EXAMS, ON, 2\n"
        "SORT\n"
        "1, SORT_MIN_DAYS_MANDATORY\n",
        encoding="utf-8",
    )

    return {
        "programs": programs,
        "courses": courses,
        "periods": periods,
        "settings": settings,
    }


def test_run_cli_passes_loaded_settings_into_memory_exporter(tmp_path, monkeypatch):
    paths = _write_min_inputs(tmp_path)
    output = tmp_path / "schedules.txt"

    captured = {}

    class _RecordingExporter(_MemoryExporter):
        def __init__(self, *args, **kwargs):
            captured["settings"] = kwargs.get("settings")
            captured["selected_programs"] = kwargs.get("selected_programs")
            super().__init__(*args, **kwargs)

    # _run_cli imports _MemoryExporter from this module, so patch it here.
    monkeypatch.setattr(
        "src.engine.generation_workers._MemoryExporter", _RecordingExporter
    )

    main._run_cli(
        [
            "--programs", str(paths["programs"]),
            "--courses", str(paths["courses"]),
            "--periods", str(paths["periods"]),
            "--settings", str(paths["settings"]),
            "--output", str(output),
        ]
    )

    assert captured["settings"] is not None, (
        "CLI built the exporter with settings=None; --settings sorting is silently ignored"
    )
    assert captured["settings"].sorting.rules, "loaded sort rules were not forwarded"
    assert captured["selected_programs"] == ["83101"]


def test_run_cli_without_settings_leaves_exporter_settings_none(tmp_path, monkeypatch):
    paths = _write_min_inputs(tmp_path)
    output = tmp_path / "schedules.txt"

    captured = {}

    class _RecordingExporter(_MemoryExporter):
        def __init__(self, *args, **kwargs):
            captured["settings"] = kwargs.get("settings")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(
        "src.engine.generation_workers._MemoryExporter", _RecordingExporter
    )

    main._run_cli(
        [
            "--programs", str(paths["programs"]),
            "--courses", str(paths["courses"]),
            "--periods", str(paths["periods"]),
            "--output", str(output),
        ]
    )

    assert captured["settings"] is None
