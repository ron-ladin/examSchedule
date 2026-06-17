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
        7. Passes all period iterators (NOT lists) to exporter.export_schedules().
        8. Logs progress using the logging module — no print() calls.

Notes:
    - Never import FileDataProvider, TextFileExporter, ExactConflictStrategy,
      or ScheduleGenerator here. This layer depends only on interfaces.
    - The iterator from generate_schedules MUST flow through to the exporter
      without being converted to a list.  Calling list() here would silently
      destroy the O(n) memory guarantee and break PaginatedExporter.
    - schedules_by_period maps period keys to Iterator[Schedule], not List.
      The exporter is responsible for consuming the iterator page by page.
"""

import logging
from collections.abc import Iterator

from src.domain.interfaces import IThresholdFilter
from src.domain.classroom import Classroom
from src.domain.proctor import ProctorConfig
from src.domain.schedule import Schedule
from src.domain.threshold import ThresholdSettings
from src.domain.time_slot import TimeSlot
from src.engine.classroom_assigner import ClassroomAssigner
from src.interfaces.i_data_provider import IDataProvider
from src.interfaces.i_output_exporter import IOutputExporter
from src.interfaces.i_schedule_generator import IScheduleGenerator


logger = logging.getLogger(__name__)


def _apply_filter(
    raw_iter: Iterator[Schedule],
    threshold_filter,
    threshold_settings,
    courses: list,
    selected_programs: list[str] | None = None,
) -> Iterator[Schedule]:
    # Accepts courses as a function argument so the value is captured
    # eagerly at call time — not by reference to the enclosing loop variable.
    return (
        s for s in raw_iter
        if threshold_filter.is_valid(s, courses, threshold_settings, selected_programs)
    )


CLASSROOM_VARIANT_MODE_ALL = "all"
CLASSROOM_VARIANT_MODE_FIRST = "first"


def _apply_classroom_assignment(
    raw_iter: Iterator[Schedule],
    courses: list,
    selected_programs: list[str],
    classrooms: list[Classroom],
    slots: list[TimeSlot],
    proctor_config: ProctorConfig,
    allow_unassigned: bool,
    classroom_variant_mode: str = CLASSROOM_VARIANT_MODE_ALL,
) -> Iterator[Schedule]:
    for schedule in raw_iter:
        # A date-only schedule is only a candidate. When Feature 4 is active,
        # the caller decides whether to expose all classroom/time-slot variants
        # or only the first one.
        #
        # "first" is used by normal Generate / Load Dates so those actions stay
        # focused on different date schedules and do not spend time expanding
        # every classroom variant. Load Variants uses ClassroomAssigner directly
        # for the currently displayed date schedule.
        if classroom_variant_mode == CLASSROOM_VARIANT_MODE_FIRST:
            yield from ClassroomAssigner.assign_variants(
                schedule,
                courses,
                selected_programs,
                classrooms,
                slots,
                proctor_config,
                allow_unassigned=allow_unassigned,
                max_options_per_day=1,
                max_options_per_schedule=1,
            )
        else:
            yield from ClassroomAssigner.assign_variants(
                schedule,
                courses,
                selected_programs,
                classrooms,
                slots,
                proctor_config,
                allow_unassigned=allow_unassigned,
            )


class AppController:

    def __init__(
        self,
        data_provider: IDataProvider,
        exporter: IOutputExporter,
        generator: IScheduleGenerator,
        selected_programs: list[str],
        threshold_filter: IThresholdFilter | None = None,
        threshold_settings: ThresholdSettings | None = None,
        classrooms: list[Classroom] | None = None,
        time_slots: list[TimeSlot] | None = None,
        proctor_config: ProctorConfig | None = None,
        allow_unassigned_classrooms: bool = False,
        classroom_variant_mode: str = CLASSROOM_VARIANT_MODE_ALL,
    ) -> None:
        self._data_provider = data_provider
        self._exporter = exporter
        self._generator = generator
        self._selected_programs = selected_programs
        self._threshold_filter = threshold_filter
        self._threshold_settings = threshold_settings
        self._classrooms = classrooms or []
        self._time_slots = time_slots or []
        self._proctor_config = proctor_config
        self._allow_unassigned_classrooms = allow_unassigned_classrooms
        self._classroom_variant_mode = classroom_variant_mode

    def run(self) -> None:
        logger.info("Starting exam schedule generation")
        logger.info("Selected programs: %s", self._selected_programs)

        all_courses = self._data_provider.get_courses()
        self._validate_selected_programs_exist(all_courses)

        exam_periods = self._data_provider.get_exam_periods()
        exam_periods = self._sort_exam_periods(exam_periods)

        courses_by_id = {course.id: course for course in all_courses}

        schedules_by_period: dict[str, Iterator[Schedule]] = {}
        seen_period_keys: set = set()

        for period in exam_periods:
            period_key = period.get_key()

            if period_key in seen_period_keys:
                raise ValueError(f"Duplicate exam period found: {period_key}")
            seen_period_keys.add(period_key)

            relevant_courses = [
                course for course in all_courses
                if course.is_relevant_for_period(self._selected_programs, period.semester)
            ]

            logger.info(
                "Period %s: %d relevant courses",
                period_key,
                len(relevant_courses),
            )

            if not relevant_courses:
                continue

            # Pass the lazy iterator directly — do NOT call list() here.
            # Converting to a list would materialise all schedules into RAM,
            # destroying the O(PAGE_SIZE) memory guarantee of PaginatedExporter
            # and defeating the entire purpose of the yield-based generator.
            raw_iter = self._generator.generate_schedules(relevant_courses, period)

            schedule_iter = raw_iter
            if self._threshold_filter is not None and self._threshold_settings is not None:
                schedule_iter = _apply_filter(
                    raw_iter,
                    self._threshold_filter,
                    self._threshold_settings,
                    relevant_courses,
                    self._selected_programs,
                )

            if self._classrooms and self._time_slots and self._proctor_config:
                schedule_iter = _apply_classroom_assignment(
                    schedule_iter,
                    relevant_courses,
                    self._selected_programs,
                    self._classrooms,
                    self._time_slots,
                    self._proctor_config,
                    self._allow_unassigned_classrooms,
                    self._classroom_variant_mode,
                )

            schedules_by_period[period_key] = schedule_iter

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
