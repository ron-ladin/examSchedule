"""
Generation Workers
------------------
Background-process entry points for schedule generation, extracted from
DesktopController. These run in separate multiprocessing.Process workers and
must depend only on picklable inputs and the engine/domain layers — never on
PyQt6 or controller state.

Contains:
    - _MemoryExporter: captures generated schedules in memory (IOutputExporter).
    - _run_generation_process: full / paged date-option generation.
    - _run_classroom_variants_process: classroom/time-slot variants for one date.
    - _KindTaggedQueue: tags results with their task kind on a shared queue.
    - _run_load_more_worker: persistent worker dispatching the two task types.

DesktopController re-exports these names for backwards compatibility.
"""

import logging
import time
from collections.abc import Iterator
from itertools import chain, islice

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.adapters.in_memory_data_provider import InMemoryDataProvider
from src.domain.classroom import Classroom
from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.domain.generation_result import GenerationResult
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
from src.engine.classroom_assigner import ClassroomAssigner
from src.engine.schedule_generator import ScheduleGenerator
from src.interfaces.i_output_exporter import IOutputExporter

logger = logging.getLogger(__name__)


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
        timeout_seconds: float | None = None,
    ) -> None:
        self._cap = cap
        self._offset_by_period = offset_by_period or {}
        self._only_period_keys = only_period_keys
        self._settings = settings
        self._selected_programs = selected_programs or []
        self._timeout_seconds = timeout_seconds

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

        deadline: float | None = (
            time.perf_counter() + self._timeout_seconds
            if self._timeout_seconds is not None
            else None
        )

        for key, schedule_iter in schedules_by_period.items():
            if self._only_period_keys is not None and key not in self._only_period_keys:
                continue

            offset = self._offset_by_period.get(key, 0)

            if self._cap is None and deadline is None:
                collected = list(islice(schedule_iter, offset, None))
                self.schedules_by_period[key] = self._sort(collected, courses_list)
                self.has_more_by_period[key] = False
                continue

            if self._cap is None:
                # Timeout-bounded unbounded collection: stream one by one.
                collected = []
                timed_out = False
                for schedule in islice(schedule_iter, offset, None):
                    if deadline is not None and time.perf_counter() > deadline:
                        timed_out = True
                        break
                    collected.append(schedule)
                self.schedules_by_period[key] = self._sort(collected, courses_list)
                if timed_out:
                    self.truncated_periods.add(key)
                    self.has_more_by_period[key] = True
                else:
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
    timeout_seconds: float | None = None,
) -> None:
    """
    Entry point for background-worker schedule generation.

    Puts a GenerationResult on the queue: ok(schedules_by_period, courses_by_id,
    truncated_periods) on success or failure(error_message) on error.

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
            timeout_seconds=timeout_seconds,
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
            GenerationResult.ok(
                memory_exporter.schedules_by_period,
                memory_exporter.courses_by_id,
                memory_exporter.truncated_periods,
            )
        )
    except Exception as exc:
        logger.exception("Generation process failed")
        result_queue.put(GenerationResult.failure(str(exc)))


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
    timeout_seconds: float | None = None,
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
            message = (
                "Cannot generate classroom variants: missing classroom, "
                "time-slot, or proctor configuration."
            )
            logger.warning(message)
            result_queue.put(GenerationResult.failure(message))
            return

        # Important for Auto Variants:
        # do not ask the classroom assigner to materialise every possible
        # variant before the UI receives a result.  For a paged request, only
        # generate enough candidates to answer this page plus one look-ahead item
        # used to decide whether another page exists.
        #
        # page_limit gates the total number of full-schedule variants
        # (max_options_per_schedule). It must NOT be reused as the per-day limit:
        # max_options_per_day caps room allocations for a single date, and
        # setting it to page_limit lets one busy date exhaust the quota on its
        # own, falsely reporting "no more variants" while other dates still have
        # unexplored allocations. Leave per-day unbounded and let the per-schedule
        # cap drive paging.
        page_limit = None if cap is None else offset + cap + 1

        variant_iter = ClassroomAssigner.assign_variants(
            schedule,
            courses,
            selected_programs,
            classrooms,
            time_slots,
            proctor_config,
            allow_unassigned=allow_unassigned_classrooms,
            max_options_per_day=None,
            max_options_per_schedule=page_limit,
        )

        if cap is None:
            if timeout_seconds is not None:
                deadline = time.perf_counter() + timeout_seconds
                batch = []
                still_more = False
                for variant in islice(variant_iter, offset, None):
                    if time.perf_counter() > deadline:
                        still_more = True
                        break
                    batch.append(variant)
            else:
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
            GenerationResult.ok(
                {period_key: batch},
                courses_by_id,
                {period_key} if still_more else set(),
            )
        )
    except Exception as exc:
        logger.exception("Classroom variant process failed")
        result_queue.put(GenerationResult.failure(str(exc)))


class _KindTaggedQueue:
    """Wrap a result queue so every payload is tagged with its task kind.

    A single persistent worker serves both "date_options" and "variants" tasks
    over one shared result queue. If a task is stopped/switched while a result is
    still pending, the next poll could read that stale result and merge it as the
    wrong kind. Tagging each result lets the UI discard results whose kind does
    not match the batch it is currently waiting for.
    """

    def __init__(self, inner, kind: str) -> None:
        self._inner = inner
        self._kind = kind

    def put(self, item) -> None:
        self._inner.put((self._kind, item))


def _course_signature(course: Course) -> tuple:
    """Stable course data key for reusing a variant cursor safely."""
    offerings_key = tuple(
        (
            offering.program_id,
            offering.year,
            offering.semester,
            offering.requirement,
            offering.student_count,
        )
        for offering in course.offerings
    )
    return (course.id, course.evaluation_type, offerings_key)


def _variant_request_key(
    period_key: str,
    schedule: Schedule,
    courses: list[Course],
    selected_programs: list[str],
    settings: Settings,
    classrooms: list[Classroom],
    time_slots: list[TimeSlot],
    proctor_config: ProctorConfig,
    allow_unassigned_classrooms: bool,
) -> tuple:
    """Return a key identifying one classroom-variant stream.

    The persistent worker keeps the generator for this key alive. As long as the
    next request has the same key and the expected offset, the worker continues
    exactly where the previous block stopped instead of rebuilding and skipping
    all earlier classroom combinations again.
    """
    sorting_key = tuple(
        (rule.priority, rule.criterion.value)
        for rule in settings.sorting.rules
    )
    return (
        period_key,
        tuple(sorted(schedule.assignments.items())),
        tuple(sorted(_course_signature(course) for course in courses)),
        tuple(selected_programs),
        tuple((room.room_id, room.capacity) for room in classrooms),
        tuple(slot.time for slot in time_slots),
        proctor_config.students_per_proctor,
        allow_unassigned_classrooms,
        sorting_key,
    )


def _build_variant_iterator(
    schedule: Schedule,
    courses: list[Course],
    selected_programs: list[str],
    classrooms: list[Classroom],
    time_slots: list[TimeSlot],
    proctor_config: ProctorConfig,
    allow_unassigned_classrooms: bool,
) -> Iterator[Schedule]:
    """Create an unlimited lazy classroom-variant iterator for one date block."""
    return ClassroomAssigner.assign_variants(
        schedule,
        courses,
        selected_programs,
        classrooms,
        time_slots,
        proctor_config,
        allow_unassigned=allow_unassigned_classrooms,
        max_options_per_day=None,
        max_options_per_schedule=None,
    )


def _skip_variants(iterator: Iterator[Schedule], offset: int) -> int:
    """Advance ``iterator`` by up to ``offset`` items and return skipped count."""
    skipped = 0
    while skipped < offset:
        try:
            next(iterator)
        except StopIteration:
            break
        skipped += 1
    return skipped


def _take_variant_page(
    state: dict, cap: int | None, deadline: float | None = None
) -> tuple[list[Schedule], bool]:
    """Take the next page from a persistent variant cursor.

    One look-ahead item is kept in ``state['overflow']`` to answer the
    "has more" question without dropping that item from the next block.

    If ``deadline`` (absolute perf_counter timestamp) is provided and exceeded
    mid-collection, returns the partial batch with ``still_more=True``.
    """
    iterator: Iterator[Schedule] = state["iterator"]
    overflow: list[Schedule] = state["overflow"]

    if cap is None:
        batch = list(overflow)
        overflow.clear()
        if deadline is None:
            batch.extend(iterator)
            state["emitted"] += len(batch)
            return batch, False
        # Timeout-bounded unbounded collection.
        for item in iterator:
            if time.perf_counter() > deadline:
                state["emitted"] += len(batch)
                return batch, True
            batch.append(item)
        state["emitted"] += len(batch)
        return batch, False

    batch: list[Schedule] = []
    while len(batch) < cap:
        if deadline is not None and time.perf_counter() > deadline:
            state["emitted"] += len(batch)
            return batch, True

        if overflow:
            batch.append(overflow.pop(0))
            continue

        try:
            batch.append(next(iterator))
        except StopIteration:
            state["emitted"] += len(batch)
            return batch, False

    try:
        overflow.append(next(iterator))
        still_more = True
    except StopIteration:
        still_more = False

    state["emitted"] += len(batch)
    return batch, still_more


def _run_classroom_variants_from_state(
    result_queue,
    variant_states: dict[tuple, dict],
    period_key: str,
    schedule: Schedule,
    courses: list[Course],
    selected_programs: list[str],
    settings: Settings | None = None,
    cap: int | None = None,
    offset: int = 0,
    classrooms: list[Classroom] | None = None,
    time_slots: list[TimeSlot] | None = None,
    proctor_config: ProctorConfig | None = None,
    allow_unassigned_classrooms: bool = False,
    timeout_seconds: float | None = None,
) -> None:
    """Stateful Auto Variants implementation used by the persistent worker."""
    try:
        active_settings = settings or Settings(
            thresholds=ThresholdSettings(),
            sorting=SortingConfig(),
        )

        if not classrooms or not time_slots or proctor_config is None:
            message = (
                "Cannot generate classroom variants: missing classroom, "
                "time-slot, or proctor configuration."
            )
            logger.warning(message)
            result_queue.put(GenerationResult.failure(message))
            return

        request_key = _variant_request_key(
            period_key,
            schedule,
            courses,
            selected_programs,
            active_settings,
            classrooms,
            time_slots,
            proctor_config,
            allow_unassigned_classrooms,
        )

        state = variant_states.get(request_key)
        if state is not None and state.get("emitted") != offset:
            logger.warning(
                "Stale classroom variant pagination state detected for %s: "
                "expected offset %s, received offset %s. Rebuilding iterator.",
                period_key,
                state.get("emitted"),
                offset,
            )

        if state is None or state.get("emitted") != offset:
            iterator = _build_variant_iterator(
                schedule,
                courses,
                selected_programs,
                classrooms,
                time_slots,
                proctor_config,
                allow_unassigned_classrooms,
            )
            skipped = _skip_variants(iterator, offset)
            state = {
                "iterator": iterator,
                "overflow": [],
                "emitted": skipped,
            }
            # Replace only the stale/missing cursor for this exact request.
            # Do not clear other period/date cursors, because they may still be
            # valid and can continue paging independently.
            variant_states[request_key] = state

            if skipped < offset:
                courses_by_id = {course.id: course for course in courses}
                result_queue.put(
                    GenerationResult.ok({period_key: []}, courses_by_id, set())
                )
                return

        deadline = (
            time.perf_counter() + timeout_seconds if timeout_seconds is not None else None
        )
        batch, still_more = _take_variant_page(state, cap, deadline)

        courses_by_id = {course.id: course for course in courses}
        if active_settings.sorting.rules:
            batch = SortingEngine.sort(
                batch,
                courses,
                active_settings.sorting,
                selected_programs,
            )

        result_queue.put(
            GenerationResult.ok(
                {period_key: batch},
                courses_by_id,
                {period_key} if still_more else set(),
            )
        )
    except Exception as exc:
        logger.exception("Stateful classroom variant process failed")
        result_queue.put(GenerationResult.failure(str(exc)))


def _run_load_more_worker(task_queue, result_queue) -> None:
    """Persistent worker process for ResultsPanel Load More / Auto Load tasks.

    The worker keeps classroom-variant cursors alive between Auto Variants
    batches. That means block 2 continues from block 1 instead of recalculating
    all classroom combinations from the beginning and skipping the old results.
    """
    variant_states: dict[tuple, dict] = {}

    while True:
        task = task_queue.get()

        if task is None:
            return

        try:
            task_type, args, kwargs = task
        except ValueError:
            result_queue.put(
                ("error", GenerationResult.failure("Invalid background worker task."))
            )
            continue

        if task_type == "date_options":
            # A different date-options batch changes the visible date block. Drop
            # variant cursors so stale classroom blocks cannot be reused after the
            # user moves to another date schedule.
            variant_states.clear()
            _run_generation_process(
                _KindTaggedQueue(result_queue, "date_options"), *args, **kwargs
            )
        elif task_type == "variants":
            _run_classroom_variants_from_state(
                _KindTaggedQueue(result_queue, "variants"),
                variant_states,
                *args,
                **kwargs,
            )
        else:
            result_queue.put(
                (
                    "error",
                    GenerationResult.failure(
                        f"Unknown background worker task: {task_type}"
                    ),
                )
            )
