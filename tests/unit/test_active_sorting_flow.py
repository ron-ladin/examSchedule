"""Regression tests for active Result Ranking / sorting flow.

These tests cover the user-visible behaviour where a sort selected in Result
Ranking should remain active for cached results and for later generation batches,
without forcing a full regeneration.
"""

import queue
from datetime import date

from src.controller import DesktopController
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.domain.settings import Settings
from src.domain.sorting import SortCriterion, SortingConfig, SortRule
from src.domain.sorting_engine import SortingEngine
from src.domain.threshold import ThresholdSettings
from src.engine.generation_workers import _run_date_options_from_state

PROGRAM = "83101"
SEMESTER = "FALL"
PERIOD_KEY = "FALL - Aleph"

BASE_PERIOD = ExamPeriod(
    semester=SEMESTER,
    moed="Aleph",
    date_ranges=[(date(2026, 1, 5), date(2026, 1, 30))],
)


class _SimpleQueue:
    def __init__(self) -> None:
        self._queue = queue.Queue()

    def put(self, item) -> None:
        self._queue.put(item)

    def get(self, timeout: float = 2):
        return self._queue.get(timeout=timeout)


def _mandatory(course_id: str) -> Course:
    course = Course(
        id=course_id,
        name=f"Course {course_id}",
        instructor="Dr. Sort",
        evaluation_type="Exam",
    )
    course.add_offering(
        CourseOffering(
            program_id=PROGRAM,
            year=1,
            semester=SEMESTER,
            requirement="Obligatory",
        )
    )
    return course


def _courses() -> list[Course]:
    return [_mandatory("11111"), _mandatory("22222"), _mandatory("33333")]


def _two_course_generation_courses() -> list[Course]:
    return [_mandatory("11111"), _mandatory("22222")]


def _schedule(assignments: dict[str, date]) -> Schedule:
    return Schedule(period=BASE_PERIOD, assignments=assignments)


def _settings_with_sort(*criteria: SortCriterion) -> Settings:
    return Settings(
        thresholds=ThresholdSettings(),
        sorting=SortingConfig.from_ordered_criteria(criteria),
    )


def _single_sort(criterion: SortCriterion) -> SortingConfig:
    return SortingConfig(rules=(SortRule(priority=1, criterion=criterion),))


def _min_gap_score(schedule: Schedule, courses: list[Course]) -> float:
    return SortingEngine.score(
        schedule,
        courses,
        SortCriterion.SORT_MIN_DAYS_MANDATORY,
        selected_programs=[PROGRAM],
    )


def test_resort_can_switch_between_sort_criteria_without_regeneration():
    """Changing Result Ranking should re-order cached schedules in place.

    This is the behaviour expected in the UI: changing sort does not change a
    schedule's assignments and does not generate again; it only changes which
    cached schedule appears first.
    """
    courses = _courses()
    spread_out = _schedule(
        {
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 15),
            "33333": date(2026, 1, 25),
        }
    )  # min mandatory gap = 10, max exams/day = 1
    dense_day = _schedule(
        {
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 8),
            "33333": date(2026, 1, 5),
        }
    )  # min mandatory gap = 0, max exams/day = 2

    ctrl = DesktopController()
    ctrl._courses = courses
    ctrl._selected_programs = [PROGRAM]
    ctrl._settings = _settings_with_sort(SortCriterion.SORT_MAX_EXAMS_PER_DAY)

    initially_sorted = ctrl.cache_generated_results(
        {PERIOD_KEY: [spread_out, dense_day]}
    )
    # 3.5 is lower-is-better (ASCENDING): spread_out (max 1/day) beats dense_day (max 2/day).
    assert initially_sorted[PERIOD_KEY] == [spread_out, dense_day]

    resorted = ctrl.resort(_single_sort(SortCriterion.SORT_MIN_DAYS_MANDATORY))

    assert ctrl.results_stale is False
    assert resorted[PERIOD_KEY] == [spread_out, dense_day]


def test_incremental_generation_batches_use_current_active_sort():
    """New generation batches should be sorted by the currently active rules."""
    courses = _courses()
    spread_out = _schedule(
        {
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 15),
            "33333": date(2026, 1, 25),
        }
    )
    dense_day = _schedule(
        {
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 8),
            "33333": date(2026, 1, 5),
        }
    )
    medium_gap = _schedule(
        {
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 12),
            "33333": date(2026, 1, 20),
        }
    )

    ctrl = DesktopController()
    ctrl._courses = courses
    ctrl._selected_programs = [PROGRAM]

    ctrl.apply_sort(_single_sort(SortCriterion.SORT_MIN_DAYS_MANDATORY))
    first_partial = ctrl.cache_generated_results_incremental(
        {PERIOD_KEY: [dense_day, spread_out, medium_gap]}
    )
    assert first_partial[PERIOD_KEY] == [spread_out, medium_gap, dense_day]

    ctrl.apply_sort(_single_sort(SortCriterion.SORT_MAX_EXAMS_PER_DAY))
    second_partial = ctrl.cache_generated_results_incremental(
        {"FALL - Bet": [spread_out, dense_day]}
    )
    # 3.5 is lower-is-better (ASCENDING): spread_out (max 1/day) ranks before dense_day.
    assert second_partial["FALL - Bet"] == [spread_out, dense_day]


def test_stateful_date_options_sort_each_loaded_batch_with_active_rules():
    """Auto Dates / Load More batches should be sorted after each page is taken.

    The worker should continue generation with its cursor, then apply the active
    sorting config to the newly loaded page. This pins the behaviour where a sort
    chosen by the user stays active for later generated batches.
    """
    courses = _two_course_generation_courses()
    period = ExamPeriod(SEMESTER, "Aleph", [(date(2026, 1, 5), date(2026, 1, 8))])
    settings = _settings_with_sort(SortCriterion.SORT_MIN_DAYS_MANDATORY)
    states = {}
    result_queue = _SimpleQueue()
    offset = 0

    for _ in range(2):
        _run_date_options_from_state(
            result_queue,
            states,
            courses=courses,
            exam_periods=[period],
            selected_programs=[PROGRAM],
            settings=settings,
            cap=4,
            period_key=PERIOD_KEY,
            offset=offset,
        )
        result = result_queue.get()
        assert result.success, result.error

        batch = result.schedules_by_period[PERIOD_KEY]
        assert batch
        scores = [_min_gap_score(schedule, courses) for schedule in batch]
        assert scores == sorted(scores, reverse=True)

        offset += len(batch)
        if PERIOD_KEY not in result.truncated_periods:
            break
