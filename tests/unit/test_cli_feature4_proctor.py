"""
Integration test: CLI Feature 4 proctor report
-----------------------------------------------
Drives main._run_cli with Feature 4 inputs across two exam periods, where the
exported combined schedules file is a Cartesian product (so each per-period
schedule is written into many ``Schedule #N`` blocks).

Verifies the generated ``*_proctor.txt``:
  - is created next to the schedules output
  - contains no duplicated period schedule blocks (relies on the
    ScheduleFileReader per-period deduplication fix)
"""

from pathlib import Path

import main
from src.adapters.readers.schedule_file_reader import ScheduleFileReader


def _write_inputs(tmp_path: Path) -> dict[str, Path]:
    programs = tmp_path / "programs.txt"
    programs.write_text("83101", encoding="utf-8")

    courses = tmp_path / "courses.txt"
    courses.write_text(
        "Calculus\n"
        "11111\n"
        "Dr. Cohen\n"
        "83101, 1, FALL, Obligatory, 30\n"
        "Exam\n",
        encoding="utf-8",
    )

    # Two periods, each with multiple date options -> Cartesian-product export.
    periods = tmp_path / "periods.txt"
    periods.write_text(
        "FALL, Aleph\n"
        "05-01-2026, 06-01-2026\n"
        "$$$$\n"
        "FALL, Bet\n"
        "12-01-2026, 13-01-2026\n",
        encoding="utf-8",
    )

    classrooms = tmp_path / "classrooms.txt"
    classrooms.write_text("$$$$\nRoom 1\n50\n", encoding="utf-8")

    slots = tmp_path / "slots.txt"
    slots.write_text("$$$$\n9:00\n$$$$\n", encoding="utf-8")

    proctor = tmp_path / "proctor.txt"
    proctor.write_text("1:20\n", encoding="utf-8")

    output = tmp_path / "schedules.txt"

    return {
        "programs": programs,
        "courses": courses,
        "periods": periods,
        "classrooms": classrooms,
        "slots": slots,
        "proctor": proctor,
        "output": output,
    }


def test_cli_feature4_writes_nonduplicated_proctor_report(tmp_path):
    paths = _write_inputs(tmp_path)

    main._run_cli(
        [
            "--programs", str(paths["programs"]),
            "--courses", str(paths["courses"]),
            "--periods", str(paths["periods"]),
            "--output", str(paths["output"]),
            "--classrooms", str(paths["classrooms"]),
            "--slots", str(paths["slots"]),
            "--proctor", str(paths["proctor"]),
        ]
    )

    proctor_path = paths["output"].with_name(paths["output"].stem + "_proctor.txt")
    assert proctor_path.exists()

    report = proctor_path.read_text(encoding="utf-8")
    assert report.strip()  # non-empty

    schedules_text = paths["output"].read_text(encoding="utf-8")

    # The proctor report must mirror the combined "Schedule #N" numbering of the
    # exported schedules file (one section per Cartesian-product combination),
    # not a per-period numbering. Count the headers in each and compare.
    schedule_blocks = schedules_text.count("Schedule #")
    proctor_sections = report.count("=== Schedule #")
    assert proctor_sections == schedule_blocks > 0

    # Numbering must be the same combined 1..N sequence in both files.
    for n in range(1, schedule_blocks + 1):
        assert f"Schedule #{n}:" in schedules_text
        assert f"=== Schedule #{n} ===" in report

    # Each combined section carries a per-period sub-block for every period.
    imported = ScheduleFileReader().read_with_metadata(paths["output"])
    for period_key in imported.schedules_by_period:
        assert f"[{period_key}]" in report


def _write_capacity_shortfall_inputs(tmp_path: Path) -> dict[str, Path]:
    """Feature 4 inputs where the exam (60 students) cannot fit the only room (10)."""
    programs = tmp_path / "programs.txt"
    programs.write_text("83101", encoding="utf-8")

    courses = tmp_path / "courses.txt"
    courses.write_text(
        "Calculus\n"
        "11111\n"
        "Dr. Cohen\n"
        "83101, 1, FALL, Obligatory, 60\n"
        "Exam\n",
        encoding="utf-8",
    )

    periods = tmp_path / "periods.txt"
    periods.write_text("FALL, Aleph\n05-01-2026, 06-01-2026\n", encoding="utf-8")

    classrooms = tmp_path / "classrooms.txt"
    classrooms.write_text("$$$$\nRoom 1\n10\n", encoding="utf-8")  # too small for 60

    slots = tmp_path / "slots.txt"
    slots.write_text("$$$$\n9:00\n$$$$\n", encoding="utf-8")

    proctor = tmp_path / "proctor.txt"
    proctor.write_text("1:20\n", encoding="utf-8")

    return {
        "programs": programs,
        "courses": courses,
        "periods": periods,
        "classrooms": classrooms,
        "slots": slots,
        "proctor": proctor,
        "output": tmp_path / "schedules.txt",
    }


def _cli_feature4_args(paths: dict[str, Path]) -> list[str]:
    return [
        "--programs", str(paths["programs"]),
        "--courses", str(paths["courses"]),
        "--periods", str(paths["periods"]),
        "--output", str(paths["output"]),
        "--classrooms", str(paths["classrooms"]),
        "--slots", str(paths["slots"]),
        "--proctor", str(paths["proctor"]),
    ]


def test_cli_capacity_shortfall_drops_schedules_without_allow_unassigned(tmp_path):
    """Without --allow-unassigned a hard capacity shortfall yields no schedules."""
    paths = _write_capacity_shortfall_inputs(tmp_path)

    main._run_cli(_cli_feature4_args(paths))

    schedules_text = paths["output"].read_text(encoding="utf-8")
    assert schedules_text.count("Schedule #") == 0


def test_cli_allow_unassigned_keeps_schedules_with_unassigned_exams(tmp_path):
    """With --allow-unassigned the same shortfall exports schedules, exams unassigned."""
    paths = _write_capacity_shortfall_inputs(tmp_path)

    main._run_cli(_cli_feature4_args(paths) + ["--allow-unassigned"])

    schedules_text = paths["output"].read_text(encoding="utf-8")
    assert schedules_text.count("Schedule #") > 0
    # The oversized exam (60 students) is reported as unassigned rather than dropped.
    assert "Unassigned classroom students: 60" in schedules_text
