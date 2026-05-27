"""
Unit Tests: DesktopController
--------------------------------
Tests for the desktop UI orchestration layer.
All file I/O uses tmp_path; no PyQt6 imports.
"""
from pathlib import Path

import pytest

from src.controller import DesktopController


# ── File-writing helpers (mirror test_file_data_provider.py patterns) ─────────

def _write_courses(path: Path, extra: str = "") -> None:
    path.write_text(
        f"""Calculus
11111
Dr. Cohen
83101, 1, FALL, Obligatory
Exam
$$$$
Algorithms
22222
Dr. Levi
83102, 2, FALL, Elective
Exam
{extra}""",
        encoding="utf-8",
    )


def _write_periods(path: Path) -> None:
    path.write_text(
        """FALL, Aleph
05-01-2026, 09-01-2026
""",
        encoding="utf-8",
    )


def _write_programs(path: Path, content: str = "83101,83102") -> None:
    path.write_text(content, encoding="utf-8")


# ── load_courses ──────────────────────────────────────────────────────────────

def test_load_courses_replace_returns_total_count(tmp_path):
    p = tmp_path / "courses.txt"
    _write_courses(p)
    ctrl = DesktopController()
    count = ctrl.load_courses(p, mode="replace")
    assert count == 2


def test_load_courses_append_accumulates(tmp_path):
    p = tmp_path / "courses.txt"
    _write_courses(p)
    ctrl = DesktopController()
    ctrl.load_courses(p, mode="replace")
    count = ctrl.load_courses(p, mode="append")
    assert count == 4  # 2 + 2 duplicate records appended


def test_load_courses_update_overwrites_existing_by_id(tmp_path):
    p = tmp_path / "courses.txt"
    _write_courses(p)
    ctrl = DesktopController()
    ctrl.load_courses(p, mode="replace")
    # Update with same file — same IDs, count stays 2
    count = ctrl.load_courses(p, mode="update")
    assert count == 2


def test_load_courses_invalid_mode_raises(tmp_path):
    p = tmp_path / "courses.txt"
    _write_courses(p)
    ctrl = DesktopController()
    with pytest.raises(ValueError, match="Unknown merge mode"):
        ctrl.load_courses(p, mode="invalid")


# ── load_periods ──────────────────────────────────────────────────────────────

def test_load_periods_returns_count(tmp_path):
    p = tmp_path / "dates.txt"
    _write_periods(p)
    ctrl = DesktopController()
    count = ctrl.load_periods(p, mode="replace")
    assert count == 1


def test_load_periods_append_mode(tmp_path):
    p = tmp_path / "dates.txt"
    _write_periods(p)
    ctrl = DesktopController()
    ctrl.load_periods(p, mode="replace")
    count = ctrl.load_periods(p, mode="append")
    assert count == 2


# ── load_programs ─────────────────────────────────────────────────────────────

def test_load_programs_returns_count(tmp_path):
    p = tmp_path / "programs.txt"
    _write_programs(p)
    ctrl = DesktopController()
    count = ctrl.load_programs(p)
    assert count == 2


def test_load_programs_invalid_file_raises(tmp_path):
    p = tmp_path / "programs.txt"
    _write_programs(p, content="")      # empty → ProgramSelectorReader raises
    ctrl = DesktopController()
    with pytest.raises(ValueError):
        ctrl.load_programs(p)


# ── get_programme_ids ─────────────────────────────────────────────────────────

def test_get_programme_ids_derived_from_courses_when_no_programs_loaded(tmp_path):
    p = tmp_path / "courses.txt"
    _write_courses(p)
    ctrl = DesktopController()
    ctrl.load_courses(p)
    ids = ctrl.get_programme_ids()
    assert "83101" in ids
    assert "83102" in ids


def test_get_programme_ids_returns_empty_before_any_load():
    ctrl = DesktopController()
    assert ctrl.get_programme_ids() == []


def test_get_programme_ids_prefers_programs_file_over_courses(tmp_path):
    cp = tmp_path / "courses.txt"
    _write_courses(cp)
    pp = tmp_path / "programs.txt"
    _write_programs(pp, content="83101")   # only 83101
    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_programs(pp)
    ids = ctrl.get_programme_ids()
    assert ids == ["83101"]               # 83102 excluded by programs file


