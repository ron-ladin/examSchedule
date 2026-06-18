"""
Unit Tests: DesktopController — file loading, querying, and selection.

Covers load_courses/periods/programs merge modes, programme-id derivation,
course filtering, simple properties, selection limits, and empty-file edges.
"""

import pytest

from src.controller import DesktopController

from tests.unit._controller_helpers import (
    _exam_course,
    _write_courses,
    _write_periods,
    _write_programs,
)


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

    # Update with same file — same IDs, count stays 2.
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
    _write_programs(p, content="")  # empty → ProgramSelectorReader raises

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
    _write_programs(pp, content="83101")  # only 83101

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_programs(pp)

    ids = ctrl.get_programme_ids()

    assert ids == ["83101"]  # 83102 excluded by programs file


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
    assert len(courses_101) == 1  # only Calculus belongs to 83101


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


# ── edge cases / boundaries / error handling ───────────────────────

def test_empty_courses_file_is_rejected_and_controller_remains_usable(tmp_path):
    """
    Loading an empty courses file should fail safely and must not leave the
    controller in a corrupted state. After the failure, the user should still be
    able to load a valid courses file normally.
    """
    cp = tmp_path / "courses.txt"
    cp.write_text("", encoding="utf-8")

    ctrl = DesktopController()

    with pytest.raises(ValueError):
        ctrl.load_courses(cp)

    assert ctrl.has_courses is False
    assert ctrl.get_programme_ids() == []

    _write_courses(cp)

    count = ctrl.load_courses(cp)

    assert count == 2
    assert ctrl.has_courses is True
    assert "83101" in ctrl.get_programme_ids()


def test_empty_exam_periods_file_is_rejected_and_controller_remains_usable(tmp_path):
    """
    Loading an empty exam-periods file should fail safely and must not leave the
    controller in a corrupted state. After the failure, a valid periods file can
    still be loaded.
    """
    dp = tmp_path / "dates.txt"
    dp.write_text("", encoding="utf-8")

    ctrl = DesktopController()

    with pytest.raises(ValueError):
        ctrl.load_periods(dp)

    assert ctrl.has_periods is False
    assert ctrl.get_exam_periods() == []

    _write_periods(dp)

    count = ctrl.load_periods(dp)

    assert count == 1
    assert ctrl.has_periods is True


def test_empty_programs_file_is_rejected_and_controller_remains_usable(tmp_path):
    """
    Empty selected-programs input should be rejected, but the controller should
    still allow loading a valid programs file afterwards.
    """
    pp = tmp_path / "programs.txt"
    pp.write_text("", encoding="utf-8")

    ctrl = DesktopController()

    with pytest.raises(ValueError):
        ctrl.load_programs(pp)

    assert ctrl.get_programme_ids() == []

    _write_programs(pp, content="83101,83102")

    count = ctrl.load_programs(pp)

    assert count == 2
    assert ctrl.get_programme_ids() == ["83101", "83102"]


def test_selecting_more_than_five_programmes_is_rejected_and_previous_selection_kept():
    """
    The 5-programme boundary must reject invalid input without corrupting the
    last valid programme selection.
    """
    ctrl = DesktopController()

    ctrl.set_selected_programs(["83101", "83102", "83103", "83104", "83105"])

    with pytest.raises(ValueError, match="Maximum 5"):
        ctrl.set_selected_programs([
            "83101",
            "83102",
            "83103",
            "83104",
            "83105",
            "83108",
        ])

    assert ctrl._selected_programs == [
        "83101",
        "83102",
        "83103",
        "83104",
        "83105",
    ]


# ── spec 4.3: missing-StudentCount detection and snapshot support ─────────────

def test_any_exam_missing_student_count_detects_missing_unfiltered():
    ctrl = DesktopController()
    ctrl._courses = [_exam_course(None)]

    # No programmes selected, no periods loaded — still detected (file-load abort).
    assert ctrl.any_exam_missing_student_count() is True


def test_any_exam_missing_student_count_false_when_all_present():
    ctrl = DesktopController()
    ctrl._courses = [_exam_course(40)]

    assert ctrl.any_exam_missing_student_count() is False


def test_snapshot_and_restore_courses_round_trip():
    ctrl = DesktopController()
    ctrl._courses = [_exam_course(40)]
    snapshot = ctrl.snapshot_courses()

    ctrl._courses = [_exam_course(None, course_id="22222")]
    ctrl.restore_courses(snapshot)

    assert [c.id for c in ctrl._courses] == ["11111"]
    assert ctrl.any_exam_missing_student_count() is False
