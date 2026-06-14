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

import inspect
import logging
from collections.abc import Callable, Iterator
from itertools import chain, islice
from pathlib import Path

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.adapters.in_memory_data_provider import InMemoryDataProvider
from src.adapters.readers.classroom_file_reader import ClassroomFileReader
from src.adapters.readers.course_file_reader import CourseFileReader
from src.adapters.readers.exam_period_file_reader import ExamPeriodFileReader
from src.adapters.readers.proctor_config_reader import ProctorConfigReader
from src.adapters.readers.program_selector_reader import ProgramSelectorReader
from src.adapters.readers.settings_file_reader import SettingsFileReader
from src.adapters.readers.slots_file_reader import SlotsFileReader
from src.adapters.text_file_exporter import TextFileExporter
from src.domain.classroom import Classroom
from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.domain.proctor import ProctorConfig
from src.domain.schedule import Schedule
from src.domain.semester import normalize_semester
from src.domain.settings import Settings
from src.domain.sorting import SortingConfig
from src.domain.sorting_engine import SortingEngine
from src.domain.threshold import ThresholdSettings
from src.domain.threshold_filter import ThresholdFilter
from src.domain.time_slot import TimeSlot
from src.engine.app_controller import AppController as _EngineController
from src.engine.schedule_generator import ScheduleGenerator
from src.engine.schedule_validator import filter_schedules
from src.interfaces.i_output_exporter import IOutputExporter

logger = logging.getLogger(__name__)


# Number of schedules fetched per UI batch. The first generation subprocess
# keeps its iterators alive, so later Load More requests continue from the
# current iterator position instead of recomputing from the beginning.
RESULT_BATCH_SIZE: int = 1000
RESULT_CAP: int = RESULT_BATCH_SIZE


