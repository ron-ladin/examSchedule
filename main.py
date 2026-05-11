"""
Entry Point: main.py
---------------------
CLI entry point for the Exam Scheduling System.

Responsibilities:
    1. Parse CLI arguments using argparse:
           --programs  : path to selected_programs.txt
           --courses   : path to courses.txt
           --periods   : path to exam_periods.txt
           --output    : path to output file (e.g. schedules.txt)
    2. Instantiate concrete adapters:
           FileDataProvider, TextFileExporter, ExactConflictStrategy
    3. Instantiate AppController with the adapters injected.
    4. Call controller.run() to execute the full pipeline.
    5. Configure logging (level=INFO) before running.

Usage:
    python main.py --programs selected_programs.txt --courses courses.txt
                   --periods exam_periods.txt --output schedules.txt

Notes:
    - All paths must be handled as pathlib.Path objects.
    - No business logic here — only wiring and CLI parsing.
    - No print() calls — logging only.
"""

import argparse
import logging
from pathlib import Path

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.adapters.file_data_provider import FileDataProvider
from src.adapters.text_file_exporter import TextFileExporter
from src.engine.app_controller import AppController


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Exam Scheduling System")
    parser.add_argument("--programs", type=Path, required=True, help="Path to selected_programs.txt")
    parser.add_argument("--courses", type=Path, required=True, help="Path to courses.txt")
    parser.add_argument("--periods", type=Path, required=True, help="Path to exam_periods.txt")
    parser.add_argument("--output", type=Path, required=True, help="Path to output schedules file")
    args = parser.parse_args()

    data_provider = FileDataProvider(
        courses_path=args.courses,
        periods_path=args.periods,
        programs_path=args.programs,
    )
    exporter = TextFileExporter(output_path=args.output)
    conflict_strategy = ExactConflictStrategy()

    controller = AppController(
        data_provider=data_provider,
        exporter=exporter,
        conflict_strategy=conflict_strategy,
    )
    controller.run()


if __name__ == "__main__":
    main()
