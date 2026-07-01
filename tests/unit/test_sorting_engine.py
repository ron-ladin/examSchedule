"""
Unit Tests: SortingEngine  (SCRUM-283)
----------------------------------------
TDD tests for SortingEngine.sort(schedules, courses, config) based on
sprint3_source_of_truth.md sections 3.1–3.5.

The class is expected to live at:
    src.domain.sorting_engine.SortingEngine

Public contract assumed:
    SortingEngine.sort(
        schedules: List[Schedule],
        courses: List[Course],
        config: SortingConfig,
    ) -> List[Schedule]

All sort criteria are DESCENDING (higher metric = ranked first).
Priority 1 is the primary sort key; higher priority numbers are tie-breakers.
"""

import pytest
from datetime import date
from typing import List

from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.domain.sorting import (
    ASCENDING_CRITERIA,
    SortCriterion,
    SortRule,
    SortingConfig,
    sorts_descending,
)
from src.domain.sorting_engine import SortingEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROGRAM_A = "83101"
PROGRAM_B = "83102"
SEMESTER = "FALL"

BASE_PERIOD = ExamPeriod(
    semester=SEMESTER,
    moed="Aleph",
    date_ranges=[(date(2026, 1, 4), date(2026, 1, 31))],
)


def _offering(program: str, year: int, requirement: str) -> CourseOffering:
    return CourseOffering(
        program_id=program, year=year, semester=SEMESTER, requirement=requirement
    )


def _mandatory(course_id: str, program: str = PROGRAM_A, year: int = 1) -> Course:
    c = Course(
        id=course_id,
        name=f"Course {course_id}",
        instructor="Prof. X",
        evaluation_type="Exam",
    )
    c.add_offering(_offering(program, year, "Obligatory"))
    return c


def _elective(course_id: str, program: str = PROGRAM_A, year: int = 1) -> Course:
    c = Course(
        id=course_id,
        name=f"Elective {course_id}",
        instructor="Prof. Y",
        evaluation_type="Exam",
    )
    c.add_offering(_offering(program, year, "Elective"))
    return c


def _schedule(assignments: dict) -> Schedule:
    return Schedule(period=BASE_PERIOD, assignments=assignments)


def _config_single(criterion: SortCriterion, priority: int = 1) -> SortingConfig:
    return SortingConfig(rules=(SortRule(priority=priority, criterion=criterion),))


# ---------------------------------------------------------------------------
# Sort direction (single source of truth) — all five criteria sort DESCENDING
# ---------------------------------------------------------------------------

class TestSortDirection:
    """Direction map: per the SRS all five criteria sort DESCENDING."""

    @pytest.mark.parametrize(
        "criterion, expected_descending",
        [
            (SortCriterion.SORT_MIN_DAYS_MANDATORY, True),
            (SortCriterion.SORT_AVG_DAYS_ANY, True),
            (SortCriterion.SORT_EXAM_PERIOD_SPREAD, True),
            (SortCriterion.SORT_ELECTIVE_COLLISIONS, True),
            (SortCriterion.SORT_MAX_EXAMS_PER_DAY, True),
        ],
    )
    def test_sorts_descending_direction(self, criterion, expected_descending):
        assert sorts_descending(criterion) is expected_descending

    def test_ascending_criteria_is_empty(self):
        # SRS §3.1-3.5 mandate descending for all five; the flip mechanism stays
        # available but no criterion is currently ascending.
        assert ASCENDING_CRITERIA == frozenset()


# ---------------------------------------------------------------------------
# Per-criterion direction outcome (single source of truth for "better first").
#
# Each row builds a clearly-better and a clearly-worse schedule for one
# criterion and asserts the better one ranks first under that criterion alone.
# This replaces five near-identical per-class "ranks first" methods.
# ---------------------------------------------------------------------------

def _case_min_days_mandatory():
    courses = [_mandatory("11111"), _mandatory("22222")]
    better = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 12)})  # gap 7
    worse = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 7)})    # gap 2
    return courses, better, worse


def _case_avg_days_any():
    courses = [_mandatory("11111"), _elective("22222")]
    better = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 15)})  # avg 10
    worse = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 7)})    # avg 2
    return courses, better, worse


def _case_exam_period_spread():
    courses = [_mandatory("11111"), _mandatory("22222")]
    better = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 20)})  # spread 15
    worse = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 8)})    # spread 3
    return courses, better, worse


