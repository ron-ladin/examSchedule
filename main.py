"""
Entry Point: main.py
---------------------
Desktop GUI entry point for Syncademic (standalone PyQt6 app).

Usage:
    python main.py              ← launches the desktop GUI  (default)
    python main.py --cli ...    ← runs the batch CLI
    python main.py ...          ← runs the batch CLI, legacy-compatible mode

    Required:
        --programs  data/programs.txt   comma-separated 5-digit program IDs
        --courses   data/courses.txt
        --periods   data/dates.txt
        --output    output/schedules.txt

    Optional — Phase 3 (threshold filtering + sorting):
        --settings  data/settings.txt

    Optional — Feature 4 (classroom assignment):
        --classrooms  data/classrooms.txt
        --slots       data/slots.txt
        --proctor     data/proctors.txt
"""

import logging
import sys
from pathlib import Path

_CLI_MAX_COMBINATIONS = 10_000


def _resolve_output_path(output: Path) -> Path:
    """Honor the user-provided --output path exactly, creating its parent dir.

    The user explicitly passes --output, so we write to that path verbatim — a
    bare filename lands in the working directory, output/foo.txt lands in
    output/. We only ensure the parent directory exists so the write succeeds;
    we never rewrite the path the user asked for.
    """
    output = Path(output)
    if str(output.parent) not in ("", "."):
        output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _write_cli_proctor_report(output_path, schedules_by_period, courses_by_id):
    """Write the Feature 4 proctor report from in-memory schedules.

    Built directly from the generated schedules (not by re-parsing the exported
    text file) and — crucially — using the SAME combined "Schedule #N" numbering
    and structure as the exported schedules file. The schedules file is a
    Cartesian product across periods (one Schedule #N per combination), so the
    proctor report mirrors that exactly: one section per combined schedule, with
    a per-period sub-block inside, capped at the same combination limit.
    """
    from itertools import product as cartesian_product

    from src.engine.proctor_report import build_proctor_report

    period_keys = list(schedules_by_period.keys())
    schedule_lists = [schedules_by_period[key] for key in period_keys]

    sections: list[str] = []
    if period_keys and all(schedule_lists):
        for count, combo in enumerate(cartesian_product(*schedule_lists), 1):
            if count > _CLI_MAX_COMBINATIONS:
                break
            blocks = [f"=== Schedule #{count} ==="]
            for period_key, schedule in zip(period_keys, combo):
                report = build_proctor_report(schedule, courses_by_id)
                blocks.append(f"  [{period_key}]\n{report}")
            sections.append("\n".join(blocks))

    proctor_path = output_path.with_name(output_path.stem + "_proctor.txt")

    if not sections:
        proctor_path.write_text(
            "No schedules were generated, so no proctor report is available.\n",
            encoding="utf-8",
        )
    else:
        proctor_path.write_text("\n\n".join(sections), encoding="utf-8")

    logging.info("Proctor report written to %s", proctor_path.resolve())


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _run_gui() -> None:
    from PyQt6.QtWidgets import QApplication
    from src.ui.app import ExamSchedulerApp

    _configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Syncademic")
    window = ExamSchedulerApp()
    window.show()
    sys.exit(app.exec())


