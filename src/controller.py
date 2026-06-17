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
import multiprocessing
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
from src.engine.app_controller import (
    AppController as _EngineController,
    CLASSROOM_VARIANT_MODE_ALL,
    CLASSROOM_VARIANT_MODE_FIRST,
)
from src.engine.classroom_assigner import ClassroomAssigner
from src.engine.proctor_report import build_proctor_report
from src.engine.schedule_generator import ScheduleGenerator
from src.interfaces.i_output_exporter import IOutputExporter

logger = logging.getLogger(__name__)


# All result auto-loading uses the same batch size.
# This controls both:
# 1. date-option loading / Auto Dates
# 2. same-date classroom variant loading / Auto Variants
#
# Increase this value to load more blocks per request.
# Decrease it if the UI feels slow or freezes during loading.
LOAD_BATCH_SIZE: int = 1000

# Backward-compatible names used by the UI/controller code.
RESULT_BATCH_SIZE: int = LOAD_BATCH_SIZE
VARIANT_BATCH_SIZE: int = LOAD_BATCH_SIZE


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
        selected_programs: list[str] | None = None,
    ) -> None:
        self._cap = cap
        self._offset_by_period = offset_by_period or {}
        self._only_period_keys = only_period_keys
        self._settings = settings
        self._selected_programs = selected_programs or []

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
            return SortingEngine.sort(
                schedules, courses, self._settings.sorting, self._selected_programs
            )
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
    classrooms: "list[Classroom] | None" = None,
    time_slots: "list[TimeSlot] | None" = None,
    proctor_config: "ProctorConfig | None" = None,
    allow_unassigned_classrooms: bool = False,
    classroom_variant_mode: str = CLASSROOM_VARIANT_MODE_FIRST,
) -> None:
    """
    Entry point for background-worker schedule generation.

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
            selected_programs=selected_programs,
        )

        engine = _EngineController(
            data_provider=data_provider,
            exporter=memory_exporter,
            generator=generator,
            selected_programs=selected_programs,
            threshold_filter=ThresholdFilter(),
            threshold_settings=active_settings.thresholds,
            classrooms=classrooms,
            time_slots=time_slots,
            proctor_config=proctor_config,
            allow_unassigned_classrooms=allow_unassigned_classrooms,
            classroom_variant_mode=classroom_variant_mode,
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



def _run_classroom_variants_process(
    result_queue,
    period_key: "str",
    schedule: "Schedule",
    courses: "list[Course]",
    selected_programs: "list[str]",
    settings: "Settings | None" = None,
    cap: "int | None" = None,
    offset: int = 0,
    classrooms: "list[Classroom] | None" = None,
    time_slots: "list[TimeSlot] | None" = None,
    proctor_config: "ProctorConfig | None" = None,
    allow_unassigned_classrooms: bool = False,
) -> None:
    """Generate classroom/time-slot variants for one already-chosen date schedule.

    This does not run the date generator again. It reuses schedule.assignments as
    the fixed date block and expands only classroom/time-slot allocations for it.
    """
    try:
        active_settings = settings or Settings(
            thresholds=ThresholdSettings(),
            sorting=SortingConfig(),
        )

        if not classrooms or not time_slots or proctor_config is None:
            result_queue.put((True, {period_key: []}, {c.id: c for c in courses}, set()))
            return

        # Important for Auto Variants:
        # do not ask the classroom assigner to materialise every possible
        # variant before the UI receives a result.  For a paged request, only
        # generate enough candidates to answer this page plus one look-ahead item
        # used to decide whether another page exists.
        page_limit = None if cap is None else offset + cap + 1

        variant_iter = ClassroomAssigner.assign_variants(
            schedule,
            courses,
            selected_programs,
            classrooms,
            time_slots,
            proctor_config,
            allow_unassigned=allow_unassigned_classrooms,
            max_options_per_day=page_limit,
            max_options_per_schedule=page_limit,
        )

        if cap is None:
            batch = list(islice(variant_iter, offset, None))
            still_more = False
        else:
            batch_plus_one = list(islice(variant_iter, offset, offset + cap + 1))
            still_more = len(batch_plus_one) > cap
            batch = batch_plus_one[:cap]

        courses_by_id = {course.id: course for course in courses}
        if active_settings.sorting.rules:
            batch = SortingEngine.sort(
                batch,
                courses,
                active_settings.sorting,
                selected_programs,
            )

        result_queue.put(
            (
                True,
                {period_key: batch},
                courses_by_id,
                {period_key} if still_more else set(),
            )
        )
    except Exception as exc:
        logger.exception("Classroom variant process failed")
        result_queue.put((False, str(exc)))


def _run_load_more_worker(task_queue, result_queue) -> None:
    """Persistent worker process for ResultsPanel Load More / Auto Load tasks.

    The old implementation opened a fresh multiprocessing.Process for every
    Load More / Auto Dates / Auto Variants batch. On Windows, each new process
    can briefly flash a small console window. This worker is started once per
    period and then reused for subsequent batches, so Auto Load does not create
    a new Python process for every page.
    """
    while True:
        task = task_queue.get()

        if task is None:
            return

        try:
            task_type, args, kwargs = task
        except ValueError:
            result_queue.put((False, "Invalid background worker task."))
            continue

        if task_type == "date_options":
            _run_generation_process(result_queue, *args, **kwargs)
        elif task_type == "variants":
            _run_classroom_variants_process(result_queue, *args, **kwargs)
        else:
            result_queue.put((False, f"Unknown background worker task: {task_type}"))


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
        self._results_stale: bool = False
        self._settings: Settings = Settings(
            thresholds=ThresholdSettings(),
            sorting=SortingConfig(),
        )

        # Cache of the last threshold-valid results, kept so a sort-only change
        # can re-rank in place instead of regenerating from scratch.
        self._last_results: dict[str, list[Schedule]] | None = None

        # Persistent Load More / Auto Load workers.
        # One worker is kept per period and reused across batches, instead of
        # opening a new multiprocessing.Process for every Auto batch. This
        # keeps multiprocessing performance while greatly reducing the number
        # of short Windows console popups during automatic loading.
        self._load_worker_tasks: dict[str, multiprocessing.Queue] = {}
        self._load_worker_results: dict[str, multiprocessing.Queue] = {}
        self._load_worker_procs: dict[str, multiprocessing.Process] = {}

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

    def snapshot_courses(self) -> list[Course]:
        """Return a shallow copy of the current courses list for rollback."""
        return list(self._courses)

    def restore_courses(self, courses: list[Course]) -> None:
        """Restore a previously snapshotted courses list (spec 4.3 abort)."""
        self._courses = list(courses)
        self.mark_results_stale()

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
        Parse comma-separated HH:MM slots from an in-memory value.

        Kept as a compatibility helper; the GUI loads slots from a .txt file.
        Raises ValueError on invalid input.
        """
        self._time_slots = SlotsFileReader.parse_line(text)
        self.mark_results_stale()
        return len(self._time_slots)

    def set_proctor_config_from_text(self, text: str) -> ProctorConfig:
        """
        Parse a '1:X' proctor ratio from an in-memory value.

        Kept as a compatibility helper; the GUI loads the ratio from a .txt
        file. Raises ValueError on invalid input.
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
        seen: set[tuple] = set()
        relevant: list = []
        for semester in semesters:
            for offering in course.get_relevant_offerings(
                self._selected_programs, semester
            ):
                key = (
                    offering.program_id,
                    offering.year,
                    normalize_semester(offering.semester),
                )
                if key not in seen:
                    seen.add(key)
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

    def any_exam_missing_student_count(self) -> bool:
        """
        True if ANY exam course has an offering without a StudentCount,
        regardless of programme selection (spec 4.3 file-load abort).

        Used at courses-file load time, before programmes/periods are known,
        to reject a file that cannot satisfy Feature 4. Unlike
        feature4_missing_student_counts this is not filtered by relevance.
        """
        return any(
            offering.student_count is None
            for course in self._courses
            if course.has_exam()
            for offering in course.offerings
        )

    def feature4_missing_student_counts(self) -> bool:
        """
        True if any *relevant* exam offering lacks a StudentCount (spec 4.3).

        Only courses with evaluation_type == "Exam" are assigned rooms, and only
        offerings for the selected programmes in a loaded period's semester are
        scheduled — so only those offerings require a count. Courses or
        programmes the user did not select never block generation.

        When no programmes are selected yet, relevance cannot be determined, so
        fall back to the unfiltered check — otherwise the warning would be
        vacuously suppressed and the engine would raise at generate time.
        """
        if not self._selected_programs:
            return self.any_exam_missing_student_count()
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

        memory_exporter = _MemoryExporter(
            cap=None,
            settings=self._settings,
            selected_programs=self._selected_programs,
        )

        engine = _EngineController(
            data_provider=data_provider,
            exporter=memory_exporter,
            generator=generator,
            selected_programs=self._selected_programs,
            threshold_filter=ThresholdFilter(),
            threshold_settings=self._settings.thresholds,
            classrooms=self.engine_classrooms(),
            time_slots=self.engine_time_slots(),
            proctor_config=self.engine_proctor_config(),
            classroom_variant_mode=CLASSROOM_VARIANT_MODE_FIRST,
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
            period_key: SortingEngine.sort(schedules, courses, config, self._selected_programs)
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
            period_key: SortingEngine.sort(schedules, courses, sorting, self._selected_programs)
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

    def _get_or_start_load_worker(
        self,
        period_key: str,
    ) -> "tuple[multiprocessing.Queue, multiprocessing.Queue, multiprocessing.Process]":
        """Return a reusable background worker for one period.

        Starting a multiprocessing process is expensive on Windows and may flash
        a small console window. Auto Load can request many batches, so this
        method starts the worker once and keeps it alive for the next batch.
        """
        proc = self._load_worker_procs.get(period_key)
        task_queue = self._load_worker_tasks.get(period_key)
        result_queue = self._load_worker_results.get(period_key)

        if (
            proc is not None
            and task_queue is not None
            and result_queue is not None
            and proc.is_alive()
        ):
            return task_queue, result_queue, proc

        self._cleanup_load_worker(period_key, terminate=True)

        task_queue = multiprocessing.Queue()
        result_queue = multiprocessing.Queue()
        proc = multiprocessing.Process(
            target=_run_load_more_worker,
            args=(task_queue, result_queue),
            daemon=True,
        )
        proc.start()

        self._load_worker_tasks[period_key] = task_queue
        self._load_worker_results[period_key] = result_queue
        self._load_worker_procs[period_key] = proc

        return task_queue, result_queue, proc

    def _cleanup_load_worker(self, period_key: str, terminate: bool = False) -> None:
        """Stop and remove one persistent Load More worker."""
        task_queue = self._load_worker_tasks.pop(period_key, None)
        result_queue = self._load_worker_results.pop(period_key, None)
        proc = self._load_worker_procs.pop(period_key, None)

        if task_queue is not None:
            try:
                if not terminate:
                    task_queue.put(None)
            except Exception:
                logger.debug("Could not send shutdown task to load worker", exc_info=True)

        if proc is not None:
            try:
                if terminate and proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=0.5)

                    if proc.is_alive():
                        proc.kill()
                        proc.join(timeout=0.5)
                else:
                    proc.join(timeout=0.5)
            except Exception:
                logger.debug("Failed cleaning up load worker", exc_info=True)

        for q in (task_queue, result_queue):
            if q is None:
                continue
            try:
                q.cancel_join_thread()
            except Exception:
                pass
            try:
                q.close()
            except Exception:
                pass

    def shutdown_load_workers(self) -> None:
        """Stop all persistent Load More / Auto Load workers."""
        for period_key in list(self._load_worker_procs):
            self._cleanup_load_worker(period_key, terminate=True)

    def start_load_more_date_options_for_period(
        self,
        period_key: str,
        already_loaded_date_options: int,
    ) -> "tuple[multiprocessing.Queue, multiprocessing.Process]":
        """Queue the next batch of different date options for one period.

        A persistent worker process is reused per period, so Auto Dates does
        not open a new Python process for every batch.
        """
        task_queue, result_queue, proc = self._get_or_start_load_worker(period_key)

        task_queue.put(
            (
                "date_options",
                (
                    list(self._courses),
                    list(self._exam_periods),
                    list(self._selected_programs),
                ),
                {
                    "settings": self._settings,
                    "cap": RESULT_BATCH_SIZE,
                    "period_key": period_key,
                    "offset": already_loaded_date_options,
                    "classrooms": self.engine_classrooms(),
                    "time_slots": self.engine_time_slots(),
                    "proctor_config": self.engine_proctor_config(),
                    "allow_unassigned_classrooms": self._allow_unassigned_classrooms,
                    "classroom_variant_mode": CLASSROOM_VARIANT_MODE_FIRST,
                },
            )
        )

        return result_queue, proc

    def start_load_variants_for_schedule(
        self,
        period_key: str,
        schedule: Schedule,
        already_loaded_variants: int,
    ) -> "tuple[multiprocessing.Queue, multiprocessing.Process]":
        """Queue the next classroom/time-slot variants for the current dates.

        A persistent worker process is reused per period, so Auto Variants does
        not open a new Python process for every batch.
        """
        task_queue, result_queue, proc = self._get_or_start_load_worker(period_key)

        task_queue.put(
            (
                "variants",
                (
                    period_key,
                    schedule,
                    list(self._courses),
                    list(self._selected_programs),
                ),
                {
                    "settings": self._settings,
                    "cap": VARIANT_BATCH_SIZE,
                    "offset": already_loaded_variants,
                    "classrooms": self.engine_classrooms(),
                    "time_slots": self.engine_time_slots(),
                    "proctor_config": self.engine_proctor_config(),
                    "allow_unassigned_classrooms": self._allow_unassigned_classrooms,
                },
            )
        )

        return result_queue, proc

    def start_load_more_for_period(
        self,
        period_key: str,
        already_loaded: int,
    ) -> "tuple[multiprocessing.Queue, multiprocessing.Process]":
        """Backward-compatible alias for loading more date options."""
        return self.start_load_more_date_options_for_period(period_key, already_loaded)

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

    def proctor_report_text(self, schedule: Schedule) -> str:
        """Return the spec 4.6 proctor report text for one schedule."""
        courses_by_id = {course.id: course for course in self._courses}
        return build_proctor_report(schedule, courses_by_id)

    def export_proctor_report(self, schedule: Schedule, output_path: Path) -> None:
        """Write the spec 4.6 proctor report for one schedule to a .txt file."""
        if self._results_stale:
            raise ValueError(
                "Cannot export stale schedules. Generate schedules again first."
            )

        text = self.proctor_report_text(schedule)
        Path(output_path).write_text(text, encoding="utf-8")
        logger.info("Exported proctor report to %s", output_path)
