"""
Unit Tests: DesktopController
--------------------------------
Tests for the desktop UI orchestration layer.
All file I/O uses tmp_path; no PyQt6 imports.
"""

import logging
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

    schedules_by_period, courses_by_id, truncated = ctrl.generate()

    assert isinstance(schedules_by_period, dict)
    assert isinstance(courses_by_id, dict)
    assert isinstance(truncated, set)
    assert "11111" in courses_by_id
    assert not truncated


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

    schedules_by_period, _, _trunc = ctrl.generate()
    ctrl.export(schedules_by_period, out)

    assert out.exists()
    assert out.stat().st_size > 0


# ── full generation ───────────────────────────────────────────────────────────

def test_generate_returns_all_period_schedules_without_truncation(tmp_path):
    """
    Three obligatory courses in the same programme + a 4-week window produces
    10,626 valid schedules.

    The current domain logic includes Fridays and excludes Saturdays only.
    In the range 05-01-2026 to 31-01-2026 there are 27 calendar days,
    4 Saturdays, and therefore 23 valid exam dates.

    With 23 valid dates and 3 mutually-conflicting courses:
    23 * 22 * 21 = 10,626 schedules.

    Since desktop generation now computes all schedules up front, generate()
    should not return truncated periods and should return all schedules.
    """
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"

    cp.write_text(
        "Calculus\n"
        "11111\n"
        "Dr. Cohen\n"
        "83101, 1, FALL, Obligatory\n"
        "Exam\n"
        "$$$$\n"
        "Algorithms\n"
        "22222\n"
        "Dr. Levi\n"
        "83101, 1, FALL, Obligatory\n"
        "Exam\n"
        "$$$$\n"
        "Physics\n"
        "33333\n"
        "Dr. Bar\n"
        "83101, 1, FALL, Obligatory\n"
        "Exam\n",
        encoding="utf-8",
    )

    dp.write_text(
        "FALL, Aleph\n"
        "05-01-2026, 31-01-2026\n",
        encoding="utf-8",
    )

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])

    schedules_by_period, _, truncated = ctrl.generate()

    assert truncated == set(), "full generation should not truncate results"

    period = ctrl.get_exam_periods()[0]
    valid_dates_count = len(period.get_valid_dates())

    # Current business rule: Friday is allowed, Saturday is excluded.
    assert valid_dates_count == 23

    expected_count = (
        valid_dates_count
        * (valid_dates_count - 1)
        * (valid_dates_count - 2)
    )

    period_key = next(iter(schedules_by_period))
    assert len(schedules_by_period[period_key]) == expected_count


# ── duplicate-key warning ─────────────────────────────────────────────────────

def test_merge_by_key_update_warns_on_duplicate_key(caplog):
    """
    _merge_by_key 'update' mode must log a WARNING when new_items contains
    two entries with the same key, and keep only the last occurrence.
    """
    from src.domain.course import Course

    ctrl = DesktopController()

    item1 = Course(
        id="11111",
        name="Calculus",
        instructor="Dr. Cohen",
        evaluation_type="Exam",
    )
    item2 = Course(
        id="11111",
        name="Calculus v2",
        instructor="Dr. Smith",
        evaluation_type="Exam",
    )
    existing: list = []

    with caplog.at_level(logging.WARNING, logger="src.controller"):
        ctrl._merge_by_key(
            existing,
            [item1, item2],
            mode="update",
            key_fn=lambda c: c.id,
        )

    assert any(
        "duplicate key" in record.message.lower() and "11111" in record.message
        for record in caplog.records
    )
    assert len(existing) == 1
    assert existing[0].name == "Calculus v2"  # last occurrence wins


# ── stale results / failed regeneration ───────────────────────────────────────

def test_export_is_blocked_after_dates_change_even_if_regeneration_fails(tmp_path):
    """
    Old schedules must not be exportable after exam dates changed,
    even if the next generation attempt fails.

    This is a logic test, not a UI test:
    it verifies that DesktopController keeps stale state and blocks export.
    """
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"
    out = tmp_path / "out.txt"

    _write_courses(cp)
    _write_periods(dp)

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])

    schedules_by_period, _, _ = ctrl.generate()
    assert schedules_by_period

    ctrl.mark_results_stale()
    assert ctrl.results_stale is True

    # Simulate a failed generation attempt after the date change.
    ctrl.set_selected_programs([])

    with pytest.raises(ValueError, match="No programmes selected"):
        ctrl.generate()

    # Failed generation must NOT clear stale state.
    assert ctrl.results_stale is True

    with pytest.raises(ValueError, match="Cannot export stale schedules"):
        ctrl.export(schedules_by_period, out)

    assert not out.exists()


def test_export_is_blocked_after_courses_reload(tmp_path):
    """
    Old schedules must not be exportable after courses are reloaded.

    Course data changes can change relevant offerings, course names, requirements,
    or conflicts. Therefore loading courses after a successful generation must
    mark existing results as stale and block export until regeneration succeeds.
    """
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"
    out = tmp_path / "out.txt"

    _write_courses(cp)
    _write_periods(dp)

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])

    schedules_by_period, _, _ = ctrl.generate()
    assert schedules_by_period
    assert ctrl.results_stale is False

    ctrl.load_courses(cp, mode="replace")

    assert ctrl.results_stale is True

    with pytest.raises(ValueError, match="Cannot export stale schedules"):
        ctrl.export(schedules_by_period, out)

    assert not out.exists()


def test_successful_generation_clears_stale_state(tmp_path):
    """
    If the user generates schedules successfully after dates changed,
    the new schedules are valid again and stale state should be cleared.
    """
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"

    _write_courses(cp)
    _write_periods(dp)

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])

    ctrl.mark_results_stale()
    assert ctrl.results_stale is True

    schedules_by_period, _, _ = ctrl.generate()

    assert schedules_by_period
    assert ctrl.results_stale is False


def test_export_allowed_when_results_are_not_stale(tmp_path):
    """
    Normal export should still work after a successful generation.
    This makes sure the stale guard does not break valid exports.
    """
    cp = tmp_path / "courses.txt"
    dp = tmp_path / "dates.txt"
    out = tmp_path / "out.txt"

    _write_courses(cp)
    _write_periods(dp)

    ctrl = DesktopController()
    ctrl.load_courses(cp)
    ctrl.load_periods(dp)
    ctrl.set_selected_programs(["83101"])

    schedules_by_period, _, _ = ctrl.generate()

    assert ctrl.results_stale is False

    ctrl.export(schedules_by_period, out)

    assert out.exists()
    assert out.stat().st_size > 0