class _MemoryExporter(IOutputExporter):
    """
    Captures generated schedules in memory instead of writing to disk.

    cap=None means full generation:
        collect all schedules for each period.

    cap=<number> means streaming batched generation:
        collect the first cap schedules per period, keep the remaining lazy
        iterators in this exporter, and mark truncated periods for Load More.
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

    def load_more(self, period_key: str, limit: int | None = None) -> list[Schedule]:
        """Consume the next batch from an already-live period iterator.

        This is the performance-critical path for the desktop Load More flow:
        it advances the iterator that was created during the initial generation
        subprocess. It never re-runs generation and never skips from offset 0.
        """
        batch_size = limit if limit is not None else self._cap
        if batch_size is None:
            batch_size = RESULT_BATCH_SIZE

        if batch_size < 0:
            raise ValueError("limit must be non-negative.")

        if batch_size == 0 or not self.has_more_by_period.get(period_key, False):
            return []

        schedule_iter = self.remaining_iterators.get(period_key)
        if schedule_iter is None:
            self.has_more_by_period[period_key] = False
            self.truncated_periods.discard(period_key)
            return []

        batch = list(islice(schedule_iter, batch_size + 1))
        courses_list = list(self.courses_by_id.values())

        if len(batch) > batch_size:
            self.remaining_iterators[period_key] = chain([batch[batch_size]], schedule_iter)
            self.has_more_by_period[period_key] = True
            self.truncated_periods.add(period_key)
            return self._sort(batch[:batch_size], courses_list)

        self.remaining_iterators.pop(period_key, None)
        self.has_more_by_period[period_key] = False
        self.truncated_periods.discard(period_key)
        return self._sort(batch, courses_list)

    def _sort(self, schedules: list[Schedule], courses: list[Course]) -> list[Schedule]:
        """Apply Sprint 3 thresholds first, then sorting.

        Some branches do not support threshold filtering inside AppController,
        so the desktop memory exporter must enforce the settings itself. This
        keeps both the in-process generate() path and the subprocess UI path
        consistent.
        """
        if not self._settings:
            return schedules

        filtered = filter_schedules(
            schedules,
            courses,
            self._settings.thresholds,
        )

        if self._settings.sorting.rules:
            return SortingEngine.sort(filtered, courses, self._settings.sorting)

        return filtered



def _build_engine_controller(
    *,
    data_provider: InMemoryDataProvider,
    exporter: IOutputExporter,
    generator: ScheduleGenerator,
    selected_programs: list[str],
    settings: Settings,
    classrooms: list[Classroom] | None = None,
    time_slots: list[TimeSlot] | None = None,
    proctor_config: ProctorConfig | None = None,
    allow_unassigned_classrooms: bool = False,
) -> _EngineController:
    """Create AppController using only constructor args this branch supports.

    Some branches include Feature 4 / threshold parameters in AppController,
    while older branches apply thresholds in this UI controller after export and
    do not accept classroom-related constructor arguments. Introspecting the
    signature keeps the desktop controller compatible without passing unexpected
    keyword arguments.
    """
    supported = inspect.signature(_EngineController.__init__).parameters

    kwargs = {
        "data_provider": data_provider,
        "exporter": exporter,
        "generator": generator,
        "selected_programs": selected_programs,
    }

    if "threshold_filter" in supported:
        kwargs["threshold_filter"] = ThresholdFilter()

    if "threshold_settings" in supported:
        kwargs["threshold_settings"] = settings.thresholds

    if "classrooms" in supported:
        kwargs["classrooms"] = classrooms or []

    if "time_slots" in supported:
        kwargs["time_slots"] = time_slots or []

    if "proctor_config" in supported:
        kwargs["proctor_config"] = proctor_config

    if "allow_unassigned_classrooms" in supported:
        kwargs["allow_unassigned_classrooms"] = allow_unassigned_classrooms

    return _EngineController(**kwargs)


def _run_generation_process(
    result_queue,
    courses: "list[Course]",
    exam_periods: "list[ExamPeriod]",
    selected_programs: "list[str]",
    settings: "Settings | None" = None,
    cap: "int | None" = None,
    period_key: "str | None" = None,
    offset: int = 0,
    classrooms: "list[Classroom] | None" = None,
    time_slots: "list[TimeSlot] | None" = None,
    proctor_config: "ProctorConfig | None" = None,
    allow_unassigned_classrooms: bool = False,
    command_queue=None,
) -> None:
    """
    Entry point for multiprocessing.Process-based schedule generation.

    Puts (True, schedules_by_period, courses_by_id, truncated_periods) on success
    or (False, error_message) on failure.

    Default behavior:
        cap=None -> generate all schedules up front.

    Optional streaming batching:
        cap=<number> with command_queue keeps the generator process alive.
        Later load_more commands continue from the saved iterator position;
        they do NOT regenerate from offset 0.
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

        engine = _build_engine_controller(
            data_provider=data_provider,
            exporter=memory_exporter,
            generator=generator,
            selected_programs=selected_programs,
            settings=active_settings,
            classrooms=classrooms,
            time_slots=time_slots,
            proctor_config=proctor_config,
            allow_unassigned_classrooms=allow_unassigned_classrooms,
        )
        engine.run()

        result_queue.put(
            (
                True,
                dict(memory_exporter.schedules_by_period),
                dict(memory_exporter.courses_by_id),
                set(memory_exporter.truncated_periods),
            )
        )

        if command_queue is not None and memory_exporter.truncated_periods:
            while any(memory_exporter.has_more_by_period.values()):
                command = command_queue.get()

                if command in (None, "shutdown"):
                    break

                if not isinstance(command, tuple) or not command:
                    continue

                action = command[0]
                if action == "shutdown":
                    break

                if action != "load_more":
                    continue

                _action, load_period_key, load_limit = command
                extra = memory_exporter.load_more(load_period_key, load_limit)
                truncated = (
                    {load_period_key}
                    if memory_exporter.has_more_by_period.get(load_period_key, False)
                    else set()
                )

                result_queue.put(
                    (
                        True,
                        {load_period_key: extra},
                        dict(memory_exporter.courses_by_id),
                        truncated,
                    )
                )
    except Exception as exc:
        logger.exception("Generation process failed")
        result_queue.put((False, str(exc)))


class _CompletedProcess:
    """Small process-like object used when no worker is available."""

    def is_alive(self) -> bool:
        return False

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None

    def join(self, timeout: float | None = None) -> None:
        return None


