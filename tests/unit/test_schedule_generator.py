"""
Unit Tests: ScheduleGenerator
-------------------------------
Tests for backtracking schedule generation logic.
"""
import itertools
from datetime import date
from typing import List

import pytest

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.domain.threshold import Criterion, ThresholdEntry, ThresholdSettings
from src.domain.threshold_filter import ThresholdFilter
from src.engine.schedule_generator import ScheduleGenerator


def _make_course(course_id: str, program_id: str, year: int, semester: str, requirement: str) -> Course:
    course = Course(
        id=course_id,
        name=f"Course {course_id}",
        instructor="Dr. Test",
        evaluation_type="Exam",
    )
    course.add_offering(CourseOffering(
        program_id=program_id,
        year=year,
        semester=semester,
        requirement=requirement,
    ))
    return course


def _make_period(start: date, end: date, excluded=None) -> ExamPeriod:
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(start, end)],
        excluded_dates=excluded or set(),
    )


def _generator(selected_programs: List[str]) -> ScheduleGenerator:
    return ScheduleGenerator(ExactConflictStrategy(selected_programs))


def _schedule_signature(schedule: Schedule) -> tuple:
    return tuple(
        sorted((course_id, exam_date.isoformat()) for course_id, exam_date in schedule.assignments.items())
    )


def _brute_force_schedules(
    courses: list[Course],
    period: ExamPeriod,
    selected_programs: list[str],
) -> list[Schedule]:
    strategy = ExactConflictStrategy(selected_programs)
    valid_dates = period.get_valid_dates()
    schedules: list[Schedule] = []

    def rec(index: int, assignments: dict[str, date]) -> None:
        if index >= len(courses):
            schedules.append(Schedule(period=period, assignments=dict(assignments)))
            return

        course = courses[index]
        for exam_date in valid_dates:
            if any(
                assignments.get(other.id) == exam_date
                and strategy.is_conflict(course, other)
                for other in courses[:index]
            ):
                continue
            assignments[course.id] = exam_date
            rec(index + 1, assignments)
            del assignments[course.id]

    rec(0, {})
    return schedules


def _threshold_settings(criterion: Criterion, k: int) -> ThresholdSettings:
    return ThresholdSettings(entries=(ThresholdEntry(criterion, True, k),))


def _assert_threshold_equivalence(
    *,
    courses: list[Course],
    period: ExamPeriod,
    selected_programs: list[str],
    criterion: Criterion,
    k: int,
    expect_threshold_prunes: bool,
) -> None:
    settings = _threshold_settings(criterion, k)
    gen = ScheduleGenerator(
        ExactConflictStrategy(selected_programs),
        threshold_settings=settings,
        selected_programs=selected_programs,
    )

    optimized = list(gen.generate_schedules(courses, period))
    brute_force_valid = [
        schedule
        for schedule in _brute_force_schedules(courses, period, selected_programs)
        if ThresholdFilter.is_valid(schedule, courses, settings, selected_programs)
    ]

    assert {_schedule_signature(schedule) for schedule in optimized} == {
        _schedule_signature(schedule) for schedule in brute_force_valid
    }
    assert len(optimized) == len(
        {_schedule_signature(schedule) for schedule in optimized}
    )
    if expect_threshold_prunes:
        assert gen.last_metrics.threshold_prunes > 0


def test_no_courses_yields_no_schedules():
    gen = _generator(["83101"])
    period = _make_period(date(2026, 1, 5), date(2026, 1, 7))
    assert list(gen.generate_schedules([], period)) == []


def test_single_course_single_date_yields_one_schedule():
    gen = _generator(["83101"])
    course = _make_course("11111", "83101", 1, "FALL", "Obligatory")
    period = _make_period(date(2026, 1, 5), date(2026, 1, 5))  # Monday
    schedules = list(gen.generate_schedules([course], period))
    assert len(schedules) == 1
    assert schedules[0].assignments["11111"] == date(2026, 1, 5)


