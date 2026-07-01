"""
Unit tests: CLI --output path handling
--------------------------------------
Regression coverage for the fix that stopped main._resolve_output_path from
silently prepending an ``output/`` directory to user-provided paths.

The user passes --output explicitly, so the file must be written to exactly
that path:
  - a bare filename stays a bare filename (no output/ prefix)
  - output/schedules.txt must NOT become output/output/schedules.txt
"""

from pathlib import Path

import main


def test_resolve_output_path_keeps_bare_filename():
    assert main._resolve_output_path(Path("schedules.txt")) == Path("schedules.txt")


def test_resolve_output_path_does_not_double_prefix_output_dir():
    resolved = main._resolve_output_path(Path("output/schedules.txt"))
    assert resolved == Path("output/schedules.txt")
    assert "output/output" not in str(resolved)


def test_resolve_output_path_respects_absolute_path(tmp_path):
    target = tmp_path / "nested" / "schedules.txt"
    resolved = main._resolve_output_path(target)
    assert resolved == target
    # Parent directory is created so the later write succeeds.
    assert target.parent.is_dir()


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

    return {"programs": programs, "courses": courses, "periods": periods}


def test_run_cli_writes_to_exact_output_path(tmp_path):
    paths = _write_min_inputs(tmp_path)
    # An explicit nested path under tmp_path — must be written verbatim.
    output = tmp_path / "exact" / "schedules.txt"

    main._run_cli(
        [
            "--programs", str(paths["programs"]),
            "--courses", str(paths["courses"]),
            "--periods", str(paths["periods"]),
            "--output", str(output),
        ]
    )

    assert output.exists()
    # No accidental nesting of the requested directory name.
    assert not (tmp_path / "exact" / "exact").exists()