def _case_elective_collisions():
    # 3.3 sorts DESCENDING: the HIGHER collision count ranks first.
    courses = [_elective("11111"), _elective("22222")]
    better = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 5)})   # 1 collision
    worse = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 6)})    # 0 collisions
    return courses, better, worse


def _case_max_exams_per_day():
    # 3.5 sorts DESCENDING: the HIGHER max-exams-per-day ranks first.
    courses = [_mandatory("11111"), _mandatory("22222"), _mandatory("33333")]
    better = _schedule({  # max 2 exams/day
        "11111": date(2026, 1, 5), "22222": date(2026, 1, 5), "33333": date(2026, 1, 10),
    })
    worse = _schedule({  # max 1 exam/day
        "11111": date(2026, 1, 5), "22222": date(2026, 1, 6), "33333": date(2026, 1, 7),
    })
    return courses, better, worse


@pytest.mark.parametrize(
    "criterion, case_factory",
    [
        (SortCriterion.SORT_MIN_DAYS_MANDATORY, _case_min_days_mandatory),
        (SortCriterion.SORT_AVG_DAYS_ANY, _case_avg_days_any),
        (SortCriterion.SORT_EXAM_PERIOD_SPREAD, _case_exam_period_spread),
        (SortCriterion.SORT_ELECTIVE_COLLISIONS, _case_elective_collisions),
        (SortCriterion.SORT_MAX_EXAMS_PER_DAY, _case_max_exams_per_day),
    ],
)
def test_better_schedule_ranks_first(criterion, case_factory):
    """The better schedule for each criterion ranks first under the correct direction."""
    courses, better, worse = case_factory()
    result = SortingEngine.sort([worse, better], courses, _config_single(criterion))
    assert result[0] is better


# ---------------------------------------------------------------------------
# 3.1  SORT_MIN_DAYS_MANDATORY — multi-schedule ordering & group isolation
# ---------------------------------------------------------------------------

class TestSortMinDaysMandatory:
    """Criterion 3.1: descending by minimum gap between mandatory exams."""

    CRITERION = SortCriterion.SORT_MIN_DAYS_MANDATORY

    def test_equal_min_gaps_both_in_result(self):
        c1, c2 = _mandatory("11111"), _mandatory("22222")
        sched_a = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 10)})
        sched_b = _schedule({"11111": date(2026, 1, 6), "22222": date(2026, 1, 11)})

        result = SortingEngine.sort([sched_a, sched_b], [c1, c2], _config_single(self.CRITERION))
        assert len(result) == 2
        assert sched_a in result
        assert sched_b in result

    def test_descending_order_for_three_schedules(self):
        c1, c2 = _mandatory("11111"), _mandatory("22222")
        sched_a = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 15)})  # gap=10
        sched_b = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 10)})  # gap=5
        sched_c = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 7)})   # gap=2

        result = SortingEngine.sort(
            [sched_b, sched_c, sched_a], [c1, c2], _config_single(self.CRITERION)
        )
        assert result == [sched_a, sched_b, sched_c]


# ---------------------------------------------------------------------------
# 3.2  SORT_AVG_DAYS_ANY — descending by average gap between all exams
# ---------------------------------------------------------------------------

class TestSortAvgDaysAny:
    """Criterion 3.2: sort descending by average gap between any two exams."""

    CRITERION = SortCriterion.SORT_AVG_DAYS_ANY

    def test_electives_included_in_average_computation(self):
        """Criterion 3.2 covers mandatory AND elective courses."""
        c_mand, c_elec = _mandatory("11111"), _elective("22222")
        # sched_a: elective far from mandatory
        sched_a = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 20)})
        # sched_b: elective close to mandatory
        sched_b = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 6)})

        result = SortingEngine.sort(
            [sched_b, sched_a], [c_mand, c_elec], _config_single(self.CRITERION)
        )
        assert result[0] is sched_a


# ---------------------------------------------------------------------------
# 3.3  SORT_ELECTIVE_COLLISIONS — descending by elective collision count
# ---------------------------------------------------------------------------

class TestSortElectiveCollisions:
    """Criterion 3.3: DESCENDING by elective collision count (SRS §3.3 'בסדר יורד')."""

    CRITERION = SortCriterion.SORT_ELECTIVE_COLLISIONS

    def test_most_collisions_ranks_first(self):
        c1, c2 = _elective("11111"), _elective("22222")
        sched_a = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 5)})  # 1 collision
        sched_b = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 6)})  # 0 collisions

        result = SortingEngine.sort([sched_b, sched_a], [c1, c2], _config_single(self.CRITERION))
        assert result[0] is sched_a
        assert result[-1] is sched_b