class _ImmediateResultQueue:
    """Queue-like wrapper that returns one already-known result."""

    def __init__(self, result) -> None:
        self._result = result
        self._used = False

    def get_nowait(self):
        from queue import Empty as _QueueEmpty

        if self._used:
            raise _QueueEmpty

        self._used = True
        return self._result


class _LoadMoreResponseQueue:
    """Per-period view over the shared generation worker result queue."""

    def __init__(self, controller: "DesktopController", period_key: str) -> None:
        self._controller = controller
        self._period_key = period_key

    def get_nowait(self):
        return self._controller._get_worker_result_for_period(self._period_key)


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
        self._classrooms: list[Classroom] = []
        self._time_slots: list[TimeSlot] = []
        self._proctor_config: ProctorConfig | None = None
        self._allow_unassigned_classrooms: bool = False
        self._feature4_enabled: bool = False
        self._remaining_schedule_iterators: dict[str, Iterator[Schedule]] = {}
        self._has_more_schedules: dict[str, bool] = {}
        self._iterator_overflows: dict[str, Schedule] = {}
        self._worker_command_queue = None
        self._worker_result_queue = None
        self._worker_process = None
        self._worker_pending_results: dict[str, tuple] = {}
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

    def load_classrooms(self, path: Path) -> int:
        """Load and validate the optional Feature 4 classrooms file."""
        self._classrooms = ClassroomFileReader(Path(path)).read()
        self.mark_results_stale()
        return len(self._classrooms)

    def load_time_slots(self, path: Path) -> int:
        """Load and validate the optional Feature 4 slots file."""
        self._time_slots = SlotsFileReader(Path(path)).read()
        self.mark_results_stale()
        return len(self._time_slots)

    def load_proctor_config(self, path: Path) -> ProctorConfig:
        """Load and validate the optional Feature 4 proctor configuration."""
        self._proctor_config = ProctorConfigReader(Path(path)).read()
        self.mark_results_stale()
        return self._proctor_config

    def set_time_slots_from_text(self, text: str) -> int:
        """
        Parse comma-separated HH:MM slots typed in the GUI (spec 4.1).

        The GUI provides slots as a text input, not a file; parsing and
        validation are delegated to SlotsFileReader.parse_line so the rules
        match the CLI file path exactly. Raises ValueError on invalid input.
        """
        self._time_slots = SlotsFileReader.parse_line(text)
        self.mark_results_stale()
        return len(self._time_slots)

    def set_proctor_config_from_text(self, text: str) -> ProctorConfig:
        """
        Parse a '1:X' proctor ratio typed in the GUI (spec 4.1).

        Delegates to ProctorConfigReader.parse_line so GUI and CLI enforce the
        same '1:X' rule. Raises ValueError on invalid input.
        """
        self._proctor_config = ProctorConfigReader.parse_line(text)
        self.mark_results_stale()
        return self._proctor_config

    def set_feature4_enabled(self, enabled: bool) -> None:
        """Toggle Feature 4 on/off (spec 4.1 dedicated activation toggle)."""
        self._feature4_enabled = enabled
        self.mark_results_stale()

    def clear_classrooms(self) -> None:
        self._classrooms = []
        self.mark_results_stale()

    def clear_time_slots(self) -> None:
        self._time_slots = []
        self.mark_results_stale()

    def clear_proctor_config(self) -> None:
        self._proctor_config = None
        self.mark_results_stale()

    def set_allow_unassigned_classrooms(self, allow: bool) -> None:
        """Preserve the user's soft-warning choice for subsequent result batches."""
        self._allow_unassigned_classrooms = bool(allow)

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

    @property
    def classrooms(self) -> list[Classroom]:
        return list(self._classrooms)

    @property
    def time_slots(self) -> list[TimeSlot]:
        return list(self._time_slots)

    @property
    def proctor_config(self) -> ProctorConfig | None:
        return self._proctor_config

    @property
    def feature4_enabled(self) -> bool:
        """Whether the user turned the Feature 4 toggle on (spec 4.1)."""
        return self._feature4_enabled

    @property
    def feature4_inputs_valid(self) -> bool:
        """True when all three Feature 4 inputs have been loaded and validated."""
        return bool(self._classrooms and self._time_slots and self._proctor_config)

    @property
    def feature4_active(self) -> bool:
        """
        Feature 4 is active only when the toggle is on AND all inputs are valid
        (spec 4.1 — activated via a dedicated toggle).
        """
        return self._feature4_enabled and self.feature4_inputs_valid

    def _relevant_offerings_for_course(self, course: Course) -> list:
        """
        Offerings of an exam course that are relevant to the current run:
        selected programmes AND the semester of any loaded exam period
        (spec 4.3/4.4). Mirrors ClassroomAssigner.get_relevant_offerings so the
        pre-generation checks and the engine agree on which exams matter.
        """
        semesters = {period.semester for period in self._exam_periods}
        seen: set[int] = set()
        relevant: list = []
        for semester in semesters:
            for offering in course.get_relevant_offerings(
                self._selected_programs, semester
            ):
                if id(offering) not in seen:
                    seen.add(id(offering))
                    relevant.append(offering)
        return relevant

    def engine_classrooms(self) -> list[Classroom]:
        """Classrooms passed to the engine — empty unless Feature 4 is active.

        Gating here (not only in the UI) guarantees that disabling the toggle
        truly disables classroom assignment, even if files remain loaded
        (spec 4.1).
        """
        return list(self._classrooms) if self.feature4_active else []

    def engine_time_slots(self) -> list[TimeSlot]:
        """Time slots passed to the engine — empty unless Feature 4 is active."""
        return list(self._time_slots) if self.feature4_active else []

    def engine_proctor_config(self) -> ProctorConfig | None:
        """Proctor config passed to the engine — None unless Feature 4 is active."""
        return self._proctor_config if self.feature4_active else None

    def feature4_missing_student_counts(self) -> bool:
        """
        True if any *relevant* exam offering lacks a StudentCount (spec 4.3).

        Only courses with evaluation_type == "Exam" are assigned rooms, and only
        offerings for the selected programmes in a loaded period's semester are
        scheduled — so only those offerings require a count. Courses or
        programmes the user did not select never block generation.
        """
        return any(
            offering.student_count is None
            for course in self._courses
            if course.has_exam()
            for offering in self._relevant_offerings_for_course(course)
        )

    def feature4_ready(self) -> bool:
        """
        True when Feature 4 may proceed to generation (spec 4.2): toggle on,
        all three inputs valid, and every exam offering has a StudentCount.
        """
        return (
            self._feature4_enabled
            and self.feature4_inputs_valid
            and not self.feature4_missing_student_counts()
        )

    def _exam_student_totals(self) -> dict[str, int]:
        """
        Total students per exam (spec 4.3): for each "Exam" course, sum the
        StudentCount across only its *relevant* program lines — selected
        programmes in a loaded period's semester. Courses with no relevant
        offering are excluded. Missing counts contribute zero.
        """
        totals: dict[str, int] = {}
        for course in self._courses:
            if not course.has_exam():
                continue
            offerings = self._relevant_offerings_for_course(course)
            if not offerings:
                continue
            totals[course.id] = sum(o.student_count or 0 for o in offerings)
        return totals

    def feature4_capacity_shortfall(self) -> tuple[int, int] | None:
        """
        Pre-generation capacity warning (spec 4.4).

        Returns (total classroom capacity, largest single-exam student count)
        when the total capacity of ALL rooms is less than the StudentCount of
        ANY single exam — because each exam occupies rooms in a single slot, so
        the binding constraint is the largest single exam, not the sum of all
        exams. Returns None when Feature 4 is inactive or capacity suffices.
        """
        if not self.feature4_active:
            return None

        exam_totals = self._exam_student_totals()
        if not exam_totals:
            return None

        total_capacity = sum(room.capacity for room in self._classrooms)
        largest_exam = max(exam_totals.values())

        if total_capacity < largest_exam:
            return total_capacity, largest_exam

        return None

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
        # Changing the programme selection changes which exams are scheduled, so
        # any previously generated results no longer match the inputs (spec §7).
        self.mark_results_stale()

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

        engine = _build_engine_controller(
            data_provider=data_provider,
            exporter=memory_exporter,
            generator=generator,
            selected_programs=self._selected_programs,
            settings=self._settings,
            classrooms=self.engine_classrooms(),
            time_slots=self.engine_time_slots(),
            proctor_config=self.engine_proctor_config(),
            allow_unassigned_classrooms=self._allow_unassigned_classrooms,
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

        With full generation this receives an empty set; with streaming
        generation it records which period iterators still have more pages.
        """
        self._remaining_schedule_iterators.clear()
        self._iterator_overflows.clear()
        self._has_more_schedules = {key: True for key in truncated_periods}

    def attach_generation_worker(
        self,
        command_queue,
        result_queue,
        process,
    ) -> None:
        """Keep the successful generation subprocess alive for Load More.

        The initial subprocess owns the lazy schedule iterators. Keeping a
        reference to it lets Load More advance those iterators without
        recomputing and skipping from the beginning.
        """
        self.shutdown_generation_worker()
        self._worker_command_queue = command_queue
        self._worker_result_queue = result_queue
        self._worker_process = process
        self._worker_pending_results.clear()

    def shutdown_generation_worker(self) -> None:
        """Stop any live background generation worker safely."""
        proc = self._worker_process
        cmd_q = self._worker_command_queue

        if cmd_q is not None:
            try:
                cmd_q.put(("shutdown",))
            except Exception:
                logger.debug("Failed sending generation-worker shutdown", exc_info=True)

        if proc is not None:
            try:
                # Give the worker a short chance to consume the shutdown command
                # and exit cleanly before escalating to terminate/kill.
                proc.join(timeout=0.5)
                if proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=0.5)
                    if proc.is_alive():
                        proc.kill()
                        proc.join(timeout=0.5)
            except Exception:
                logger.debug("Failed stopping generation worker", exc_info=True)

        for q in (self._worker_command_queue, self._worker_result_queue):
            if q is not None:
                try:
                    q.cancel_join_thread()
                except Exception:
                    pass
                try:
                    q.close()
                except Exception:
                    pass

        self._worker_command_queue = None
        self._worker_result_queue = None
        self._worker_process = None
        self._worker_pending_results.clear()

    def _get_worker_result_for_period(self, period_key: str):
        """Return the next worker result that belongs to period_key."""
        from queue import Empty as _QueueEmpty

        if period_key in self._worker_pending_results:
            return self._worker_pending_results.pop(period_key)

        if self._worker_result_queue is None:
            raise _QueueEmpty

        while True:
            result = self._worker_result_queue.get_nowait()

            if (
                isinstance(result, tuple)
                and len(result) == 4
                and result[0] is True
                and isinstance(result[1], dict)
            ):
                result_keys = set(result[1])
                if period_key in result_keys:
                    return result

                for key in result_keys:
                    self._worker_pending_results[key] = result
                continue

            return result

    def start_load_more_for_period(
        self,
        period_key: str,
        already_loaded: int,
    ):
        """Request the next batch from the live generation worker.

        Unlike the old offset-based implementation, this method does not start
        a new subprocess and does not call islice(iterator, offset, ...). The
        worker owns the original iterator and advances it in-place.
        """
        _ = already_loaded

        empty_success = (
            True,
            {period_key: []},
            {course.id: course for course in self._courses},
            set(),
        )

        if not self._has_more_schedules.get(period_key, False):
            return _ImmediateResultQueue(empty_success), _CompletedProcess()

        if (
            self._worker_command_queue is None
            or self._worker_process is None
            or not self._worker_process.is_alive()
        ):
            self._has_more_schedules[period_key] = False
            return _ImmediateResultQueue(empty_success), _CompletedProcess()

        self._worker_command_queue.put(("load_more", period_key, RESULT_BATCH_SIZE))
        return _LoadMoreResponseQueue(self, period_key), self._worker_process

    def load_more_schedules(
        self,
        period_key: str,
        limit: int | None = None,
    ) -> list[Schedule]:
        """
        Legacy helper for the old in-process batched flow.

        The PyQt UI uses start_load_more_for_period(), which delegates to the
        live subprocess worker. This method is kept for older unit-level callers.
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
