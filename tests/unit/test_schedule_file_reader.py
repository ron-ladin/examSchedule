"""Unit tests for ScheduleFileReader."""

from datetime import date
from pathlib import Path

import pytest

from src.adapters.readers.schedule_file_reader import ScheduleFileReader


_MAX_SAFE_REAL_OUTPUT_BYTES = 10 * 1024 * 1024


_SAMPLE = """\
Schedule #1:
  [FALL - Aleph]
  - Physics 1 | Course ID: 83102 | Date: 29-01-2026 | Instructor: Prof. A
  - Calculus 1 | Course ID: 83112 | Date: 04-02-2026 | Instructor: Dr. B

Schedule #2:
  [FALL - Aleph]
  - Physics 1 | Course ID: 83102 | Date: 30-01-2026 | Instructor: Prof. A
  - Calculus 1 | Course ID: 83112 | Date: 05-02-2026 | Instructor: Dr. B

"""

_MULTI_PERIOD = """\
Schedule #1:
  [FALL - Aleph]
  - Physics 1 | Course ID: 83102 | Date: 29-01-2026 | Instructor: Prof. A
  [FALL - Bet]
  - Physics 1 | Course ID: 83102 | Date: 10-04-2026 | Instructor: Prof. A

"""


def test_reads_single_period_two_schedules(tmp_path: Path) -> None:
    f = tmp_path / "schedules.txt"
    f.write_text(_SAMPLE, encoding="utf-8")

    result = ScheduleFileReader().read(f)

    assert set(result.keys()) == {"FALL - Aleph"}
    schedules = result["FALL - Aleph"]
    assert len(schedules) == 2

    assert schedules[0].assignments == {
        "83102": date(2026, 1, 29),
        "83112": date(2026, 2, 4),
    }
    assert schedules[1].assignments["83102"] == date(2026, 1, 30)


def test_reads_multiple_periods(tmp_path: Path) -> None:
    f = tmp_path / "schedules.txt"
    f.write_text(_MULTI_PERIOD, encoding="utf-8")

    result = ScheduleFileReader().read(f)

    assert "FALL - Aleph" in result
    assert "FALL - Bet" in result
    assert result["FALL - Aleph"][0].assignments["83102"] == date(2026, 1, 29)
    assert result["FALL - Bet"][0].assignments["83102"] == date(2026, 4, 10)


def test_period_key_round_trip_normalizes_display_semesters(tmp_path: Path) -> None:
    """Period keys from display names (SPRING/SUMMER) must match ExamPeriod.get_key()."""
    content = """\
Schedule #1:
  [SPRING - Aleph]
  - Physics 1 | Course ID: 83102 | Date: 29-01-2026 | Instructor: Prof. A

Schedule #2:
  [SUMMER - Bet]
  - Calculus 1 | Course ID: 83112 | Date: 10-06-2026 | Instructor: Dr. B

"""
    f = tmp_path / "schedules.txt"
    f.write_text(content, encoding="utf-8")

    result = ScheduleFileReader().read(f)

    assert "SPRI - Aleph" in result, f"Expected 'SPRI - Aleph', got keys: {list(result)}"
    assert "SUMM - Bet" in result, f"Expected 'SUMM - Bet', got keys: {list(result)}"
    assert "SPRING - Aleph" not in result
    assert "SUMMER - Bet" not in result


def test_multi_period_cartesian_export_deduplicates_repeated_period_schedules(
    tmp_path: Path,
) -> None:
    """An exported combined file repeats each per-period schedule across the
    Cartesian product of periods. The reader must keep each distinct per-period
    schedule only once, while preserving the distinct schedules of other periods.

    Here FALL - Aleph has a single schedule (A1) that repeats in every combined
    block, while FALL - Bet has two distinct schedules (B1, B2).
    """
    content = """\
Schedule #1:
  [FALL - Aleph]
  - Physics 1 | Course ID: 83102 | Date: 29-01-2026 | Instructor: Prof. A
  [FALL - Bet]
  - Calculus 1 | Course ID: 83112 | Date: 10-04-2026 | Instructor: Dr. B

Schedule #2:
  [FALL - Aleph]
  - Physics 1 | Course ID: 83102 | Date: 29-01-2026 | Instructor: Prof. A
  [FALL - Bet]
  - Calculus 1 | Course ID: 83112 | Date: 11-04-2026 | Instructor: Dr. B

"""
    f = tmp_path / "schedules.txt"
    f.write_text(content, encoding="utf-8")

    result = ScheduleFileReader().read(f)

    # Repeated period schedule appears only once.
    assert len(result["FALL - Aleph"]) == 1
    assert result["FALL - Aleph"][0].assignments["83102"] == date(2026, 1, 29)

    # The other period keeps both distinct schedules, in order.
    assert len(result["FALL - Bet"]) == 2
    assert result["FALL - Bet"][0].assignments["83112"] == date(2026, 4, 10)
    assert result["FALL - Bet"][1].assignments["83112"] == date(2026, 4, 11)


def test_empty_file_returns_empty_dict(tmp_path: Path) -> None:
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    assert ScheduleFileReader().read(f) == {}


def test_reads_real_output_file(tmp_path: Path) -> None:
    """Round-trip a realistic exported file.

    Self-contained: writes an exported-shape file and reads it back, so the test
    always runs instead of silently skipping when output/schedules.txt is absent.
    """
    path = tmp_path / "schedules.txt"
    path.write_text(_SAMPLE + _MULTI_PERIOD, encoding="utf-8")

    assert path.stat().st_size <= _MAX_SAFE_REAL_OUTPUT_BYTES

    result = ScheduleFileReader().read(path)
    assert result
    for schedules in result.values():
        for sched in schedules:
            assert sched.assignments