# ---------------------------------------------------------------------------
# 3.4  SORT_EXAM_PERIOD_SPREAD — descending by first-to-last mandatory span
# ---------------------------------------------------------------------------

class TestSortExamPeriodSpread:
    """Criterion 3.4: sort descending by spread of mandatory exam period."""

    CRITERION = SortCriterion.SORT_EXAM_PERIOD_SPREAD

    def test_electives_not_counted_in_spread(self):
        mand = _mandatory("11111")
        elec = _elective("22222")
        mand2 = _mandatory("33333")
        # sched_a: only 1 mandatory (spread=0), but elective is far away
        # sched_b: 2 mandatories 10 days apart (spread=10)
        sched_a = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 25)})
        sched_b = _schedule({"11111": date(2026, 1, 5), "33333": date(2026, 1, 15)})

        result = SortingEngine.sort(
            [sched_a, sched_b], [mand, elec, mand2], _config_single(self.CRITERION)
        )
        assert result[0] is sched_b


# ---------------------------------------------------------------------------
# 3.5  SORT_MAX_EXAMS_PER_DAY — descending by max exams on a single day
# ---------------------------------------------------------------------------

class TestSortMaxExamsPerDay:
    """Criterion 3.5: DESCENDING by max exams on a single day (SRS §3.5 'בסדר יורד')."""

    CRITERION = SortCriterion.SORT_MAX_EXAMS_PER_DAY

    def test_three_exams_same_day_ranks_before_two(self):
        c1, c2, c3 = _mandatory("11111"), _mandatory("22222"), _mandatory("33333")
        sched_a = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 5),
            "33333": date(2026, 1, 5),
        })  # max = 3 (more → ranks first)
        sched_b = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 5),
            "33333": date(2026, 1, 6),
        })  # max = 2

        result = SortingEngine.sort([sched_b, sched_a], [c1, c2, c3], _config_single(self.CRITERION))
        assert result[0] is sched_a


# ---------------------------------------------------------------------------
# Multi-level sort: primary + tie-breaker
# ---------------------------------------------------------------------------

