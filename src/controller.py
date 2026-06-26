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

import copy
import logging
import multiprocessing
from collections.abc import Iterator
from itertools import chain, islice
from pathlib import Path

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.adapters.in_memory_data_provider import InMemoryDataProvider
from src.adapters.sqlite_schedule_store import SQLiteScheduleExporter, SQLiteScheduleStore, StoredScheduleList
from src.adapters.readers.classroom_file_reader import ClassroomFileReader
from src.adapters.readers.course_file_reader import CourseFileReader
from src.adapters.readers.exam_period_file_reader import ExamPeriodFileReader
from src.adapters.readers.proctor_config_reader import ProctorConfigReader
from src.adapters.readers.schedule_file_reader import (
    EmptyScheduleImportError,
    ImportedScheduleData,
    ScheduleFileReader,
)
from src.adapters.readers.program_selector_reader import ProgramSelectorReader
from src.adapters.readers.settings_file_reader import SettingsFileReader
from src.adapters.readers.slots_file_reader import SlotsFileReader
from src.adapters.text_file_exporter import TextFileExporter
from src.domain.classroom import Classroom
from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.domain.feature4_validator import Feature4Validator
from src.domain.period_order import sort_period_mapping_canonically
from src.domain.proctor import ProctorConfig
from src.domain.schedule import Schedule
from src.domain.settings import Settings
from src.domain.sorting import SortingConfig
from src.domain.sorting_engine import SortingEngine
from src.domain.threshold import ThresholdSettings
from src.domain.threshold_filter import ThresholdFilter
from src.domain.time_slot import TimeSlot
from src.engine.app_controller import (
    AppController as _EngineController,
    CLASSROOM_VARIANT_MODE_FIRST,
)
from src.engine.combined_schedule_indexer import CombinedScheduleIndexer
from src.engine.generation_workers import _MemoryExporter
# Re-exported so existing callers (config_screen, tests) keep importing it here.
from src.engine.generation_workers import _run_generation_process  # noqa: F401
from src.engine.load_worker_pool import LoadWorkerPool
from src.engine.proctor_report import build_proctor_report
from src.engine.ranking_worker import RankingJob
from src.engine.schedule_generator import ScheduleGenerator
from src.utils.merge_utils import merge_by_key, update_merge_courses

logger = logging.getLogger(__name__)


# All result auto-loading uses the same batch size.
# This controls both:
# 1. date-option loading / Auto Dates
# 2. same-date classroom variant loading / Auto Variants
#
# Increase this value to load more blocks per request.
# Decrease it if the UI feels slow or freezes during loading.
LOAD_BATCH_SIZE: int = 5000


