"""
Core Engine: AppController
---------------------------
Orchestrates the full pipeline: data loading → schedule generation → export.

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
           generate_schedules(courses, period) — receives a generator (not a list).
        5. Passes the generator stream to exporter.export_schedules().
        6. Logs progress using the logging module — no print() calls.

Notes:
    - Never import FileDataProvider, TextFileExporter, or ExactConflictStrategy here.
      This layer depends only on interfaces.
    - The generator from ScheduleGenerator must flow through to the exporter
      without being converted to a list.
"""

import logging
from typing import Dict, Iterable

from src.domain.schedule import Schedule
from src.engine.schedule_generator import ScheduleGenerator
from src.interfaces.i_conflict_strategy import IConflictStrategy
from src.interfaces.i_data_provider import IDataProvider
from src.interfaces.i_output_exporter import IOutputExporter


logger = logging.getLogger(__name__)


class AppController:
    # This class connects all the parts of the system together.
    # It does not contain business logic — it just calls the right components in the right order.

    def __init__(
        self,
        data_provider: IDataProvider,
        exporter: IOutputExporter,
        conflict_strategy: IConflictStrategy,
    ) -> None:
        self._data_provider = data_provider
        self._exporter = exporter
        # One shared instance is safe — ScheduleGenerator is stateless between calls
        self._generator = ScheduleGenerator(conflict_strategy)

    def run(self) -> None:
        # Step 1: find out which programs the user selected
        logger.info("Starting exam schedule generation")

        selected_programs = self._data_provider.get_selected_programs()
        logger.info("Selected programs: %s", selected_programs)

        # Step 2: load all courses and exam periods from the data source
        all_courses = self._data_provider.get_courses()
        exam_periods = self._data_provider.get_exam_periods()

        # Build a dict for fast course lookup by ID (used later by the exporter)
        courses_by_id = {course.id: course for course in all_courses}

        # Step 3: for each exam period, generate all valid schedules
        schedules_by_period: Dict[str, Iterable[Schedule]] = {}
        for period in exam_periods:
            # Keep only courses that have exams and belong to the selected programs
            relevant_courses = [
                c for c in all_courses
                if c.is_relevant_for_period(selected_programs, period.semester)
            ]
            logger.info("Period %s: %d relevant courses", period.get_key(), len(relevant_courses))

            # generate_schedules returns a lazy iterator — no schedules are computed yet
            schedules_by_period[period.get_key()] = self._generator.generate_schedules(
                relevant_courses, period
            )

        # Step 4: pass everything to the exporter, which writes the output file
        self._exporter.export_schedules(schedules_by_period, courses_by_id)
        logger.info("Export complete")
