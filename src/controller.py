"""
Desktop Controller
-------------------
Thin orchestration layer for the PyQt6 desktop UI.

Responsibilities:
    1. Hold in-memory state: courses, exam periods, selected programmes
    2. Load data from files using existing file readers (replace/append/update modes)
    3. Delegate schedule generation to the engine via the existing AppController
    4. Capture preview results in memory for display in the UI
    5. Support Cartesian-product combined schedule navigation for the UI
    6. Export selected schedules to file via TextFileExporter

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
from src.adapters.readers.settings_file_reader import SettingsFileReader
from src.adapters.text_file_exporter import TextFileExporter
from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.domain.semester import normalize_semester
from src.domain.settings import Settings
from src.domain.sorting import SortingConfig
from src.domain.sorting_engine import SortingEngine
from src.domain.threshold import ThresholdSettings
from src.domain.threshold_filter import ThresholdFilter
from src.engine.app_controller import AppController as _EngineController
from src.engine.schedule_generator import ScheduleGenerator
from src.interfaces.i_output_exporter import IOutputExporter

logger = logging.getLogger(__name__)


# Kept for backward compatibility with existing UI/tests that import this name.
# Full generation uses cap=None, so this value is only used by legacy helpers.
RESULT_BATCH_SIZE: int = 1000
RESULT_CAP: int = RESULT_BATCH_SIZE


class _MemoryExporter(IOutputExporter):
    """
    Captures generated schedules in memory instead of writing to disk.

    cap=None means full generation:
        collect all schedules for each period.

    cap=<number> means legacy batched generation:
        collect only cap schedules per period and mark truncated periods.
    """

    def __init__(
        self,
        cap: int | None = None,
        offset_by_period: dict[str, int] | None = None,
        only_period_keys: set[str] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._cap = cap
        self._offset_by_period = offset_by_period or {}
        self._only_period_keys = only_period_keys
        self._settings = settings

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

        courses_list = list(courses_by_id.values())

        for key, schedule_iter in schedules_by_period.items():
            if self._only_period_keys is not None and key not in self._only_period_keys:
                continue

            offset = self._offset_by_period.get(key, 0)

            if self._cap is None:
                collected = list(islice(schedule_iter, offset, None))
                self.schedules_by_period[key] = self._sort(collected, courses_list)
                self.has_more_by_period[key] = False
                continue

            batch = list(islice(schedule_iter, offset, offset + self._cap + 1))

            if len(batch) > self._cap:
                self.schedules_by_period[key] = self._sort(batch[: self._cap], courses_list)
                self.truncated_periods.add(key)
                self.has_more_by_period[key] = True

                self.remaining_iterators[key] = chain(
                    [batch[self._cap]],
                    schedule_iter,
                )
            else:
                self.schedules_by_period[key] = self._sort(batch, courses_list)
                self.has_more_by_period[key] = False

    def _sort(self, schedules: list[Schedule], courses: list[Course]) -> list[Schedule]:
        if self._settings and self._settings.sorting.rules:
            return SortingEngine.sort(schedules, courses, self._settings.sorting)
        return schedules



def _run_generation_process(
    result_queue,
    courses: "list[Course]",
    exam_periods: "list[ExamPeriod]",
    selected_programs: "list[str]",
    settings: "Settings | None" = None,
    cap: "int | None" = None,
    period_key: "str | None" = None,
    offset: int = 0,
) -> None:
    """
    Entry point for multiprocessing.Process-based schedule generation.

    Puts (True, schedules_by_period, courses_by_id, truncated_periods) on success
    or (False, error_message) on failure.

    Default behavior:
        cap=None -> generate all schedules up front.

    Optional legacy batching:
        cap=<number>, period_key=<key>, offset=<already loaded>.
    """
    try:
        active_settings = settings or Settings(
            thresholds=ThresholdSettings(),
            sorting=SortingConfig(),
        )

        data_provider = InMemoryDataProvider(
            courses=courses,
            exam_periods=exam_periods,
            selected_programs=selected_programs,
        )
        conflict_strategy = ExactConflictStrategy(selected_programs=selected_programs)
        generator = ScheduleGenerator(conflict_strategy=conflict_strategy)

        memory_exporter = _MemoryExporter(
            cap=cap,
            offset_by_period={period_key: offset} if period_key else None,
            only_period_keys={period_key} if period_key else None,
            settings=active_settings,
        )

        engine = _EngineController(
            data_provider=data_provider,
            exporter=memory_exporter,
            generator=generator,
            selected_programs=selected_programs,
            threshold_filter=ThresholdFilter(),
            threshold_settings=active_settings.thresholds,
        )
        engine.run()

        result_queue.put(
            (
                True,
                dict(memory_exporter.schedules_by_period),
                dict(memory_exporter.courses_by_id),
                memory_exporter.truncated_periods,
            )
        )
    except Exception as exc:
        logger.exception("Generation process failed")
        result_queue.put((False, str(exc)))


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
        self._remaining_schedule_iterators: dict[str, Iterator[Schedule]] = {}
        self._has_more_schedules: dict[str, bool] = {}
        self._iterator_overflows: dict[str, Schedule] = {}
        self._results_stale: bool = False
        self._settings: Settings = Settings(
            thresholds=ThresholdSettings(),
            sorting=SortingConfig(),
        )

        # Cache of the last threshold-valid results, kept so a sort-only change
        # can re-rank in place instead of regenerating from scratch.
        self._last_results: dict[str, list[Schedule]] | None = None

    @property
    def settings(self) -> Settings:
        return self._settings

    def apply_sort(self, config: SortingConfig) -> None:
        """Store a new sort config immediately on sort-list change (§281).

        Preserves existing thresholds. Called live — does NOT restart generation.
        """
        self._settings = Settings(thresholds=self._settings.thresholds, sorting=config)
        logger.info("apply_sort: %d active rules", len(config.rules))

    def apply_settings(self, settings: Settings) -> None:
        """Persist the full settings object (thresholds + sort) from the dialog OK path."""
        self._settings = settings
        logger.info(
            "apply_settings: thresholds=%d active, sort=%d rules",
            sum(1 for e in settings.thresholds.entries if e.enabled),
            len(settings.sorting.rules),
        )

    def load_settings(self, path: Path) -> None:
        """Load settings from a file and apply them (§1.1 CLI path)."""
        settings = SettingsFileReader(Path(path)).read()
        self.apply_settings(settings)

    def load_courses(self, path: Path, mode: str = "replace") -> int:
        """
        Load courses from a file into memory.

        mode: "replace" | "append" | "update"
        Returns the total number of courses now in memory.
        """
        reader = CourseFileReader(Path(path))
        new_courses = reader.read()

        if mode == "update":
            self._update_merge_courses(new_courses)
        else:
            self._merge_by_key(self._courses, new_courses, mode, key_fn=lambda c: c.id)

        self.mark_results_stale()

        logger.info(
            "load_courses: mode=%s, loaded=%d, total=%d",
            mode,
            len(new_courses),
            len(self._courses),
        )
        return len(self._courses)

    def _update_merge_courses(self, new_courses: list[Course]) -> None:
        """Update mode: merge offerings into existing courses; add unknown courses."""
        existing_by_id: dict[str, Course] = {c.id: c for c in self._courses}

        for new_course in new_courses:
            if new_course.id in existing_by_id:
                existing = existing_by_id[new_course.id]
                existing_keys = {
                    (o.program_id, o.year, normalize_semester(o.semester))
                    for o in existing.offerings
                }

                for offering in new_course.offerings:
                    key = (
                        offering.program_id,
                        offering.year,
                        normalize_semester(offering.semester),
                    )

                    if key not in existing_keys:
                        existing.add_offering(offering)
                        existing_keys.add(key)
            else:
                self._courses.append(new_course)
                existing_by_id[new_course.id] = new_course

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

        self.mark_results_stale()

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
            seen_new: set[str] = set()

            for item in new_items:
                key = key_fn(item)

                if key in seen_new:
                    logger.warning(
                        "_merge_by_key: duplicate key '%s' in new items — "
                        "last occurrence kept",
                        key,
                    )

                seen_new.add(key)

                if key in key_to_idx:
                    existing[key_to_idx[key]] = item
                else:
                    existing.append(item)
                    key_to_idx[key] = len(existing) - 1
        else:
            raise ValueError(
                f"Unknown merge mode: '{mode}'. Use replace, append, or update."
            )

    @property
    def courses(self) -> list[Course]:
        return list(self._courses)

    @property
    def results_stale(self) -> bool:
        """Return True when generated schedules no longer match current input data."""
        return self._results_stale

    def mark_results_stale(self) -> None:
        """Mark generated schedules as stale after input data was edited."""
        self._results_stale = True
        self._last_results = None

    def clear_results_stale(self) -> None:
        """Mark generated schedules as fresh after successful regeneration."""
        self._results_stale = False

    @property
    def has_courses(self) -> bool:
        return bool(self._courses)

    @property
    def has_periods(self) -> bool:
        return bool(self._exam_periods)

    def has_more_schedules(self, period_key: str) -> bool:
        """Return True if more schedules can be loaded for the given period."""
        return self._has_more_schedules.get(period_key, False)

    def has_any_more_schedules(self) -> bool:
        """Return True if any period still has more schedules available."""
        return any(self._has_more_schedules.values())

    def set_has_more_for_period(self, period_key: str, has_more: bool) -> None:
        """
        Set whether more schedules are available for one period.

        This keeps UI code from mutating controller internals directly.
        """
        self._has_more_schedules[period_key] = has_more

    def on_generation_succeeded(self, truncated_periods: set[str] | None = None) -> None:
        """
        Update controller state after a successful generation run.

        This is used by both in-process and subprocess-based generation flows.
        """
        self.clear_results_stale()
        self.set_has_more_from_truncated(truncated_periods or set())

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

    def set_selected_programs(self, program_ids: list[str]) -> None:
        """Set which programmes to schedule, up to 5 programmes."""
        if len(program_ids) > 5:
            raise ValueError("Maximum 5 programmes may be selected.")

        self._selected_programs = list(program_ids)

    def update_exam_periods(self, periods: list[ExamPeriod]) -> None:
        """Replace in-memory periods with edited versions from the UI."""
        self._exam_periods = list(periods)
        self.mark_results_stale()

    def generate(self) -> tuple[dict[str, list[Schedule]], dict[str, Course], set[str]]:
        """
        Run the CSP engine and return
        (schedules_by_period, courses_by_id, truncated_periods).

        This version computes all schedules up front.
        No batching/truncation is applied.
        """
        if not self._selected_programs:
            raise ValueError("No programmes selected. Select at least one programme.")

        if not self._courses:
            raise ValueError("No courses loaded. Load a courses file first.")

        if not self._exam_periods:
            raise ValueError("No exam periods loaded. Load a periods file first.")

        self._remaining_schedule_iterators.clear()
        self._has_more_schedules.clear()
        self._iterator_overflows.clear()

        data_provider = InMemoryDataProvider(
            courses=self._courses,
            exam_periods=self._exam_periods,
            selected_programs=self._selected_programs,
        )
        conflict_strategy = ExactConflictStrategy(
            selected_programs=self._selected_programs
        )
        generator = ScheduleGenerator(conflict_strategy=conflict_strategy)

        memory_exporter = _MemoryExporter(cap=None, settings=self._settings)

        engine = _EngineController(
            data_provider=data_provider,
            exporter=memory_exporter,
            generator=generator,
            selected_programs=self._selected_programs,
            threshold_filter=ThresholdFilter(),
            threshold_settings=self._settings.thresholds,
        )
        engine.run()

        self._last_results = dict(memory_exporter.schedules_by_period)
        self.on_generation_succeeded(set())

        self._remaining_schedule_iterators.clear()
        self._has_more_schedules.clear()
        self._iterator_overflows.clear()

        return (
            dict(memory_exporter.schedules_by_period),
            dict(memory_exporter.courses_by_id),
            set(),
        )

    def resort(self, config: SortingConfig) -> dict[str, list[Schedule]]:
        """Re-rank cached threshold-valid results without regenerating schedules."""
        if self._last_results is None:
            raise ValueError(
                "No results to re-sort. Generate schedules before changing sort order."
            )

        self.apply_sort(config)

        courses = list(self._courses)
        resorted = {
            period_key: SortingEngine.sort(schedules, courses, config)
            for period_key, schedules in self._last_results.items()
        }

        self._last_results = resorted
        return resorted

    def cache_generated_results(
        self,
        schedules_by_period: dict[str, list[Schedule]],
    ) -> dict[str, list[Schedule]]:
        """Cache subprocess results and apply the current sort order before display.

        The subprocess already receives a settings snapshot and applies thresholds.
        The parent process re-applies the current sorting config before displaying,
        because sort order may have changed while generation was running.
        """
        courses = list(self._courses)
        sorting = self._settings.sorting

        resorted = {
            period_key: SortingEngine.sort(schedules, courses, sorting)
            for period_key, schedules in schedules_by_period.items()
        }

        self._last_results = resorted
        return resorted

    def reset_generation_state(self) -> None:
        """Clear all iterator state after subprocess-based generation completes."""
        self._remaining_schedule_iterators.clear()
        self._iterator_overflows.clear()
        self._has_more_schedules.clear()

    def set_has_more_from_truncated(self, truncated_periods: set[str]) -> None:
        """
        After subprocess generation, preserve which periods have more schedules.

        With full generation this usually receives an empty set, so it clears
        all has-more state.
        """
        self._remaining_schedule_iterators.clear()
        self._iterator_overflows.clear()
        self._has_more_schedules = {key: True for key in truncated_periods}

    def start_load_more_for_period(
        self,
        period_key: str,
        already_loaded: int,
    ) -> "tuple[multiprocessing.Queue, multiprocessing.Process]":
        """
        Legacy helper for old batched UI flow.

        Full generation no longer needs Load More. Kept so old UI/tests do not
        break if they still import or call this method.
        """
        import multiprocessing as _mp

        q: _mp.Queue = _mp.Queue()
        proc = _mp.Process(
            target=_run_generation_process,
            args=(
                q,
                list(self._courses),
                list(self._exam_periods),
                list(self._selected_programs),
            ),
            kwargs={
                "settings": self._settings,
                "cap": RESULT_BATCH_SIZE,
                "period_key": period_key,
                "offset": already_loaded,
            },
            daemon=True,
        )
        proc.start()
        return q, proc

    def load_more_schedules(
        self,
        period_key: str,
        limit: int | None = None,
    ) -> list[Schedule]:
        """
        Legacy helper for the old in-process batched flow.

        Full generation normally returns everything in generate(), so this should
        usually return [] in the UI.
        """
        batch_size = limit if limit is not None else RESULT_BATCH_SIZE

        if batch_size < 0:
            raise ValueError("limit must be non-negative.")

        if batch_size == 0:
            return []

        if not self._has_more_schedules.get(period_key, False):
            return []

        schedule_iter = self._remaining_schedule_iterators.get(period_key)
        if schedule_iter is None:
            self._has_more_schedules[period_key] = False
            return []

        overflow = self._iterator_overflows.pop(period_key, None)
        it = chain([overflow], schedule_iter) if overflow is not None else schedule_iter

        batch = list(islice(it, batch_size + 1))

        if len(batch) > batch_size:
            self._has_more_schedules[period_key] = True
            self._iterator_overflows[period_key] = batch[batch_size]
            return batch[:batch_size]

        self._has_more_schedules[period_key] = False
        self._remaining_schedule_iterators.pop(period_key, None)
        return batch

    def get_combined_schedule_count(
        self,
        schedules_by_period: dict[str, list[Schedule]],
    ) -> int:
        """
        Return the number of currently loaded combined schedules.

        This is the Cartesian product size of the loaded schedules per period.
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

    def export(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        output_path: Path,
    ) -> None:
        """Write selected schedules to a text file using TextFileExporter."""
        if self._results_stale:
            raise ValueError(
                "Cannot export stale schedules. Generate schedules again first."
            )

        courses_by_id = {course.id: course for course in self._courses}

        exporter = TextFileExporter(
            output_path=Path(output_path),
            max_combinations=None,
        )
        exporter.export_schedules(schedules_by_period, courses_by_id)

        logger.info("Exported schedules to %s", output_path)