# ── get_courses_by_programme ──────────────────────────────────────────────────

def test_get_courses_by_programme_filters_correctly(tmp_path):
    p = tmp_path / "courses.txt"
    _write_courses(p)
    ctrl = DesktopController()
    ctrl.load_courses(p)
    courses_101 = ctrl.get_courses_by_programme("83101")
    assert all(
        any(o.program_id == "83101" for o in c.offerings)
        for c in courses_101
    )
    assert len(courses_101) == 1   # only Calculus belongs to 83101


def test_get_courses_by_programme_returns_empty_for_unknown(tmp_path):
    p = tmp_path / "courses.txt"
    _write_courses(p)
    ctrl = DesktopController()
    ctrl.load_courses(p)
    assert ctrl.get_courses_by_programme("99999") == []


# ── properties ────────────────────────────────────────────────────────────────

def test_has_courses_false_before_load():
    assert DesktopController().has_courses is False


def test_has_courses_true_after_load(tmp_path):
    p = tmp_path / "courses.txt"
    _write_courses(p)
    ctrl = DesktopController()
    ctrl.load_courses(p)
    assert ctrl.has_courses is True


def test_has_periods_false_before_load():
    assert DesktopController().has_periods is False


def test_has_periods_true_after_load(tmp_path):
    p = tmp_path / "dates.txt"
    _write_periods(p)
    ctrl = DesktopController()
    ctrl.load_periods(p)
    assert ctrl.has_periods is True


def test_courses_property_returns_list(tmp_path):
    p = tmp_path / "courses.txt"
    _write_courses(p)
    ctrl = DesktopController()
    ctrl.load_courses(p)
    assert len(ctrl.courses) == 2


# ── set_selected_programs ─────────────────────────────────────────────────────

def test_set_selected_programs_stores_ids():
    ctrl = DesktopController()
    ctrl.set_selected_programs(["83101", "83102"])
    assert ctrl._selected_programs == ["83101", "83102"]


def test_set_selected_programs_raises_if_more_than_five():
    ctrl = DesktopController()
    with pytest.raises(ValueError, match="Maximum 5"):
        ctrl.set_selected_programs(["1", "2", "3", "4", "5", "6"])


# ── update_exam_periods ───────────────────────────────────────────────────────

def test_update_exam_periods_replaces_loaded_periods(tmp_path):
    dp = tmp_path / "dates.txt"
    _write_periods(dp)
    ctrl = DesktopController()
    ctrl.load_periods(dp)
    assert len(ctrl.get_exam_periods()) == 1
    ctrl.update_exam_periods([])
    assert ctrl.get_exam_periods() == []


# ── generate (precondition guards) ───────────────────────────────────────────

def test_generate_raises_when_no_programmes_selected():
    ctrl = DesktopController()
    with pytest.raises(ValueError, match="No programmes selected"):
        ctrl.generate()


def test_generate_raises_when_no_courses_loaded(tmp_path):
    ctrl = DesktopController()
    ctrl.set_selected_programs(["83101"])
    with pytest.raises(ValueError, match="No courses loaded"):
        ctrl.generate()


def test_generate_raises_when_no_periods_loaded(tmp_path):
    cp = tmp_path / "courses.txt"
    _write_courses(cp)
    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.set_selected_programs(["83101"])
    with pytest.raises(ValueError, match="No exam periods loaded"):
        ctrl.generate()


# ── generate (happy path) ────────────────────────────────────────────────────

def test_generate_returns_schedules_and_courses(tmp_path):
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"
    _write_courses(cp)
    _write_periods(dp)
    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])
    schedules_by_period, courses_by_id = ctrl.generate()
    assert isinstance(schedules_by_period, dict)
    assert isinstance(courses_by_id, dict)
    assert "11111" in courses_by_id


# ── export ────────────────────────────────────────────────────────────────────

def test_export_writes_output_file(tmp_path):
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"
    out = tmp_path / "out.txt"
    _write_courses(cp)
    _write_periods(dp)
    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])
    schedules_by_period, _ = ctrl.generate()
    ctrl.export(schedules_by_period, out)
    assert out.exists()
    assert out.stat().st_size > 0
