"""
Domain Service: SortingEngine
-------------------------------
Sorts a list of valid Schedules by a SortingConfig (spec sections 3.1–3.5).
All criteria sort in DESCENDING order (higher score = ranked first).

Public API:
    SortingEngine.sort(schedules, courses, config, selected_programs=None) -> list[Schedule]

Returns a new list; the input is not mutated.
"""

from collections import Counter
from datetime import date
from functools import lru_cache
from itertools import combinations
from src.domain.course import Course
from src.domain.schedule import Schedule
from src.domain.schedule_metrics import (
    all_dates_by_group,
    elective_dates_by_program,
    mandatory_dates_by_group,
)
from src.domain.sorting import SortCriterion, SortingConfig


class SortingEngine:

    @staticmethod
    def score(
        schedule: Schedule,
        courses: list[Course],
        criterion: SortCriterion,
        selected_programs: list[str] | None = None,
    ) -> float:
        """Return the numeric score for one schedule and one sort criterion."""
        prog_set: set = set(selected_programs) if selected_programs else set()
        return float(_SCORERS[criterion](schedule, courses, prog_set))

    @staticmethod
    def scores(
        schedule: Schedule,
        courses: list[Course],
        selected_programs: list[str] | None = None,
    ) -> dict[SortCriterion, float]:
        """Return all sort scores for one schedule.

        SQLiteScheduleStore uses these values as persisted ORDER BY columns so
        Result Ranking can re-order cached schedules without materialising the
        whole result set back into RAM.
        """
        return {
            criterion: SortingEngine.score(
                schedule, courses, criterion, selected_programs
            )
            for criterion in SortCriterion
        }

    @staticmethod
    def sort(
        schedules: list[Schedule],
        courses: list[Course],
        config: SortingConfig,
        selected_programs: list[str] | None = None,
    ) -> list[Schedule]:
        criteria = config.criteria_in_order()
        if not criteria:
            return list(schedules)

        prog_set: set = set(selected_programs) if selected_programs else set()

        def sort_key(schedule: Schedule) -> tuple:
            # Negate each score so sorted() produces descending order.
            return tuple(-_SCORERS[c](schedule, courses, prog_set) for c in criteria)

        return sorted(schedules, key=sort_key)


# ---------------------------------------------------------------------------
# Internal helpers (sorting-specific — not shared with ThresholdFilter)
# ---------------------------------------------------------------------------

# Aggressive memoization layer
# -----------------------------
# These three helpers are the hot path: with all 5 criteria enabled and tens of
# thousands of candidate schedules re-scored across many priority permutations,
# the same lists of exam dates are reduced to the same gap/collision numbers
# millions of times. lru_cache turns each repeat into a dict lookup.
#
# lists are unhashable, so each public wrapper normalises its input to a SORTED
# tuple before delegating to the cached core. Sorting is safe — all three
# metrics are order-independent (they range over unordered pairs) — and it
# collapses differently-ordered date lists onto the same cache entry, maximising
# the hit rate.
#
# maxsize is BOUNDED (not None): this is a long-running desktop app, so an
# unbounded cache would grow without limit as users load new files and re-run
# generation, eventually risking an OOM crash. 8192 entries per helper keeps the
# RAM footprint to a few MB at most while comfortably covering the working set of
# distinct date tuples seen when ranking 10,000+ schedules.
_CACHE_MAXSIZE = 8192


@lru_cache(maxsize=_CACHE_MAXSIZE)
def _min_gap_cached(dates: tuple[date, ...]) -> int:
    if len(dates) < 2:
        return 0
    return min(abs((b - a).days) for a, b in combinations(dates, 2))


@lru_cache(maxsize=_CACHE_MAXSIZE)
def _avg_gap_cached(dates: tuple[date, ...]) -> float:
    if len(dates) < 2:
        return 0.0
    pairs = list(combinations(dates, 2))
    return sum(abs((b - a).days) for a, b in pairs) / len(pairs)


@lru_cache(maxsize=_CACHE_MAXSIZE)
def _count_same_day_pairs_cached(dates: tuple[date, ...]) -> int:
    return sum(1 for a, b in combinations(dates, 2) if a == b)


def _min_gap(dates: list[date]) -> int:
    return _min_gap_cached(tuple(sorted(dates)))


def _avg_gap(dates: list[date]) -> float:
    return _avg_gap_cached(tuple(sorted(dates)))


def _count_same_day_pairs(dates: list[date]) -> int:
    return _count_same_day_pairs_cached(tuple(sorted(dates)))


# ---------------------------------------------------------------------------
# Criterion scorers — (schedule, courses, prog_set) -> float (higher = ranked first)
# ---------------------------------------------------------------------------

def _score_3_1(schedule: Schedule, courses: list[Course], prog_set: set) -> float:
    """3.1 — min days between mandatory exams (same program, year)."""
    groups = mandatory_dates_by_group(schedule, courses, prog_set)
    if not groups:
        return 0.0
    return float(min(_min_gap(dates) for dates in groups.values()))


def _score_3_2(schedule: Schedule, courses: list[Course], prog_set: set) -> float:
    """3.2 — average days between any two exams (same program, year)."""
    groups = all_dates_by_group(schedule, courses, prog_set)
    avgs = [_avg_gap(dates) for dates in groups.values() if len(dates) >= 2]
    return sum(avgs) / len(avgs) if avgs else 0.0


def _score_3_3(schedule: Schedule, courses: list[Course], prog_set: set) -> float:
    """3.3 — total elective-elective same-day collision pairs (same program)."""
    groups = elective_dates_by_program(schedule, courses, prog_set)
    return float(sum(_count_same_day_pairs(dates) for dates in groups.values()))


def _score_3_4(schedule: Schedule, courses: list[Course], prog_set: set) -> float:
    """3.4 — spread (last - first mandatory date, same program/year)."""
    groups = mandatory_dates_by_group(schedule, courses, prog_set)
    if not groups:
        return 0.0
    return float(min((max(d) - min(d)).days for d in groups.values()))


def _score_3_5(schedule: Schedule, courses: list[Course], prog_set: set) -> float:
    """3.5 — max exams on the same day (global)."""
    if not schedule.assignments:
        return 0.0
    return float(max(Counter(schedule.assignments.values()).values()))


_SCORERS = {
    SortCriterion.SORT_MIN_DAYS_MANDATORY: _score_3_1,
    SortCriterion.SORT_AVG_DAYS_ANY: _score_3_2,
    SortCriterion.SORT_ELECTIVE_COLLISIONS: _score_3_3,
    SortCriterion.SORT_EXAM_PERIOD_SPREAD: _score_3_4,
    SortCriterion.SORT_MAX_EXAMS_PER_DAY: _score_3_5,
}