def test_two_non_conflicting_courses_can_share_same_date():
    gen = _generator(["83101"])
    c1 = _make_course("11111", "83101", 1, "FALL", "Obligatory")
    c2 = _make_course("22222", "83101", 2, "FALL", "Obligatory")  # different year → no conflict
    period = _make_period(date(2026, 1, 5), date(2026, 1, 5))
    schedules = list(gen.generate_schedules([c1, c2], period))
    assert len(schedules) == 1
    assert schedules[0].assignments["11111"] == date(2026, 1, 5)
    assert schedules[0].assignments["22222"] == date(2026, 1, 5)


def test_two_conflicting_courses_must_have_different_dates():
    gen = _generator(["83101"])
    c1 = _make_course("11111", "83101", 1, "FALL", "Obligatory")
    c2 = _make_course("22222", "83101", 1, "FALL", "Obligatory")
    period = _make_period(date(2026, 1, 5), date(2026, 1, 5))  # only 1 date
    assert list(gen.generate_schedules([c1, c2], period)) == []


def test_two_conflicting_courses_with_two_dates_yield_two_schedules():
    gen = _generator(["83101"])
    c1 = _make_course("11111", "83101", 1, "FALL", "Obligatory")
    c2 = _make_course("22222", "83101", 1, "FALL", "Obligatory")
    period = _make_period(date(2026, 1, 5), date(2026, 1, 6))  # Mon + Tue
    schedules = list(gen.generate_schedules([c1, c2], period))
    assert len(schedules) == 2
    for s in schedules:
        assert s.assignments["11111"] != s.assignments["22222"]


def test_all_schedules_cover_all_courses():
    gen = _generator(["83101"])
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Obligatory"),
        _make_course("22222", "83101", 1, "FALL", "Obligatory"),
        _make_course("33333", "83101", 1, "FALL", "Obligatory"),
    ]
    expected_ids = {c.id for c in courses}
    period = _make_period(date(2026, 1, 5), date(2026, 1, 9))  # 5 weekdays
    schedules = list(gen.generate_schedules(courses, period))
    assert len(schedules) > 0
    for s in schedules:
        assert set(s.assignments.keys()) == expected_ids


def test_impossible_case_yields_nothing():
    gen = _generator(["83101"])
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Obligatory"),
        _make_course("22222", "83101", 1, "FALL", "Obligatory"),
        _make_course("33333", "83101", 1, "FALL", "Obligatory"),
    ]
    period = _make_period(date(2026, 1, 5), date(2026, 1, 6))  # 3 courses, only 2 dates
    assert list(gen.generate_schedules(courses, period)) == []


def test_mcv_heuristic_produces_valid_schedules():
    a = Course(id="11111", name="A", instructor="x", evaluation_type="Exam")
    a.add_offering(CourseOffering("83101", 1, "FALL", "Obligatory"))
    a.add_offering(CourseOffering("83102", 1, "FALL", "Obligatory"))
    b = _make_course("22222", "83101", 1, "FALL", "Obligatory")  # conflicts with A
    c = _make_course("33333", "83102", 1, "FALL", "Obligatory")  # conflicts with A but not B

    gen = _generator(["83101", "83102"])
    period = _make_period(date(2026, 1, 5), date(2026, 1, 7))
    schedules = list(gen.generate_schedules([a, b, c], period))
    assert len(schedules) > 0
    for s in schedules:
        assert s.assignments["11111"] != s.assignments["22222"]
        assert s.assignments["11111"] != s.assignments["33333"]


def test_all_elective_courses_can_share_one_date():
    gen = _generator(["83101"])
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Elective"),
        _make_course("22222", "83101", 1, "FALL", "Elective"),
        _make_course("33333", "83101", 1, "FALL", "Elective"),
    ]
    period = _make_period(date(2026, 1, 5), date(2026, 1, 5))  # single date
    schedules = list(gen.generate_schedules(courses, period))
    assert len(schedules) == 1
    assert len(set(schedules[0].assignments.values())) == 1


