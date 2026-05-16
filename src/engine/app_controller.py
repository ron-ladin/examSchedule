"""
Core Engine: AppController
---------------------------
Orchestrates the full pipeline: data loading → schedule generation → export.

Constructor args:
    - data_provider    (IDataProvider)     : source of courses and exam periods
    - exporter         (IOutputExporter)   : destination for generated schedules
    - generator        (IScheduleGenerator): generates conflict-free schedules per period
    - selected_programs (List[str])        : pre-resolved program IDs for this run

Main method:
    - run() -> None
        1. Logs selected programs.
        2. Loads all courses and exam periods from the data provider.
        3. Validates that selected programs exist in the course data.
        4. Sorts exam periods by semester and moed.
        5. For each ExamPeriod, filters courses relevant to the selected programs
           and evaluation_type == "Exam".
        6. Calls generator.generate_schedules(courses, period) — receives a lazy iterator.
        7. Passes all period iterators to exporter.export_schedules().
        8. Logs progress using the logging module — no print() calls.

Notes:
    - Never import FileDataProvider, TextFileExporter, ExactConflictStrategy,
      or ScheduleGenerator here. This layer depends only on interfaces.
    - The iterator from generate_schedules must flow through to the exporter
      without being converted to a list.
"""

import logging
from typing import Dict, Iterable, List

from src.domain.schedule import Schedule
from src.interfaces.i_data_provider import IDataProvider
from src.interfaces.i_output_exporter import IOutputExporter
from src.interfaces.i_schedule_generator import IScheduleGenerator


logger = logging.getLogger(__name__)


class AppController:

    def __init__(
        self,
        data_provider: IDataProvider,
        exporter: IOutputExporter,
        generator: IScheduleGenerator,
        selected_programs: List[str],
    ) -> None:
        self._data_provider = data_provider
        self._exporter = exporter
        self._generator = generator
        self._selected_programs = selected_programs

    def run(self) -> None:
        logger.info("Starting exam schedule generation")
        logger.info("Selected programs: %s", self._selected_programs)

        all_courses = self._data_provider.get_courses()
        self._validate_selected_programs_exist(all_courses)

        exam_periods = self._data_provider.get_exam_periods()
        exam_periods = self._sort_exam_periods(exam_periods)

        courses_by_id = {course.id: course for course in all_courses}

        schedules_by_period: Dict[str, Iterable[Schedule]] = {}

        for period in exam_periods:
            period_key = period.get_key()

            if period_key in schedules_by_period:
                raise ValueError(f"Duplicate exam period found: {period_key}")

            relevant_courses = [
                course for course in all_courses
                if course.is_relevant_for_period(self._selected_programs, period.semester)
            ]

            logger.info(
                "Period %s: %d relevant courses",
                period_key,
                len(relevant_courses),
            )

            schedules_by_period[period_key] = self._generator.generate_schedules(
                relevant_courses,
                period,
            )

        self._exporter.export_schedules(schedules_by_period, courses_by_id)
        logger.info("Export complete")

    def _sort_exam_periods(self, exam_periods):
        semester_order = {"FALL": 1, "SPRI": 2, "SUMM": 3}
        moed_order = {"Aleph": 1, "Bet": 2, "Gimel": 3}

        return sorted(
            exam_periods,
            key=lambda period: (
                semester_order[period.semester],
                moed_order[period.moed],
            ),
        )

    def _validate_selected_programs_exist(self, courses) -> None:
        available_programs = {
            offering.program_id
            for course in courses
            for offering in course.offerings
        }

        missing_programs = [
            program_id
            for program_id in self._selected_programs
            if program_id not in available_programs
        ]

        if missing_programs:
            raise ValueError(
                f"Selected program ids do not exist in the course data: {missing_programs}"
            )