class TestMultiLevelSort:
    """Primary sort key applied first; tie-breaker resolves equal primary scores."""

    def test_primary_sort_by_3_1_tiebreaker_by_3_5(self):
        """
        Both schedules have the same min-mandatory gap (primary sort, 3.1).
        The tie-breaker (3.5: max exams per day) determines final order.

        Setup: 2 mandatory courses (11111, 22222) with gap=10 in BOTH schedules.
        An elective (33333) is placed differently to create a difference in max-exams-per-day.
        sched_b reaches max exams/day = 2, so under the DESCENDING direction for 3.5
        (more ranks first, SRS §3.5) it ranks first.
        """
        c1, c2 = _mandatory("11111"), _mandatory("22222")
        c3 = _elective("33333")

        # Both schedules: mandatory gap = Jan5→Jan15 = 10 days  (identical primary score)
        # sched_a: elective alone on Jan10 → max exams/day = 1  (fewer → ranks last)
        sched_a = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 15),
            "33333": date(2026, 1, 10),
        })
        # sched_b: elective on same day as 11111 (Jan5) → max exams/day = 2  (more → ranks first)
        sched_b = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 15),
            "33333": date(2026, 1, 5),
        })

        config = SortingConfig(
            rules=(
                SortRule(priority=1, criterion=SortCriterion.SORT_MIN_DAYS_MANDATORY),
                SortRule(priority=2, criterion=SortCriterion.SORT_MAX_EXAMS_PER_DAY),
            )
        )
        result = SortingEngine.sort([sched_a, sched_b], [c1, c2, c3], config)
        assert result[0] is sched_b

    def test_primary_criterion_overrides_secondary(self):
        """
        sched_a wins primary (larger min mandatory gap);
        sched_b wins secondary — but primary always dominates.
        """
        c1, c2, c3 = _mandatory("11111"), _mandatory("22222"), _mandatory("33333")

        # sched_a: min mandatory gap = 10 (wins primary)
        sched_a = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 15),
            "33333": date(2026, 1, 20),
        })
        # sched_b: min mandatory gap = 3 (loses primary), but 2 exams on one day (wins secondary)
        sched_b = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 8),
            "33333": date(2026, 1, 5),
        })

        config = SortingConfig(
            rules=(
                SortRule(priority=1, criterion=SortCriterion.SORT_MIN_DAYS_MANDATORY),
                SortRule(priority=2, criterion=SortCriterion.SORT_MAX_EXAMS_PER_DAY),
            )
        )
        result = SortingEngine.sort([sched_b, sched_a], [c1, c2, c3], config)
        assert result[0] is sched_a

    def test_all_five_criteria_applied_in_priority_order(self):
        """Sanity check: all five criteria in a config does not crash."""
        c1, c2, c3 = _mandatory("11111"), _mandatory("22222"), _elective("33333")
        sched_a = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 15),
            "33333": date(2026, 1, 20),
        })
        sched_b = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 8),
            "33333": date(2026, 1, 5),
        })

        config = SortingConfig(
            rules=(
                SortRule(priority=1, criterion=SortCriterion.SORT_MIN_DAYS_MANDATORY),
                SortRule(priority=2, criterion=SortCriterion.SORT_AVG_DAYS_ANY),
                SortRule(priority=3, criterion=SortCriterion.SORT_ELECTIVE_COLLISIONS),
                SortRule(priority=4, criterion=SortCriterion.SORT_EXAM_PERIOD_SPREAD),
                SortRule(priority=5, criterion=SortCriterion.SORT_MAX_EXAMS_PER_DAY),
            )
        )
        result = SortingEngine.sort([sched_a, sched_b], [c1, c2, c3], config)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_schedule_list_returns_empty(self):
        config = _config_single(SortCriterion.SORT_MIN_DAYS_MANDATORY)
        result = SortingEngine.sort([], [], config)
        assert result == []

    def test_single_schedule_returned_unchanged(self):
        c1, c2 = _mandatory("11111"), _mandatory("22222")
        sched = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 10)})
        config = _config_single(SortCriterion.SORT_MIN_DAYS_MANDATORY)
        result = SortingEngine.sort([sched], [c1, c2], config)
        assert result == [sched]

    def test_empty_sorting_config_returns_original_order(self):
        c1, c2 = _mandatory("11111"), _mandatory("22222")
        sched_a = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 10)})
        sched_b = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 6)})
        result = SortingEngine.sort([sched_a, sched_b], [c1, c2], SortingConfig())
        assert result == [sched_a, sched_b]

    def test_sort_does_not_mutate_input_list(self):
        """sort() must return a new list; the original must be unchanged."""
        c1, c2 = _mandatory("11111"), _mandatory("22222")
        sched_a = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 12)})
        sched_b = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 7)})
        original = [sched_b, sched_a]
        config = _config_single(SortCriterion.SORT_MIN_DAYS_MANDATORY)
        result = SortingEngine.sort(original, [c1, c2], config)
        assert original == [sched_b, sched_a]  # unchanged
        assert result == [sched_a, sched_b]

    def test_sort_rules_are_applied_by_priority_not_input_order(self):
        """SortingConfig priority must win over the raw order of rules."""
        c1, c2, c3 = _mandatory("11111"), _mandatory("22222"), _mandatory("33333")

        # Better primary score for SORT_MIN_DAYS_MANDATORY, worse secondary day-load.
        sched_better_gap = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 15),
            "33333": date(2026, 1, 20),
        })

        # Worse primary score, better secondary score.
        sched_better_day_load = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 8),
            "33333": date(2026, 1, 5),
        })

        config = SortingConfig(
            rules=(
                # Intentionally out of order: priority 2 appears before priority 1.
                SortRule(priority=2, criterion=SortCriterion.SORT_MAX_EXAMS_PER_DAY),
                SortRule(priority=1, criterion=SortCriterion.SORT_MIN_DAYS_MANDATORY),
            )
        )

        result = SortingEngine.sort(
            [sched_better_day_load, sched_better_gap],
            [c1, c2, c3],
            config,
        )

        assert result[0] is sched_better_gap

# ---------------------------------------------------------------------------
# SortingConfig ordered-criteria API (drag-and-drop round trip)
# ---------------------------------------------------------------------------