def test_independent_programs_yield_cartesian_product():
    a1 = _make_course("11111", "83101", 1, "FALL", "Obligatory")
    a2 = _make_course("22222", "83101", 1, "FALL", "Obligatory")
    b1 = _make_course("33333", "83102", 1, "FALL", "Obligatory")

    gen = _generator(["83101", "83102"])
    period = _make_period(date(2026, 1, 5), date(2026, 1, 6))  # 2 weekdays
    schedules = list(gen.generate_schedules([a1, a2, b1], period))
    assert len(schedules) == 4  # 2 orderings × 2 placements for b1


def test_generator_respects_saturday_exclusion():
    gen = _generator(["83101"])
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Obligatory"),
        _make_course("22222", "83101", 1, "FALL", "Obligatory"),
    ]
    # Fri 09-Jan, Sat 10-Jan (auto-excluded), Sun 11-Jan
    period = _make_period(date(2026, 1, 9), date(2026, 1, 11))
    schedules = list(gen.generate_schedules(courses, period))
    for s in schedules:
        for d in s.assignments.values():
            assert d.weekday() != 5


def test_prefilter_metrics_count_removed_invalid_period_dates():
    gen = _generator(["83101"])
    course = _make_course("11111", "83101", 1, "FALL", "Obligatory")
    period = _make_period(
        date(2026, 1, 9),
        date(2026, 1, 11),
        excluded={date(2026, 1, 11)},
    )

    schedules = list(gen.generate_schedules([course], period))

    assert [_schedule_signature(schedule) for schedule in schedules] == [
        (("11111", "2026-01-09"),)
    ]
    assert gen.last_metrics.prefiltered_candidates_removed == 2


def test_forward_checking_prunes_impossible_conflict_domains():
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Obligatory"),
        _make_course("22222", "83101", 1, "FALL", "Obligatory"),
        _make_course("33333", "83101", 1, "FALL", "Obligatory"),
    ]
    period = _make_period(date(2026, 1, 5), date(2026, 1, 6))
    gen = _generator(["83101"])

    assert list(gen.generate_schedules(courses, period)) == []
    assert gen.last_metrics.domain_prunes > 0
    assert gen.last_metrics.conflict_prunes > 0


def test_safe_threshold_pruning_matches_final_threshold_filter():
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Obligatory"),
        _make_course("22222", "83101", 2, "FALL", "Obligatory"),
    ]
    period = _make_period(date(2026, 1, 5), date(2026, 1, 6))
    settings = ThresholdSettings(
        entries=(ThresholdEntry(Criterion.MAX_EXAMS_PER_DAY, True, 1),)
    )
    gen = ScheduleGenerator(
        ExactConflictStrategy(["83101"]),
        threshold_settings=settings,
        selected_programs=["83101"],
    )

    optimized = list(gen.generate_schedules(courses, period))
    brute_force_valid = [
        schedule for schedule in _brute_force_schedules(courses, period, ["83101"])
        if ThresholdFilter.is_valid(schedule, courses, settings, ["83101"])
    ]

    assert {_schedule_signature(schedule) for schedule in optimized} == {
        _schedule_signature(schedule) for schedule in brute_force_valid
    }
    assert gen.last_metrics.threshold_prunes > 0


def test_all_threshold_criteria_disabled_match_generator_without_thresholds():
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Obligatory"),
        _make_course("22222", "83101", 1, "FALL", "Elective"),
        _make_course("33333", "83102", 2, "FALL", "Obligatory"),
    ]
    period = _make_period(date(2026, 1, 5), date(2026, 1, 7))
    selected_programs = ["83101", "83102"]
    disabled_settings = ThresholdSettings(
        entries=tuple(
            ThresholdEntry(criterion, False, 1)
            for criterion in Criterion
        )
    )

    baseline = [
        _schedule_signature(schedule)
        for schedule in _generator(selected_programs).generate_schedules(
            courses,
            period,
        )
    ]
    gen = ScheduleGenerator(
        ExactConflictStrategy(selected_programs),
        threshold_settings=disabled_settings,
        selected_programs=selected_programs,
    )
    with_disabled_thresholds = [
        _schedule_signature(schedule)
        for schedule in gen.generate_schedules(courses, period)
    ]

    assert with_disabled_thresholds == baseline
    assert gen.last_metrics.threshold_prunes == 0


