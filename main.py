"""
Entry Point: main.py
---------------------
Desktop GUI entry point for Syncademic (standalone PyQt6 app).

Usage:
    python main.py              ← launches the desktop GUI  (default)
    python main.py --cli ...    ← runs the original CLI (backward compat)
        --cli --programs selected_programs.txt --courses courses.txt
             --periods exam_periods.txt --output schedules.txt
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
    from src.adapters.text_file_exporter import TextFileExporter
    from src.engine.app_controller import AppController
    from src.engine.schedule_generator import ScheduleGenerator

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Exam Scheduling System (CLI)")
    parser.add_argument("--programs", type=Path, required=True)
    parser.add_argument("--courses",  type=Path, required=True)
    parser.add_argument("--periods",  type=Path, required=True)
    parser.add_argument("--output",   type=Path, required=True)
    args = parser.parse_args(sys.argv[2:])  # skip ["main.py", "--cli"]

    data_provider = FileDataProvider(
        courses_path=args.courses,
        periods_path=args.periods,
        programs_path=args.programs,
    )
    selected_programs = data_provider.get_selected_programs()
    exporter          = TextFileExporter(output_path=args.output)
    conflict_strategy = ExactConflictStrategy(selected_programs=selected_programs)
    generator         = ScheduleGenerator(conflict_strategy=conflict_strategy)

    AppController(
        data_provider=data_provider,
        exporter=exporter,
        generator=generator,
        selected_programs=selected_programs,
    ).run()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        _run_cli()
    else:
        _run_gui()
