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


# Sentinel for "iterator is exhausted" — distinct from any real Schedule and
# from None, so a legitimately-yielded value is never mistaken for end-of-stream.
_ITER_DONE = object()


def _variant_cache_key(
    period_key: str,
    schedule: "Schedule",
    cap: "int | None",
    classrooms: "list[Classroom]",
    time_slots: "list[TimeSlot]",
    allow_unassigned: bool,
) -> tuple:
    """Stable identity for a paged variant request.

    Two Load More clicks belong to the same lazy stream only when every input
    that shapes the generator is identical. The fixed date block
    (schedule.assignments) plus the room/slot inputs fully determine the variant
    sequence, so a change in any of them must start a fresh generator rather than
    resume a stale one.
    """
    return (
        period_key,
        tuple(sorted(schedule.assignments.items())),
        cap,
        tuple(room.room_id for room in classrooms),
        tuple(slot.time for slot in time_slots),
        allow_unassigned,
    )


def _build_variant_iterator(
    schedule: "Schedule",
    courses: "list[Course]",
    selected_programs: "list[str]",
    classrooms: "list[Classroom]",
    time_slots: "list[TimeSlot]",
    proctor_config: "ProctorConfig",
    allow_unassigned: bool,
) -> "Iterator[Schedule]":
    """Build the raw, fully-lazy variant generator with no per-schedule cap.

    Paging is driven by *consuming* this generator one page at a time (see
    _ResumableVariantPager), not by re-running it with a growing limit. The
    assigner is lazy all the way down (room distributions, per-day allocations,
    and the cross-date DFS are all generators), so there is no per-day cap and no
    valid option is dropped — the first page returns without materialising the
    full search space.
    """
    return ClassroomAssigner.assign_variants(
        schedule,
        courses,
        selected_programs,
        classrooms,
        time_slots,
        proctor_config,
        allow_unassigned=allow_unassigned,
        max_options_per_schedule=None,
    )


class _ResumableVariantPager:
    """Retain live variant generators across Load More calls.

    The persistent worker outlives any single page request, so it can keep the
    generator parked exactly where the previous page stopped. The next
    contiguous request resumes from that point — O(page) work — instead of
    rebuilding the generator and discarding `offset` items first (O(offset)
    per page, i.e. O(N^2) over a full scroll). A non-contiguous offset (e.g. the
    user jumped or the inputs changed) transparently falls back to a fresh
    generator.
    """

    def __init__(self) -> None:
        # key -> {"iter": Iterator[Schedule], "next_offset": int}
        self._parked: dict[tuple, dict] = {}

    def page(
        self,
        key: tuple,
        build_iter,
        offset: int,
        cap: "int | None",
    ) -> "tuple[list, bool]":
        """Return (batch, still_more) for one page, resuming when possible."""
        parked = self._parked.pop(key, None)
        if parked is not None and parked["next_offset"] == offset:
            variant_iter = parked["iter"]
        else:
            variant_iter = build_iter()
            # Fresh stream (or a non-contiguous jump): skip to the requested
            # offset once. Subsequent contiguous pages resume without re-skipping.
            for _ in range(offset):
                if next(variant_iter, _ITER_DONE) is _ITER_DONE:
                    return [], False

        if cap is None:
            return list(variant_iter), False

        batch = list(islice(variant_iter, cap))

        # One look-ahead decides "is there another page" without forcing the
        # rest of the stream. Park the look-ahead back onto the generator so the
        # next page does not drop it.
        lookahead = next(variant_iter, _ITER_DONE)
        still_more = lookahead is not _ITER_DONE
        if still_more:
            self._parked[key] = {
                "iter": chain([lookahead], variant_iter),
                "next_offset": offset + len(batch),
            }
        return batch, still_more


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
    pager: "_ResumableVariantPager | None" = None,
) -> None:
    """Generate classroom/time-slot variants for one already-chosen date schedule.

    This does not run the date generator again. It reuses schedule.assignments as
    the fixed date block and expands only classroom/time-slot allocations for it.

    When a `pager` is supplied (the persistent Load More worker always supplies
    one), the variant generator is retained between pages so each Load More
    resumes from where the last page stopped. Without a pager (a one-shot call),
    a fresh generator is built and advanced to `offset` for this single page.
    """
    try:
        active_settings = settings or Settings(
            thresholds=ThresholdSettings(),
            sorting=SortingConfig(),
        )

        if not classrooms or not time_slots or proctor_config is None:
            result_queue.put(
                GenerationResult.ok(
                    {period_key: []}, {c.id: c for c in courses}, set()
                )
            )
            return

        def build_iter() -> "Iterator[Schedule]":
            return _build_variant_iterator(
                schedule,
                courses,
                selected_programs,
                classrooms,
                time_slots,
                proctor_config,
                allow_unassigned_classrooms,
            )

        active_pager = pager if pager is not None else _ResumableVariantPager()
        key = _variant_cache_key(
            period_key,
            schedule,
            cap,
            classrooms,
            time_slots,
            allow_unassigned_classrooms,
        )
        batch, still_more = active_pager.page(key, build_iter, offset, cap)

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


def _run_load_more_worker(task_queue, result_queue) -> None:
    """Persistent worker process for ResultsPanel Load More / Auto Load tasks.

    The old implementation opened a fresh multiprocessing.Process for every
    Load More / Auto Dates / Auto Variants batch. On Windows, each new process
    can briefly flash a small console window. This worker is started once per
    period and then reused for subsequent batches, so Auto Load does not create
    a new Python process for every page.
    """
    # One pager lives for the whole worker lifetime, so every "variants" Load
    # More resumes the same parked generator instead of rebuilding it and
    # re-discarding `offset` items each page.
    variant_pager = _ResumableVariantPager()

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
            _run_generation_process(
                _KindTaggedQueue(result_queue, "date_options"), *args, **kwargs
            )
        elif task_type == "variants":
            _run_classroom_variants_process(
                _KindTaggedQueue(result_queue, "variants"),
                *args,
                pager=variant_pager,
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