def test_spread_threshold_remains_final_filter_only():
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Obligatory"),
        _make_course("22222", "83101", 1, "FALL", "Obligatory"),
    ]
    period = _make_period(date(2026, 1, 5), date(2026, 1, 6))
    selected_programs = ["83101"]
    settings = ThresholdSettings(
        entries=(
            ThresholdEntry(Criterion.MIN_DAYS_EXAM_PERIOD_SPREAD, True, 2),
        )
    )
    gen = ScheduleGenerator(
        ExactConflictStrategy(selected_programs),
        threshold_settings=settings,
        selected_programs=selected_programs,
    )

    generated = list(gen.generate_schedules(courses, period))
    filtered = [
        schedule for schedule in generated
        if ThresholdFilter.is_valid(
            schedule,
            courses,
            settings,
            selected_programs,
        )
    ]

    assert generated
    assert filtered == []
    assert gen.last_metrics.threshold_prunes == 0


def test_max_exams_per_day_pruning_matches_threshold_filter_for_k0_and_k1():
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Obligatory"),
        _make_course("22222", "83102", 2, "FALL", "Elective"),
    ]
    period = _make_period(date(2026, 1, 5), date(2026, 1, 6))

    _assert_threshold_equivalence(
        courses=courses,
        period=period,
        selected_programs=["83101", "83102"],
        criterion=Criterion.MAX_EXAMS_PER_DAY,
        k=0,
        expect_threshold_prunes=True,
    )
    _assert_threshold_equivalence(
        courses=courses,
        period=period,
        selected_programs=["83101", "83102"],
        criterion=Criterion.MAX_EXAMS_PER_DAY,
        k=1,
        expect_threshold_prunes=True,
    )


def test_max_elective_collisions_pruning_matches_threshold_filter_for_k0_and_k1():
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Elective"),
        _make_course("22222", "83101", 1, "FALL", "Elective"),
        _make_course("33333", "83101", 1, "FALL", "Elective"),
        _make_course("44444", "83102", 1, "FALL", "Elective"),
    ]
    period = _make_period(date(2026, 1, 5), date(2026, 1, 6))

    _assert_threshold_equivalence(
        courses=courses,
        period=period,
        selected_programs=["83101", "83102"],
        criterion=Criterion.MAX_ELECTIVE_COLLISIONS,
        k=0,
        expect_threshold_prunes=True,
    )
    _assert_threshold_equivalence(
        courses=courses,
        period=period,
        selected_programs=["83101", "83102"],
        criterion=Criterion.MAX_ELECTIVE_COLLISIONS,
        k=1,
        expect_threshold_prunes=True,
    )


def test_min_days_between_mandatory_pruning_matches_threshold_filter_edges():
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Obligatory"),
        _make_course("22222", "83101", 1, "FALL", "Obligatory"),
        _make_course("33333", "83101", 2, "FALL", "Obligatory"),
        _make_course("44444", "83102", 1, "FALL", "Obligatory"),
    ]
    period = _make_period(date(2026, 1, 5), date(2026, 1, 7))

    _assert_threshold_equivalence(
        courses=courses,
        period=period,
        selected_programs=["83101", "83102"],
        criterion=Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS,
        k=0,
        expect_threshold_prunes=False,
    )
    _assert_threshold_equivalence(
        courses=courses,
        period=period,
        selected_programs=["83101", "83102"],
        criterion=Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS,
        k=1,
        expect_threshold_prunes=False,
    )
    _assert_threshold_equivalence(
        courses=courses,
        period=period,
        selected_programs=["83101", "83102"],
        criterion=Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS,
        k=2,
        expect_threshold_prunes=True,
    )