def _run_cli(argv: list[str] | None = None) -> None:
    import argparse
    from pathlib import Path

    from src.adapters.exact_conflict_strategy import ExactConflictStrategy
    from src.adapters.file_data_provider import FileDataProvider
    from src.adapters.readers.classroom_file_reader import ClassroomFileReader
    from src.adapters.readers.proctor_config_reader import ProctorConfigReader
    from src.adapters.readers.settings_file_reader import SettingsFileReader
    from src.adapters.readers.slots_file_reader import SlotsFileReader
    from src.adapters.text_file_exporter import TextFileExporter
    from src.domain.feature4_validator import Feature4Validator
    from src.domain.threshold_filter import ThresholdFilter
    from src.engine.app_controller import (
        AppController,
        CLASSROOM_VARIANT_MODE_FIRST,
    )
    from src.engine.schedule_generator import ScheduleGenerator

    _configure_logging()

    parser = argparse.ArgumentParser(description="Exam Scheduling System (CLI)")
    parser.add_argument("--programs", type=Path, required=True)
    parser.add_argument("--courses", type=Path, required=True)
    parser.add_argument("--periods", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--settings", type=Path, default=None)
    parser.add_argument("--classrooms", type=Path, default=None)
    parser.add_argument("--slots", type=Path, default=None)
    parser.add_argument("--proctor", type=Path, default=None)

    args = parser.parse_args(argv)
    args.output = _resolve_output_path(args.output)

    logging.info("Starting CLI generation...")

    data_provider = FileDataProvider(
        courses_path=args.courses,
        periods_path=args.periods,
        programs_path=args.programs,
    )

    selected_programs = data_provider.get_selected_programs()

    feature4_requested = any(
        value is not None
        for value in (args.classrooms, args.slots, args.proctor)
    )

    if feature4_requested and not all(
        value is not None
        for value in (args.classrooms, args.slots, args.proctor)
    ):
        parser.error(
            "Feature 4 requires all three arguments together: "
            "--classrooms, --slots, and --proctor."
        )

    # SAFEGUARD:
    # Never allow the CLI exporter to write an unbounded number of combinations.
    # This prevents runaway combinatorics from producing massive output files.
    #
    # Capture the final per-period schedules in memory (already filtered, room-
    # assigned and sorted by AppController). The file is written from this capture
    # and — crucially — so is the proctor report, instead of re-parsing the
    # exported text file. settings=None so the capture is NOT re-sorted here;
    # AppController already applied the sort config.
    from src.engine.generation_workers import _MemoryExporter

    exporter = _MemoryExporter(cap=_CLI_MAX_COMBINATIONS, settings=None)

    conflict_strategy = ExactConflictStrategy(selected_programs=selected_programs)
    generator = ScheduleGenerator(conflict_strategy=conflict_strategy)

    classrooms = []
    time_slots = []
    proctor_config = None

    if feature4_requested:
        classrooms = ClassroomFileReader(args.classrooms).read()
        time_slots = SlotsFileReader(args.slots).read()
        proctor_config = ProctorConfigReader(args.proctor).read()

        if not classrooms:
            parser.error(
                "Feature 4 requested, but no valid rooms were found in classrooms file."
            )

        if not time_slots:
            parser.error(
                "Feature 4 requested, but no valid time slots were found in slots file."
            )

        all_courses = data_provider.get_courses()
        if Feature4Validator.any_exam_missing_student_count(all_courses):
            parser.error(
                "Feature 4 requested, but at least one Exam course offering "
                "is missing StudentCount."
            )

    threshold_filter = None
    threshold_settings = None
    sorting_config = None

    if args.settings:
        settings = SettingsFileReader(args.settings).read()
        threshold_filter = ThresholdFilter()
        threshold_settings = settings.thresholds
        sorting_config = settings.sorting

    AppController(
        data_provider=data_provider,
        exporter=exporter,
        generator=generator,
        selected_programs=selected_programs,
        threshold_filter=threshold_filter,
        threshold_settings=threshold_settings,
        sorting_config=sorting_config,
        classrooms=classrooms,
        time_slots=time_slots,
        proctor_config=proctor_config,
        classroom_variant_mode=CLASSROOM_VARIANT_MODE_FIRST,
    ).run()

    # Write the schedules file from the captured in-memory results.
    TextFileExporter(
        output_path=args.output,
        max_combinations=_CLI_MAX_COMBINATIONS,
    ).export_schedules(exporter.schedules_by_period, exporter.courses_by_id)

    logging.info(
        "CLI generation completed successfully. Schedules written to %s "
        "(export capped at %s combinations).",
        args.output.resolve(),
        f"{_CLI_MAX_COMBINATIONS:,}",
    )

    if feature4_requested:
        _write_cli_proctor_report(
            args.output,
            exporter.schedules_by_period,
            exporter.courses_by_id,
        )


def _run_cli_safely(argv: list[str] | None = None) -> None:
    try:
        _run_cli(argv)
    except FileNotFoundError as exc:
        _configure_logging()
        logging.error("Configuration file missing: %s", exc)
        sys.exit(1)
    except Exception as exc:
        _configure_logging()
        logging.exception("Fatal CLI crash: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    argv = sys.argv[1:]

    if argv and argv[0] == "--cli":
        _run_cli_safely(argv[1:])
    elif argv:
        _run_cli_safely(argv)
    else:
        _run_gui()
