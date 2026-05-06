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
    - No business logic here -- only wiring and CLI parsing.
    - No print() calls -- logging only.
"""
