"""
Desktop Controller
-------------------
Thin orchestration layer for the PyQt6 desktop UI.

Responsibilities:
    1. Hold in-memory state: courses, exam periods, selected programmes
    2. Load data from files using existing file readers (replace/append/update modes)
    3. Delegate schedule generation to the engine via the existing AppController
    4. Capture preview results in memory for display in the UI
    5. Support loading additional generated schedules in UI-sized batches
    6. Support Cartesian-product combined schedule navigation for the UI
    7. Export selected schedules to file via TextFileExporter

Notes:
    - This class is UI-facing. Never import PyQt6 here.
    - Uses InMemoryDataProvider to supply loaded data to the engine.
    - Does NOT modify src/engine/app_controller.py.
"""

import logging
from collections.abc import Callable, Iterator
from itertools import chain, islice
from pathlib import Path

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.adapters.in_memory_data_provider import InMemoryDataProvider
from src.adapters.readers.course_file_reader import CourseFileReader
from src.adapters.readers.exam_period_file_reader import ExamPeriodFileReader
from src.adapters.readers.program_selector_reader import ProgramSelectorReader
from src.adapters.text_file_exporter import TextFileExporter
from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.engine.app_controller import AppController as _EngineController
from src.engine.schedule_generator import ScheduleGenerator
from src.interfaces.i_output_exporter import IOutputExporter

logger = logging.getLogger(__name__)


# Maximum schedules loaded per period in each desktop UI batch.
# Kept as RESULT_CAP so existing UI/tests that import this name keep working.
RESULT_CAP: int = 200


# ── Private helper ────────────────────────────────────────────────────────────

class _MemoryExporter(IOutputExporter):
    """
    Captures generated schedules in memory instead of writing to disk.

    The first RESULT_CAP schedules per period are stored for immediate UI display.
    If more schedules exist, the remaining iterator is preserved so the UI can
    load the next batch later using DesktopController.load_more_schedules().
    """

    def __init__(self) -> None:
        self.schedules_by_period: dict[str, list[Schedule]] = {}
        self.courses_by_id: dict[str, Course] = {}
        self.truncated_periods: set[str] = set()
        self.remaining_iterators: dict[str, Iterator[Schedule]] = {}
        self.has_more_by_period: dict[str, bool] = {}

    def export_schedules(
        self,
        schedules_by_period: dict[str, Iterator[Schedule]],
        courses_by_id: dict[str, Course],
    ) -> None:
        self.courses_by_id = dict(courses_by_id)
        self.schedules_by_period.clear()
        self.truncated_periods.clear()
        self.remaining_iterators.clear()
        self.has_more_by_period.clear()

        for key, schedule_iter in schedules_by_period.items():
            preview = list(islice(schedule_iter, RESULT_CAP + 1))

            if len(preview) > RESULT_CAP:
                self.schedules_by_period[key] = preview[:RESULT_CAP]
                self.truncated_periods.add(key)
                self.has_more_by_period[key] = True
                self.remaining_iterators[key] = chain(
                    [preview[RESULT_CAP]],
                    schedule_iter,
                )
            else:
                self.schedules_by_period[key] = preview
                self.has_more_by_period[key] = False


# ── Public class ──────────────────────────────────────────────────────────────

