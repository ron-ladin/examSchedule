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

    # Sections are split on the "=== Schedule #N - <period> ===" headers.
    sections = [s for s in report.split("=== ") if s.strip()]

    # The report must contain one section per distinct per-period schedule,
    # matching the deduplicated reader output (no inflated/duplicated blocks).
    imported = ScheduleFileReader().read_with_metadata(paths["output"])
    expected_sections = sum(
        len(schedules) for schedules in imported.schedules_by_period.values()
    )
    assert len(sections) == expected_sections

    # No two schedule report bodies are byte-identical within a period.
    bodies_by_period: dict[str, list[str]] = {}
    for section in sections:
        header, _, body = section.partition("\n")
        # header looks like "Schedule #N - FALL - Aleph ==="
        period = header.split(" - ", 1)[1].rsplit(" ===", 1)[0]
        bodies_by_period.setdefault(period, []).append(body)

    for period, bodies in bodies_by_period.items():
        assert len(bodies) == len(set(bodies)), f"Duplicate report block in {period}"
