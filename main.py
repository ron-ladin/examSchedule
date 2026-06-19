"""
Entry Point: main.py
---------------------
Desktop GUI entry point for Syncademic (standalone PyQt6 app).

Usage:
    python main.py              ← launches the desktop GUI  (default)
    python main.py --cli ...    ← runs the batch CLI

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


def _run_gui() -> None:
    from PyQt6.QtWidgets import QApplication
    from src.ui.app import ExamSchedulerApp

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("Syncademic")
    window = ExamSchedulerApp()
    window.show()
    sys.exit(app.exec())


def _run_cli() -> None:
    import argparse
    from pathlib import Path
    from src.adapters.exact_conflict_strategy import ExactConflictStrategy
    from src.adapters.file_data_provider import FileDataProvider
    from src.adapters.readers.classroom_file_reader import ClassroomFileReader
    from src.adapters.readers.proctor_config_reader import ProctorConfigReader
    from src.adapters.readers.settings_file_reader import SettingsFileReader
    from src.adapters.readers.slots_file_reader import SlotsFileReader
    from src.adapters.text_file_exporter import TextFileExporter
    from src.domain.threshold_filter import ThresholdFilter
    from src.engine.app_controller import AppController
    from src.engine.schedule_generator import ScheduleGenerator

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Exam Scheduling System (CLI)")
    parser.add_argument("--programs",    type=Path, required=True)
    parser.add_argument("--courses",     type=Path, required=True)
    parser.add_argument("--periods",     type=Path, required=True)
    parser.add_argument("--output",      type=Path, required=True)
    parser.add_argument("--settings",    type=Path, default=None)
    parser.add_argument("--classrooms",  type=Path, default=None)
    parser.add_argument("--slots",       type=Path, default=None)
    parser.add_argument("--proctor",     type=Path, default=None)
    args = parser.parse_args(sys.argv[2:])  # skip ["main.py", "--cli"]

    data_provider = FileDataProvider(
        courses_path=args.courses,
        periods_path=args.periods,
        programs_path=args.programs,
    )
    selected_programs = data_provider.get_selected_programs()
    exporter          = TextFileExporter(output_path=args.output, max_combinations=None)
    conflict_strategy = ExactConflictStrategy(selected_programs=selected_programs)
    generator         = ScheduleGenerator(conflict_strategy=conflict_strategy)

    classrooms     = ClassroomFileReader(args.classrooms).read() if args.classrooms else []
    time_slots     = SlotsFileReader(args.slots).read() if args.slots else []
    proctor_config = ProctorConfigReader(args.proctor).read() if args.proctor else None

    threshold_filter   = None
    threshold_settings = None
    sorting_config     = None
    if args.settings:
        settings           = SettingsFileReader(args.settings).read()
        threshold_filter   = ThresholdFilter()
        threshold_settings = settings.thresholds
        sorting_config     = settings.sorting

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
    ).run()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        _run_cli()
    else:
        _run_gui()