class DesktopController:
    """
    Manages application state and orchestrates the scheduling pipeline
    for the standalone desktop UI.
    """

    def __init__(self) -> None:
        self._courses: list[Course] = []
        self._exam_periods: list[ExamPeriod] = []
        self._selected_programs: list[str] = []
        self._loaded_program_ids: list[str] = []
        self._truncated_periods: set[str] = set()
        self._remaining_schedule_iterators: dict[str, Iterator[Schedule]] = {}
        self._has_more_schedules: dict[str, bool] = {}

    # ── Data loading ──────────────────────────────────────────────────────────

    def load_courses(self, path: Path, mode: str = "replace") -> int:
        """
        Load courses from a file into memory.

        mode: "replace" | "append" | "update"
        Returns the total number of courses now in memory.
        """
        reader = CourseFileReader(Path(path))
        new_courses = reader.read()
        self._merge_by_key(self._courses, new_courses, mode, key_fn=lambda c: c.id)

        logger.info(
            "load_courses: mode=%s, loaded=%d, total=%d",
            mode,
            len(new_courses),
            len(self._courses),
        )
        return len(self._courses)

    def load_programs(self, path: Path) -> int:
        """
        Load programme IDs from a comma-separated programmes file.

        Returns the number of programme IDs loaded.
        """
        reader = ProgramSelectorReader(Path(path))
        self._loaded_program_ids = reader.read()

        logger.info(
            "load_programs: loaded=%d ids=%s",
            len(self._loaded_program_ids),
            self._loaded_program_ids,
        )
        return len(self._loaded_program_ids)

    def load_periods(self, path: Path, mode: str = "replace") -> int:
        """
        Load exam periods from a file into memory.

        mode: "replace" | "append" | "update"
        Returns the total number of periods now in memory.
        """
        reader = ExamPeriodFileReader(Path(path))
        new_periods = reader.read()
        self._merge_by_key(
            self._exam_periods,
            new_periods,
            mode,
            key_fn=lambda p: p.get_key(),
        )

        logger.info(
            "load_periods: mode=%s, loaded=%d, total=%d",
            mode,
            len(new_periods),
            len(self._exam_periods),
        )
        return len(self._exam_periods)

    def _merge_by_key(
        self,
        existing: list,
        new_items: list,
        mode: str,
        key_fn: Callable,
    ) -> None:
        """Apply replace / append / update merge strategy to an in-memory list."""
        if mode == "replace":
            existing.clear()
            existing.extend(new_items)
        elif mode == "append":
            existing.extend(new_items)
        elif mode == "update":
            key_to_idx: dict[str, int] = {
                key_fn(item): i for i, item in enumerate(existing)
            }
            for item in new_items:
                key = key_fn(item)
                if key in key_to_idx:
                    existing[key_to_idx[key]] = item
                else:
                    existing.append(item)
                    key_to_idx[key] = len(existing) - 1
        else:
            raise ValueError(
                f"Unknown merge mode: '{mode}'. Use replace, append, or update."
            )

    # ── State queries ─────────────────────────────────────────────────────────

    @property
    def courses(self) -> list[Course]:
        return list(self._courses)

    @property
    def has_courses(self) -> bool:
        return bool(self._courses)

    @property
    def has_periods(self) -> bool:
        return bool(self._exam_periods)

    @property
    def results_truncated(self) -> bool:
        """Return True if at least one period still has more schedules available."""
        return bool(self._truncated_periods)

    @property
    def max_ui_preview_results(self) -> int:
        """Return the maximum number of schedules loaded per UI batch."""
        return RESULT_CAP

    def has_more_schedules(self, period_key: str) -> bool:
        """Return True if more schedules can be loaded for the given period."""
        return self._has_more_schedules.get(period_key, False)

    def has_any_more_schedules(self) -> bool:
        """Return True if any period still has more schedules available."""
        return any(self._has_more_schedules.values())

    def get_programme_ids(self) -> list[str]:
        """
        Return programme IDs to display in the sidebar list.

        Prefers the explicitly loaded programs file; falls back to IDs
        derived from course offerings if no programs file has been loaded.
        """
        if self._loaded_program_ids:
            return list(self._loaded_program_ids)

        ids: set[str] = set()
        for course in self._courses:
            for offering in course.offerings:
                ids.add(offering.program_id)
        return sorted(ids)

    def get_exam_periods(self) -> list[ExamPeriod]:
        return list(self._exam_periods)

    def get_courses_by_programme(self, program_id: str) -> list[Course]:
        """Return all courses that have at least one offering for the given programme."""
        return [
            course
            for course in self._courses
            if any(offering.program_id == program_id for offering in course.offerings)
        ]

    # ── State mutation ────────────────────────────────────────────────────────

    def set_selected_programs(self, program_ids: list[str]) -> None:
        """Set which programmes to schedule, up to 5 programmes."""
        if len(program_ids) > 5:
            raise ValueError("Maximum 5 programmes may be selected.")
        self._selected_programs = list(program_ids)

    def update_exam_periods(self, periods: list[ExamPeriod]) -> None:
        """Replace in-memory periods with edited versions from the UI."""
        self._exam_periods = list(periods)

    # ── Generation ────────────────────────────────────────────────────────────

    def generate(self) -> tuple[dict[str, list[Schedule]], dict[str, Course], set[str]]:
        """
        Run the CSP engine and return
        (schedules_by_period, courses_by_id, truncated_periods).

        This method intentionally keeps returning 3 values for compatibility
        with the existing tests and UI flow. In addition, it stores the remaining
        schedule iterators internally so the UI can call load_more_schedules().
        """
        if not self._selected_programs:
            raise ValueError("No programmes selected. Select at least one programme.")
        if not self._courses:
            raise ValueError("No courses loaded. Load a courses file first.")
        if not self._exam_periods:
            raise ValueError("No exam periods loaded. Load a periods file first.")

        self._truncated_periods.clear()
        self._remaining_schedule_iterators.clear()
        self._has_more_schedules.clear()

        data_provider = InMemoryDataProvider(
            courses=self._courses,
            exam_periods=self._exam_periods,
            selected_programs=self._selected_programs,
        )
        conflict_strategy = ExactConflictStrategy(
            selected_programs=self._selected_programs
        )
        generator = ScheduleGenerator(conflict_strategy=conflict_strategy)
        memory_exporter = _MemoryExporter()

        engine = _EngineController(
            data_provider=data_provider,
            exporter=memory_exporter,
            generator=generator,
            selected_programs=self._selected_programs,
        )
        engine.run()

        self._truncated_periods = set(memory_exporter.truncated_periods)
        self._remaining_schedule_iterators = dict(memory_exporter.remaining_iterators)
        self._has_more_schedules = dict(memory_exporter.has_more_by_period)

        return (
            memory_exporter.schedules_by_period,
            memory_exporter.courses_by_id,
            set(memory_exporter.truncated_periods),
        )

    def load_more_schedules(
        self,
        period_key: str,
        limit: int | None = None,
    ) -> list[Schedule]:
        """
        Load the next UI-sized batch of schedules for a given period.

        Returns an empty list if no more schedules are available.
        """
        batch_size = limit or RESULT_CAP

        if not self._has_more_schedules.get(period_key, False):
            return []

        schedule_iter = self._remaining_schedule_iterators.get(period_key)
        if schedule_iter is None:
            self._has_more_schedules[period_key] = False
            self._truncated_periods.discard(period_key)
            return []

        batch = list(islice(schedule_iter, batch_size + 1))

        if len(batch) > batch_size:
            self._has_more_schedules[period_key] = True
            self._remaining_schedule_iterators[period_key] = chain(
                [batch[batch_size]],
                schedule_iter,
            )
            return batch[:batch_size]

        self._has_more_schedules[period_key] = False
        self._remaining_schedule_iterators.pop(period_key, None)
        self._truncated_periods.discard(period_key)
        return batch

    # ── Cartesian-product helpers for desktop UI ──────────────────────────────

    def get_combined_schedule_count(
        self,
        schedules_by_period: dict[str, list[Schedule]],
    ) -> int:
        """
        Return the number of currently loaded combined schedules.

        This is the Cartesian product size of the loaded schedules per period.
        It may grow after calling load_more_schedules() for one or more periods.
        """
        if not schedules_by_period:
            return 0

        total = 1
        for schedules in schedules_by_period.values():
            if not schedules:
                return 0
            total *= len(schedules)

        return total

    def get_combined_schedule_at(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        index: int,
    ) -> dict[str, Schedule]:
        """
        Return one combined schedule by Cartesian-product index.

        The returned dict maps period_key -> Schedule.
        This avoids materialising list(product(...)) in memory.
        """
        total = self.get_combined_schedule_count(schedules_by_period)
        if index < 0 or index >= total:
            raise IndexError(
                f"Combined schedule index {index} out of range for total {total}."
            )

        period_keys = list(schedules_by_period.keys())
        selected_indexes: dict[str, int] = {}
        remainder = index

        for period_key in reversed(period_keys):
            schedules = schedules_by_period[period_key]
            selected_indexes[period_key] = remainder % len(schedules)
            remainder //= len(schedules)

        return {
            period_key: schedules_by_period[period_key][selected_indexes[period_key]]
            for period_key in period_keys
        }

    # ── Export ────────────────────────────────────────────────────────────────

    def export(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        output_path: Path,
    ) -> None:
        """Write selected schedules to a text file using TextFileExporter."""
        courses_by_id = {course.id: course for course in self._courses}
        exporter = TextFileExporter(output_path=Path(output_path))
        exporter.export_schedules(schedules_by_period, courses_by_id)
        logger.info("Exported schedules to %s", output_path)