def test_min_days_between_any_pruning_matches_threshold_filter_edges():
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Obligatory"),
        _make_course("22222", "83101", 1, "FALL", "Elective"),
        _make_course("33333", "83101", 1, "FALL", "Elective"),
        _make_course("44444", "83102", 2, "FALL", "Elective"),
    ]
    period = _make_period(date(2026, 1, 5), date(2026, 1, 7))

    _assert_threshold_equivalence(
        courses=courses,
        period=period,
        selected_programs=["83101", "83102"],
        criterion=Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS,
        k=0,
        expect_threshold_prunes=False,
    )
    _assert_threshold_equivalence(
        courses=courses,
        period=period,
        selected_programs=["83101", "83102"],
        criterion=Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS,
        k=1,
        expect_threshold_prunes=True,
    )


def test_optimized_generator_matches_bruteforce_for_electives_and_program_isolation():
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Elective"),
        _make_course("22222", "83101", 1, "FALL", "Elective"),
        _make_course("33333", "83102", 1, "FALL", "Obligatory"),
        _make_course("44444", "83102", 1, "FALL", "Obligatory"),
    ]
    period = _make_period(date(2026, 1, 5), date(2026, 1, 6))
    selected_programs = ["83101", "83102"]
    gen = _generator(selected_programs)

    optimized = list(gen.generate_schedules(courses, period))
    brute_force = _brute_force_schedules(courses, period, selected_programs)

    assert {_schedule_signature(schedule) for schedule in optimized} == {
        _schedule_signature(schedule) for schedule in brute_force
    }
    assert len(optimized) == len(
        {_schedule_signature(schedule) for schedule in optimized}
    )


def test_generator_output_is_deterministic_across_repeated_runs():
    courses = [
        _make_course("11111", "83101", 1, "FALL", "Obligatory"),
        _make_course("22222", "83101", 2, "FALL", "Obligatory"),
        _make_course("33333", "83102", 1, "FALL", "Obligatory"),
    ]
    period = _make_period(date(2026, 1, 5), date(2026, 1, 7))

    first = [
        _schedule_signature(schedule)
        for schedule in _generator(["83101", "83102"]).generate_schedules(
            courses,
            period,
        )
    ]
    second = [
        _schedule_signature(schedule)
        for schedule in _generator(["83101", "83102"]).generate_schedules(
            courses,
            period,
        )
    ]

    assert first == second


# 3 independent program pairs × 2 conflicting courses × 10 weekdays
# → (10×9)^3 = 729,000 valid schedules; sample 500 to verify invariant and speed
def test_high_scale_combinatorial_stress():
    strategy_programs = ["83101", "83102", "83103"]
    pairs = [
        ("11111", "22222", "83101"),
        ("33333", "44444", "83102"),
        ("55555", "66666", "83103"),
    ]
    courses = []
    for id1, id2, prog in pairs:
        courses.append(_make_course(id1, prog, 1, "FALL", "Obligatory"))
        courses.append(_make_course(id2, prog, 1, "FALL", "Obligatory"))

    # Mon 05-Jan to Fri 16-Jan 2026: 10 weekdays (Sat 10-Jan auto-excluded)
    period = _make_period(date(2026, 1, 5), date(2026, 1, 16))
    gen = _generator(strategy_programs)
    strategy = ExactConflictStrategy(strategy_programs)

    sample = list(itertools.islice(gen.generate_schedules(courses, period), 500))

    assert len(sample) == 500
    assert gen.last_metrics.schedules_produced >= 500
    assert gen.last_metrics.nodes_visited >= gen.last_metrics.schedules_produced
    assert gen.last_metrics.conflict_prunes > 0

    all_ids = {c.id for c in courses}
    for s in sample:
        assert set(s.assignments.keys()) == all_ids
        ids = list(s.assignments.keys())
        for i, id_a in enumerate(ids):
            for id_b in ids[i + 1:]:
                if s.assignments[id_a] == s.assignments[id_b]:
                    ca = next(c for c in courses if c.id == id_a)
                    cb = next(c for c in courses if c.id == id_b)
                    assert not strategy.is_conflict(ca, cb), (
                        f"Conflict violated: {id_a} and {id_b} share {s.assignments[id_a]}"
                    )