class MissingStudentCountError(ValueError):
    """Raised when a courses load would leave Exam offerings without a
    StudentCount while Feature 4 is enabled (spec 4.3 file-load abort).

    Subclasses ValueError so callers may catch either type; the UI catches
    this specific type to show the dedicated 'Missing Student Counts' dialog.
    """


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
        self._imported_courses_by_id: dict[str, Course] = {}

        # True while the cached results come from an imported schedules.txt file
        # (read-only mode), so a sort-only change must re-render the imported
        # schedule rather than fall back to stale generated results.
        self._read_only_import: bool = False

        # Cache of the last threshold-valid results, kept so a sort-only change
        # can re-rank in place instead of regenerating from scratch.
        self._last_results: dict[str, list[Schedule]] | None = None

        # Store owned by the legacy in-process generation path. Subprocess UI
        # generation may still create a panel-owned store and then cache its
        # StoredScheduleList views here.
        self._schedule_store: SQLiteScheduleStore | None = None

        # Persistent Load More / Auto Load workers — lifecycle managed by pool.
        self._worker_pool = LoadWorkerPool()

    @property
    def settings(self) -> Settings:
        return self._settings

    def set_imported_state(self, courses_by_id: dict[str, "Course"]) -> None:
        """Store courses from an imported schedule file for proctor report resolution."""
        self._imported_courses_by_id = dict(courses_by_id)

    def clear_imported_state(self) -> None:
        """Clear imported-schedule state when a normal generation run starts."""
        self._imported_courses_by_id = {}
        self._read_only_import = False

    @property
    def read_only_import(self) -> bool:
        """True while the cached results come from an imported schedule file."""
        return self._read_only_import

    def _reset_owned_schedule_store(self) -> SQLiteScheduleStore:
        """Replace the controller-owned SQLite store for a new generation run."""
        if self._schedule_store is not None:
            self._schedule_store.close(delete=True)
        self._schedule_store = SQLiteScheduleStore()
        return self._schedule_store

    def import_schedule(self, path: Path) -> ImportedScheduleData:
        """Parse a previously exported schedules.txt file and cache it as
        read-only imported results.

        Parsing, course-metadata resolution, and result caching all live here so
        the view only chooses a path and renders the returned data (MVC).

        Course metadata is taken from the currently loaded courses when an id is
        present there, otherwise from the metadata parsed out of the file.
        """
        # Parse and validate FULLY before touching any controller state, so a
        # failed import (empty file, malformed data, reader error) leaves the
        # previous results, read-only flag and imported courses exactly as they
        # were. The import is atomic: all-or-nothing.
        imported = ScheduleFileReader().read_with_metadata(Path(path))

        if not imported.schedules_by_period:
            raise EmptyScheduleImportError(
                "No schedules were found in the selected file."
            )

        loaded_courses_by_id = {course.id: course for course in self._courses}
        courses_by_id = {
            course_id: loaded_courses_by_id.get(course_id, imported_course)
            for course_id, imported_course in imported.courses_by_id.items()
        }

        # Validation passed — now commit the new imported state. Importing does
        # not change the underlying input data, so results are not stale; they
        # are simply read-only.
        self.clear_results_stale()
        self.set_imported_state(courses_by_id)
        self._read_only_import = True
        self._last_results = sort_period_mapping_canonically(
            imported.schedules_by_period
        )

        return ImportedScheduleData(
            schedules_by_period=imported.schedules_by_period,
            courses_by_id=courses_by_id,
        )

    def apply_sort(self, config: SortingConfig) -> None:
        """Store a new sort config immediately on sort-list change (§281).

        Preserves existing thresholds. Called live — does NOT restart generation.
        """
        self._settings = Settings(thresholds=self._settings.thresholds, sorting=config)
        logger.info("apply_sort: %d active rules", len(config.rules))

    def apply_settings(self, settings: Settings) -> None:
        """Persist the full settings object (thresholds + sort) from the dialog OK path.

        A threshold change can invalidate already-generated results (they may no
        longer satisfy the new rules), so existing results are marked stale and
        must be regenerated before they can be trusted or exported. A sorting-only
        change does NOT invalidate results — they are simply re-ranked in place.
        """
        previous = self._settings
        self._settings = settings
        if settings.thresholds != previous.thresholds:
            self.mark_results_stale()
        logger.info(
            "apply_settings: thresholds=%d active, sort=%d rules, stale=%s",
            sum(1 for e in settings.thresholds.entries if e.enabled),
            len(settings.sorting.rules),
            self._results_stale,
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

        # Pre-merge validation (spec 4.3): build the would-be-merged result without
        # mutating committed state.  update_merge_courses modifies Course objects
        # in-place, so it needs a deep copy. replace/append only mutate the list
        # structure (not the Course objects themselves), so a shallow copy suffices.
        if mode == "update":
            candidate = copy.deepcopy(self._courses)
            update_merge_courses(candidate, new_courses)
        else:
            candidate = list(self._courses)
            merge_by_key(candidate, new_courses, mode, key_fn=lambda c: c.id)

        # When Feature 4 is enabled, every Exam offering must carry a
        # StudentCount. Reject BEFORE committing — self._courses is untouched.
        if self._feature4_enabled and Feature4Validator.any_exam_missing_student_count(
            candidate
        ):
            raise MissingStudentCountError(
                "Feature 4 is enabled, but this courses file would leave Exam "
                "offerings without a StudentCount (spec 4.3). The load was aborted."
            )

        self._courses = candidate
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

    def set_classrooms_from_text(self, text: str) -> int:
        """
        Parse classrooms from manual GUI input.

        Uses the same format and validation rules as the classrooms file:
            $$$$
            Room Name
            Capacity

        Returns the number of valid classrooms loaded.
        """
        self._classrooms = ClassroomFileReader.parse_text(text)
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

    def _merge_by_key(self, existing: list, new_items: list, mode: str, key_fn) -> None:
        merge_by_key(existing, new_items, mode, key_fn)

    @property
    def courses(self) -> list[Course]:
        return list(self._courses)

    @property
    def selected_programs(self) -> list[str]:
        """Return the currently selected programme IDs."""
        return list(self._selected_programs)

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
        """Delegates to Feature4Validator (spec 4.3/4.4)."""
        return Feature4Validator.relevant_offerings_for_course(
            course, self._selected_programs, self._exam_periods
        )

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
        return Feature4Validator.any_exam_missing_student_count(self._courses)

    def feature4_missing_student_counts(self) -> bool:
        """
        True if any *relevant* exam offering lacks a StudentCount (spec 4.3).
        Delegates to Feature4Validator.
        """
        return Feature4Validator.missing_student_counts(
            self._courses, self._selected_programs, self._exam_periods
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

    def _exam_student_totals(self) -> dict[tuple[str, str], int]:
        """Delegates to Feature4Validator (spec 4.3/4.4)."""
        return Feature4Validator.exam_student_totals(
            self._courses, self._selected_programs, self._exam_periods
        )

    def feature4_capacity_shortfall(self) -> tuple[int, int] | None:
        """
        Pre-generation capacity warning (spec 4.4). Delegates to
        Feature4Validator; returns None when inactive or capacity suffices.
        """
        return Feature4Validator.capacity_shortfall(
            self._courses,
            self._selected_programs,
            self._exam_periods,
            self._classrooms,
            self.feature4_active,
        )

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
        self.clear_imported_state()

        data_provider = InMemoryDataProvider(
            courses=self._courses,
            exam_periods=self._exam_periods,
            selected_programs=self._selected_programs,
        )
        conflict_strategy = ExactConflictStrategy(
            selected_programs=self._selected_programs
        )
        generator = ScheduleGenerator(
            conflict_strategy=conflict_strategy,
            threshold_settings=self._settings.thresholds,
            selected_programs=self._selected_programs,
        )

        # Full in-process generation is still supported for tests / legacy callers,
        # but results are no longer accumulated in one unbounded Python list.
        # They are streamed into a temporary SQLite store and exposed through
        # list-like StoredScheduleList facades.  The actual backtracking
        # algorithm remains lazy; ScheduleGenerator may prune internally with
        # MRV/forward-checking/threshold metrics without materialising results.
        sqlite_exporter = SQLiteScheduleExporter(
            settings=self._settings,
            selected_programs=self._selected_programs,
            chunk_size=LOAD_BATCH_SIZE,
            store=self._reset_owned_schedule_store(),
        )

        engine = _EngineController(
            data_provider=data_provider,
            exporter=sqlite_exporter,
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

        ordered_results = sort_period_mapping_canonically(
            sqlite_exporter.schedules_by_period
        )
        self._last_results = ordered_results
        self.on_generation_succeeded(set())

        self._remaining_schedule_iterators.clear()
        self._has_more_schedules.clear()
        self._iterator_overflows.clear()

        return (
            dict(ordered_results),
            dict(sqlite_exporter.courses_by_id),
            set(),
        )

    def resort(self, config: SortingConfig) -> dict[str, list[Schedule]]:
        """Re-rank cached threshold-valid results without regenerating schedules.

        Plain in-memory results are sorted with SortingEngine.  SQLite-backed
        results keep the schedules on disk and only update the ORDER BY rule used
        by their StoredScheduleList facade, so re-ranking does not pull the whole
        cache into RAM.
        """
        if self._last_results is None:
            raise ValueError(
                "No results to re-sort. Generate schedules before changing sort order."
            )

        self.apply_sort(config)

        # Imported read-only schedules may have no courses file loaded, so use
        # the imported course metadata when present. The UI's selected programs
        # describe the *generation* context, not the imported file, so they must
        # NOT constrain ranking of imported data — pass None so the engine ranks
        # across all available imported courses instead of a stale UI selection.
        if self._read_only_import and self._imported_courses_by_id:
            courses = list(self._imported_courses_by_id.values())
            selected_programs = None
        else:
            courses = list(self._courses)
            selected_programs = self._selected_programs

        resorted: dict[str, list[Schedule]] = {}
        for period_key, schedules in self._last_results.items():
            if isinstance(schedules, StoredScheduleList):
                schedules.set_scoring_context(courses, selected_programs)
                schedules.set_sorting(config)
                resorted[period_key] = schedules
            else:
                resorted[period_key] = SortingEngine.sort(
                    schedules, courses, config, selected_programs
                )

        self._last_results = sort_period_mapping_canonically(resorted)
        return self._last_results

    def _ranking_context(self) -> tuple[list[Course], list[str] | None]:
        """Return the course/program context used for Result Ranking."""
        if self._read_only_import and self._imported_courses_by_id:
            return list(self._imported_courses_by_id.values()), None
        return list(self._courses), list(self._selected_programs)

    def build_ranking_job(self, config: SortingConfig) -> RankingJob:
        """Build a background-ranking payload without regenerating schedules."""
        if self._last_results is None:
            raise ValueError(
                "No results to re-sort. Generate schedules before changing sort order."
            )

        courses, selected_programs = self._ranking_context()
        memory_periods: dict[str, list[Schedule]] = {}
        sqlite_specs: dict[str, list[str]] = {}

        for period_key, schedules in self._last_results.items():
            if isinstance(schedules, StoredScheduleList):
                sqlite_specs.setdefault(str(schedules.store.path), []).append(period_key)
            else:
                # Large generated result sets are SQLite-backed before they reach
                # Result Ranking. This in-memory payload path is retained for
                # small/imported snapshots and unit-test fixtures.
                memory_periods[period_key] = list(schedules)

        return RankingJob(
            sorting=config,
            courses=courses,
            selected_programs=selected_programs,
            schedules_by_period=memory_periods,
            sqlite_store_specs=tuple(
                (path, tuple(period_keys))
                for path, period_keys in sqlite_specs.items()
            ),
        )

    def apply_ranked_results(
        self,
        config: SortingConfig,
        ranked_schedules_by_period: dict[str, list[Schedule]],
    ) -> dict[str, list[Schedule]]:
        """Commit a completed background ranking result to the cached results."""
        if self._last_results is None:
            raise ValueError(
                "No results to re-sort. Generate schedules before changing sort order."
            )

        self.apply_sort(config)
        courses, selected_programs = self._ranking_context()

        resorted: dict[str, list[Schedule]] = {}
        for period_key, schedules in self._last_results.items():
            if isinstance(schedules, StoredScheduleList):
                schedules.set_scoring_context(courses, selected_programs)
                schedules.set_sorting(config)
                resorted[period_key] = schedules
            else:
                resorted[period_key] = ranked_schedules_by_period[period_key]

        self._last_results = sort_period_mapping_canonically(resorted)
        return self._last_results

    def cache_generated_results(
        self,
        schedules_by_period: dict[str, list[Schedule]],
    ) -> dict[str, list[Schedule]]:
        """Cache subprocess results and apply the current sort order before display.

        The subprocess already receives a settings snapshot and applies thresholds.
        The parent process re-applies the current sorting config before displaying,
        because sort order may have changed while generation was running.

        If the values are StoredScheduleList objects, the data is already on disk;
        changing ranking only updates the SQLite ORDER BY rule used on access.
        """
        self.clear_imported_state()

        courses = list(self._courses)
        sorting = self._settings.sorting

        resorted: dict[str, list[Schedule]] = {}
        for period_key, schedules in schedules_by_period.items():
            if isinstance(schedules, StoredScheduleList):
                schedules.set_scoring_context(courses, self._selected_programs)
                schedules.set_sorting(sorting)
                resorted[period_key] = schedules
            else:
                resorted[period_key] = SortingEngine.sort(
                    schedules, courses, sorting, self._selected_programs
                )

        self._last_results = sort_period_mapping_canonically(resorted)
        return self._last_results

    def begin_streaming_cache(self) -> None:
        """Reset the result cache at the start of a streaming generation run.

        Streaming delivers one period at a time via
        :meth:`cache_generated_results_incremental`. Call this once before the
        first partial so leftover results from a previous run (or an imported
        schedule) do not linger and merge into the new run.
        """
        self.clear_imported_state()
        self._last_results = {}
        self._remaining_schedule_iterators.clear()
        self._iterator_overflows.clear()
        self._has_more_schedules.clear()

    def cache_generated_results_incremental(
        self,
        partial: dict[str, list[Schedule]],
    ) -> dict[str, list[Schedule]]:
        """Sort and merge one streamed batch of periods into the cache.

        Unlike :meth:`cache_generated_results`, which replaces the whole cache,
        this keeps periods streamed earlier in the same run so a later re-sort or
        export sees every period. Sorting is re-applied in the parent process
        because the active sort order may have changed while generation ran.
        Returns only the sorted periods from *partial* (for incremental display).
        """
        courses = list(self._courses)
        sorting = self._settings.sorting

        sorted_partial = {
            period_key: SortingEngine.sort(
                schedules, courses, sorting, self._selected_programs
            )
            for period_key, schedules in partial.items()
        }

        if self._last_results is None:
            self._last_results = {}
        self._last_results.update(sorted_partial)
        self._last_results = sort_period_mapping_canonically(self._last_results)

        return sorted_partial

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
        self._has_more_schedules = sort_period_mapping_canonically(
            {key: True for key in truncated_periods}
        )

    def _get_or_start_load_worker(
        self,
        period_key: str,
    ) -> "tuple[multiprocessing.Queue, multiprocessing.Queue, multiprocessing.Process]":
        return self._worker_pool.get_or_start(period_key)

    def _cleanup_load_worker(self, period_key: str, terminate: bool = False) -> None:
        self._worker_pool.cleanup(period_key, terminate)

    def shutdown_load_workers(self) -> None:
        """Stop all persistent Load More / Auto Load workers."""
        self._worker_pool.shutdown_all()

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
                    "cap": LOAD_BATCH_SIZE,
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
                    "cap": LOAD_BATCH_SIZE,
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
        batch_size = limit if limit is not None else LOAD_BATCH_SIZE

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
        """Return the Cartesian product size of the loaded schedules per period."""
        return CombinedScheduleIndexer.count(schedules_by_period)

    def get_combined_schedule_at(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        index: int,
    ) -> dict[str, Schedule]:
        """Return one combined schedule by Cartesian-product index."""
        return CombinedScheduleIndexer.at(schedules_by_period, index)

    def export(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        output_path: Path,
        courses_by_id: dict[str, Course] | None = None,
    ) -> None:
        """Write selected schedules to a text file using TextFileExporter.

        If courses_by_id is provided, use it as the export metadata source.
        This is needed for imported schedules, where the controller may not have
        the original courses file loaded but the imported schedules.txt file
        still contains course names and instructors.
        """
        if self._results_stale:
            raise ValueError(
                "Cannot export stale schedules. Generate schedules again first."
            )

        export_courses_by_id = (
            courses_by_id
            if courses_by_id is not None
            else {course.id: course for course in self._courses}
        )

        exporter = TextFileExporter(
            output_path=Path(output_path),
            max_combinations=None,
        )
        exporter.export_schedules(
            sort_period_mapping_canonically(schedules_by_period),
            export_courses_by_id,
        )

        logger.info("Exported schedules to %s", output_path)

    def proctor_report_text(self, schedule: Schedule) -> str:
        """Return the spec 4.6 proctor report text for one schedule.

        Uses imported courses state when present (set via set_imported_state),
        otherwise falls back to courses loaded from the courses file.
        """
        resolved = self._imported_courses_by_id or {
            course.id: course for course in self._courses
        }
        return build_proctor_report(schedule, resolved)

    def export_proctor_report(self, schedule: Schedule, output_path: Path) -> None:
        """Write the spec 4.6 proctor report for one schedule to a .txt file."""
        if self._results_stale:
            raise ValueError(
                "Cannot export stale schedules. Generate schedules again first."
            )

        text = self.proctor_report_text(schedule)
        Path(output_path).write_text(text, encoding="utf-8")
        logger.info("Exported proctor report to %s", output_path)
