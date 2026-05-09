"""
Unit Tests: TextFileExporter
------------------------------
Tests for output formatting logic in TextFileExporter.

Test cases to implement:
    1. Basic output — correct semester/moed headers and schedule lines.
    2. SPRI semester → "SPRING" displayed in output.
    3. Courses within a schedule are sorted chronologically.
    4. Multiple schedules in one period are numbered from #1.
    5. Empty schedules iterable → "No valid schedules found." written.
    6. Unknown course_id in assignment → line is skipped (warning logged).
    7. Multiple periods → all written in order.

Notes:
    - Use tmp_path pytest fixture to create temporary output files.
    - Use iter([...]) to simulate a streaming iterator input.
    - Import TextFileExporter from src.adapters.text_file_exporter.
"""

import logging
from datetime import date

import pytest

from src.adapters.text_file_exporter import TextFileExporter
from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule


def _make_course(course_id: str, name: str, instructor: str) -> Course:
    return Course(id=course_id, name=name, instructor=instructor, evaluation_type="Exam")


def _make_period(semester: str, moed: str) -> ExamPeriod:
    return ExamPeriod(
        semester=semester,
        moed=moed,
        date_ranges=[(date(2025, 1, 1), date(2025, 1, 31))],
    )


def _make_schedule(period: ExamPeriod, assignments: dict) -> Schedule:
    s = Schedule(period=period)
    s.assignments = assignments
    return s


def test_basic_output_format(tmp_path):
    exporter = TextFileExporter(tmp_path / "schedules.txt")
    period = _make_period("FALL", "Aleph")
    course = _make_course("11111", "Calculus", "Dr. Cohen")
    schedule = _make_schedule(period, {"11111": date(2025, 1, 5)})

    exporter.export_schedules(
        schedules_by_period={"FALL - Aleph": iter([schedule])},
        courses_by_id={"11111": course},
    )

    content = (tmp_path / "schedules.txt").read_text(encoding="utf-8")
    assert "=== SEMESTER: FALL ===" in content
    assert "--- Moed: Aleph ---" in content
    assert "Schedule #1:" in content
    assert "Calculus" in content
    assert "05-01-2025" in content
    assert "Dr. Cohen" in content


def test_spri_displays_as_spring(tmp_path):
    exporter = TextFileExporter(tmp_path / "schedules.txt")
    period = _make_period("SPRI", "Aleph")
    course = _make_course("22222", "Linear Algebra", "Dr. Levi")
    schedule = _make_schedule(period, {"22222": date(2025, 3, 10)})

    exporter.export_schedules(
        schedules_by_period={"SPRI - Aleph": iter([schedule])},
        courses_by_id={"22222": course},
    )

    content = (tmp_path / "schedules.txt").read_text(encoding="utf-8")
    assert "=== SEMESTER: SPRING ===" in content
    assert "=== SEMESTER: SPRI ===" not in content


def test_courses_sorted_chronologically(tmp_path):
    exporter = TextFileExporter(tmp_path / "schedules.txt")
    period = _make_period("FALL", "Aleph")
    course_a = _make_course("11111", "Course A", "Instructor A")
    course_b = _make_course("22222", "Course B", "Instructor B")

    # Course B (22222) has an earlier date — should appear first
    schedule = _make_schedule(period, {
        "11111": date(2025, 1, 10),
        "22222": date(2025, 1, 5),
    })

    exporter.export_schedules(
        schedules_by_period={"FALL - Aleph": iter([schedule])},
        courses_by_id={"11111": course_a, "22222": course_b},
    )

    content = (tmp_path / "schedules.txt").read_text(encoding="utf-8")
    assert content.index("Course B") < content.index("Course A")


def test_multiple_schedules_numbered_from_one(tmp_path):
    exporter = TextFileExporter(tmp_path / "schedules.txt")
    period = _make_period("FALL", "Aleph")
    course = _make_course("11111", "Calculus", "Dr. Cohen")

    schedules = [
        _make_schedule(period, {"11111": date(2025, 1, i)})
        for i in range(5, 8)
    ]

    exporter.export_schedules(
        schedules_by_period={"FALL - Aleph": iter(schedules)},
        courses_by_id={"11111": course},
    )

    content = (tmp_path / "schedules.txt").read_text(encoding="utf-8")
    assert "Schedule #1:" in content
    assert "Schedule #2:" in content
    assert "Schedule #3:" in content


def test_empty_period_writes_no_valid_schedules(tmp_path):
    exporter = TextFileExporter(tmp_path / "schedules.txt")

    exporter.export_schedules(
        schedules_by_period={"FALL - Aleph": iter([])},
        courses_by_id={},
    )

    content = (tmp_path / "schedules.txt").read_text(encoding="utf-8")
    assert "No valid schedules found." in content


def test_unknown_course_id_skipped_with_warning(tmp_path, caplog):
    exporter = TextFileExporter(tmp_path / "schedules.txt")
    period = _make_period("FALL", "Aleph")
    schedule = _make_schedule(period, {"99999": date(2025, 1, 5)})

    with caplog.at_level(logging.WARNING):
        exporter.export_schedules(
            schedules_by_period={"FALL - Aleph": iter([schedule])},
            courses_by_id={},
        )

    content = (tmp_path / "schedules.txt").read_text(encoding="utf-8")
    assert "99999" not in content
    assert any("99999" in r.message for r in caplog.records)


def test_multiple_periods_all_written(tmp_path):
    exporter = TextFileExporter(tmp_path / "schedules.txt")
    period_fall = _make_period("FALL", "Aleph")
    period_spri = _make_period("SPRI", "Bet")
    course = _make_course("11111", "Calculus", "Dr. Cohen")

    exporter.export_schedules(
        schedules_by_period={
            "FALL - Aleph": iter([_make_schedule(period_fall, {"11111": date(2025, 1, 5)})]),
            "SPRI - Bet": iter([_make_schedule(period_spri, {"11111": date(2025, 3, 5)})]),
        },
        courses_by_id={"11111": course},
    )

    content = (tmp_path / "schedules.txt").read_text(encoding="utf-8")
    assert "=== SEMESTER: FALL ===" in content
    assert "--- Moed: Aleph ---" in content
    assert "=== SEMESTER: SPRING ===" in content
    assert "--- Moed: Bet ---" in content
