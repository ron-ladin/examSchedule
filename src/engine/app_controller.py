"""
Core Engine: AppController
---------------------------
Orchestrates the full pipeline: data loading -> schedule generation -> export.

Constructor args:
    - data_provider     (IDataProvider)     : source of courses, periods, programs
    - exporter          (IOutputExporter)   : destination for generated schedules
    - conflict_strategy (IConflictStrategy) : injected into ScheduleGenerator

Main method to implement:
    - run() -> None
        1. Calls data_provider.get_selected_programs() to get chosen program IDs.
        2. Calls data_provider.get_courses() and filters to selected programs
           and evaluation_type == "Exam".
        3. Calls data_provider.get_exam_periods() to get all exam windows.
        4. For each ExamPeriod, creates a ScheduleGenerator and calls
           generate_schedules(courses, period) -- receives a generator, not a list.
        5. Passes the generator stream to exporter.export_schedules().
        6. Logs progress using the logging module -- no print() calls.

Notes:
    - Never import FileDataProvider, TextFileExporter, or ExactConflictStrategy here.
      This layer depends only on interfaces.
    - The generator from ScheduleGenerator must flow to the exporter
      without being converted to a list.
"""


class AppController:
    pass
