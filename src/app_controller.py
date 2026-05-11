import logging
from typing import Dict, Iterable
from src.domain.schedule import Schedule
from src.engine.schedule_generator import ScheduleGenerator
from src.interfaces.i_conflict_strategy import IConflictStrategy
from src.interfaces.i_data_provider import IDataProvider
from src.interfaces.i_output_exporter import IOutputExporter

logger = logging.getLogger(__name__)

class AppController:
    def __init__(
        self,
        data_provider: IDataProvider,
        exporter: IOutputExporter,
        conflict_strategy: IConflictStrategy,
    ) -> None:
        self._data_provider = data_provider
        self._exporter = exporter
        # Initialize the generator with the provided strategy
        self._generator = ScheduleGenerator(conflict_strategy)

    def run(self) -> None:
        logger.info("Starting exam schedule generation")

        selected_programs = self._data_provider.get_selected_programs()
        all_courses = self._data_provider.get_courses()
        exam_periods = self._data_provider.get_exam_periods()

        courses_by_id = {course.id: course for course in all_courses}
        schedules_by_period: Dict[str, Iterable[Schedule]] = {}

        for period in exam_periods:
            relevant_courses = [
                c for c in all_courses
                if c.is_relevant_for_period(selected_programs, period.semester)
            ]
            
            # The correct method name is generate_schedules
            schedules_by_period[period.get_key()] = self._generator.generate_schedules(
                relevant_courses, period
            )

        self._exporter.export_schedules(schedules_by_period, courses_by_id)
        logger.info("Export complete")