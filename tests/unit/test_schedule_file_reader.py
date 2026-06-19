"""Unit tests for ScheduleFileReader."""

from datetime import date
from pathlib import Path

import pytest

from src.adapters.readers.schedule_file_reader import ScheduleFileReader


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


def test_empty_file_returns_empty_dict(tmp_path: Path) -> None:
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    assert ScheduleFileReader().read(f) == {}


def test_reads_real_output_file() -> None:
    path = Path("output/schedules.txt")
    if not path.exists():
        pytest.skip("output/schedules.txt not present")

    result = ScheduleFileReader().read(path)
    assert result
    for schedules in result.values():
        for sched in schedules:
            assert sched.assignments