class TestSortingConfigOrderedCriteria:
    """The UI-facing ordered-criteria view used by the drag-and-drop widget."""

    def test_from_ordered_criteria_assigns_sequential_priorities(self):
        ordered = [
            SortCriterion.SORT_MAX_EXAMS_PER_DAY,
            SortCriterion.SORT_MIN_DAYS_MANDATORY,
            SortCriterion.SORT_AVG_DAYS_ANY,
        ]
        config = SortingConfig.from_ordered_criteria(ordered)
        assert [r.priority for r in config.rules] == [1, 2, 3]
        assert config.criteria_in_order() == ordered

    def test_enabled_criteria_returns_priority_order(self):
        config = SortingConfig(
            rules=(
                SortRule(priority=2, criterion=SortCriterion.SORT_AVG_DAYS_ANY),
                SortRule(priority=1, criterion=SortCriterion.SORT_MIN_DAYS_MANDATORY),
            )
        )
        assert config.enabled_criteria == (
            SortCriterion.SORT_MIN_DAYS_MANDATORY,
            SortCriterion.SORT_AVG_DAYS_ANY,
        )

    def test_round_trip_preserves_order(self):
        ordered = [
            SortCriterion.SORT_ELECTIVE_COLLISIONS,
            SortCriterion.SORT_EXAM_PERIOD_SPREAD,
        ]
        config = SortingConfig.from_ordered_criteria(ordered)
        assert list(config.enabled_criteria) == ordered

    def test_from_ordered_criteria_drops_duplicates(self):
        config = SortingConfig.from_ordered_criteria(
            [
                SortCriterion.SORT_MIN_DAYS_MANDATORY,
                SortCriterion.SORT_MIN_DAYS_MANDATORY,
                SortCriterion.SORT_AVG_DAYS_ANY,
            ]
        )
        assert config.enabled_criteria == (
            SortCriterion.SORT_MIN_DAYS_MANDATORY,
            SortCriterion.SORT_AVG_DAYS_ANY,
        )
        assert [r.priority for r in config.rules] == [1, 2]

    def test_empty_iterable_yields_empty_config(self):
        config = SortingConfig.from_ordered_criteria([])
        assert config.rules == ()
        assert config.enabled_criteria == ()

    def test_reordering_changes_sort_outcome(self):
        """A config built from a reordered criteria list re-ranks accordingly."""
        c1, c2, c3 = _mandatory("11111"), _mandatory("22222"), _mandatory("33333")
        # Equal min-mandatory gap (10) for both; differ on max-exams-per-day.
        sched_gap = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 15),
            "33333": date(2026, 1, 25),
        })  # max exams/day = 1
        sched_dense = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 15),
            "33333": date(2026, 1, 5),
        })  # max exams/day = 2, min gap = 0

        # Priority: max-per-day first. 3.5 sorts DESCENDING (SRS §3.5), so the
        # schedule with MORE exams/day (sched_dense, max=2) wins over sched_gap (max=1).
        config = SortingConfig.from_ordered_criteria([
            SortCriterion.SORT_MAX_EXAMS_PER_DAY,
            SortCriterion.SORT_MIN_DAYS_MANDATORY,
        ])
        result = SortingEngine.sort([sched_gap, sched_dense], [c1, c2, c3], config)
        assert result[0] is sched_dense


# ---------------------------------------------------------------------------
# Regression: relevant offering isolation
# ---------------------------------------------------------------------------

class TestRelevantOfferingIsolation:
    """Sorting metrics should only use selected-program and current-semester offerings."""

    def test_unselected_programme_offering_does_not_affect_min_gap_sort(self):
        c1 = _mandatory("11111", program=PROGRAM_A)
        c1.add_offering(_offering(PROGRAM_B, 1, "Obligatory"))
        c2 = _mandatory("22222", program=PROGRAM_A)

        sched_far = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 15),
        })
        sched_close = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 7),
        })

        result = SortingEngine.sort(
            [sched_close, sched_far],
            [c1, c2],
            _config_single(SortCriterion.SORT_MIN_DAYS_MANDATORY),
            selected_programs=[PROGRAM_A],
        )

        assert result[0] is sched_far

    def test_other_semester_offering_does_not_affect_min_gap_sort(self):
        c1 = _mandatory("11111", program=PROGRAM_A)
        c1.add_offering(
            CourseOffering(PROGRAM_A, 1, "SPRI", "Obligatory")
        )
        c2 = _mandatory("22222", program=PROGRAM_A)

        sched_far = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 15),
        })
        sched_close = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 7),
        })

        result = SortingEngine.sort(
            [sched_close, sched_far],
            [c1, c2],
            _config_single(SortCriterion.SORT_MIN_DAYS_MANDATORY),
            selected_programs=[PROGRAM_A],
        )

        assert result[0] is sched_far
