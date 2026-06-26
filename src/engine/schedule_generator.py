from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from itertools import combinations

from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.domain.schedule_metrics import relevant_offerings
from src.domain.threshold import Criterion, ThresholdSettings
from src.interfaces.i_conflict_strategy import IConflictStrategy
from src.interfaces.i_schedule_generator import IScheduleGenerator

logger = logging.getLogger(__name__)


@dataclass
class GenerationMetrics:
    """Lightweight counters for one lazy generation iterator."""

    period_key: str = ""
    nodes_visited: int = 0
    schedules_produced: int = 0
    domain_prunes: int = 0
    conflict_prunes: int = 0
    threshold_prunes: int = 0
    prefiltered_candidates_removed: int = 0
    elapsed_seconds: float = 0.0


@dataclass(frozen=True)
class _ThresholdContext:
    max_exams_per_day: int | None
    max_elective_collisions: int | None
    min_days_mandatory: int | None
    min_days_any: int | None
    mandatory_groups_by_course: dict[Course, tuple[tuple[str, int], ...]]
    all_groups_by_course: dict[Course, tuple[tuple[str, int], ...]]
    elective_programs_by_course: dict[Course, tuple[str, ...]]


class ScheduleGenerator(IScheduleGenerator):
    """Generates all conflict-free exam schedules via lazy backtracking."""

    def __init__(
        self,
        conflict_strategy: IConflictStrategy,
        threshold_settings: ThresholdSettings | None = None,
        selected_programs: list[str] | None = None,
    ) -> None:
        self._strategy = conflict_strategy
        self._threshold_settings = threshold_settings or ThresholdSettings()
        self._selected_programs = list(selected_programs or [])
        self._last_metrics = GenerationMetrics()

    @property
    def last_metrics(self) -> GenerationMetrics:
        """Return metrics for the most recently created generation iterator."""
        return self._last_metrics

    def generate_schedules(
        self,
        courses: list[Course],
        exam_period: ExamPeriod,
    ) -> Iterator[Schedule]:
        """Yield every valid conflict-free schedule for the given exam period.

        The iterator remains lazy. The current domain model has no course-level
        date blackout rules, so every course starts from the same period-valid
        date domain. Dynamic MRV, forward checking, and monotonic threshold
        checks then narrow those domains during recursion. Final ThresholdFilter
        validation still runs in AppController as the defensive source of truth.
        """
        metrics = GenerationMetrics(period_key=exam_period.get_key())
        self._last_metrics = metrics
        started = time.monotonic()

        valid_dates = tuple(exam_period.get_valid_dates())
        raw_candidate_count = self._raw_period_day_count(exam_period) * len(courses)
        metrics.prefiltered_candidates_removed = max(
            0,
            raw_candidate_count - (len(valid_dates) * len(courses)),
        )

        if not valid_dates or not courses:
            metrics.elapsed_seconds = time.monotonic() - started
            self._log_metrics(metrics)
            return iter(())

        conflict_graph = self._build_conflict_graph(courses)
        domains: dict[Course, tuple[date, ...]] = {
            course: valid_dates
            for course in courses
        }

        if any(not domain for domain in domains.values()):
            metrics.domain_prunes += 1
            metrics.elapsed_seconds = time.monotonic() - started
            self._log_metrics(metrics)
            return iter(())

        original_order = {course: index for index, course in enumerate(courses)}
        threshold_context = self._build_threshold_context(courses, exam_period)

        def _iterator() -> Iterator[Schedule]:
            try:
                yield from self._backtrack(
                    assignment={},
                    unassigned=set(courses),
                    domains=domains,
                    conflict_graph=conflict_graph,
                    original_order=original_order,
                    exam_period=exam_period,
                    metrics=metrics,
                    threshold_context=threshold_context,
                )
            finally:
                metrics.elapsed_seconds = time.monotonic() - started
                self._log_metrics(metrics)

        return _iterator()

    def _raw_period_day_count(self, exam_period: ExamPeriod) -> int:
        total = 0
        for start_date, end_date in exam_period.date_ranges:
            if end_date < start_date:
                continue
            total += (end_date - start_date).days + 1
        return total

    def _build_conflict_graph(self, courses: list[Course]) -> dict[Course, set[Course]]:
        """Return a symmetric adjacency map for direct conflict lookups."""
        graph: dict[Course, set[Course]] = {course: set() for course in courses}
        for index, course in enumerate(courses):
            for other in courses[index + 1:]:
                if self._strategy.is_conflict(course, other):
                    graph[course].add(other)
                    graph[other].add(course)
        return graph

    def _backtrack(
        self,
        assignment: dict[Course, date],
        unassigned: set[Course],
        domains: dict[Course, tuple[date, ...]],
        conflict_graph: dict[Course, set[Course]],
        original_order: dict[Course, int],
        exam_period: ExamPeriod,
        metrics: GenerationMetrics,
        threshold_context: _ThresholdContext,
    ) -> Iterator[Schedule]:
        metrics.nodes_visited += 1

        if not unassigned:
            metrics.schedules_produced += 1
            yield Schedule(
                period=exam_period,
                assignments={course.id: day for course, day in assignment.items()},
            )
            return

        course, candidate_dates = self._select_next_course(
            unassigned,
            domains,
            conflict_graph,
            original_order,
        )

        if not candidate_dates:
            metrics.domain_prunes += 1
            return

        next_unassigned = set(unassigned)
        next_unassigned.remove(course)

        for exam_date in candidate_dates:
            assignment[course] = exam_date

            if not self._partial_thresholds_are_safe(assignment, threshold_context):
                metrics.threshold_prunes += 1
                del assignment[course]
                continue

            next_domains = domains
            if next_unassigned:
                next_domains = dict(domains)
                if not self._forward_check_domains(
                    course,
                    exam_date,
                    next_unassigned,
                    next_domains,
                    conflict_graph,
                    metrics,
                ):
                    del assignment[course]
                    continue

            yield from self._backtrack(
                assignment,
                next_unassigned,
                next_domains,
                conflict_graph,
                original_order,
                exam_period,
                metrics,
                threshold_context,
            )

            del assignment[course]

    def _select_next_course(
        self,
        unassigned: set[Course],
        domains: dict[Course, tuple[date, ...]],
        conflict_graph: dict[Course, set[Course]],
        original_order: dict[Course, int],
    ) -> tuple[Course, tuple[date, ...]]:
        def key(course: Course) -> tuple[int, int, int, int]:
            unassigned_degree = len(conflict_graph[course] & unassigned)
            return (
                len(domains[course]),
                -unassigned_degree,
                -len(conflict_graph[course]),
                original_order[course],
            )

        selected = min(unassigned, key=key)
        return selected, domains[selected]

    def _forward_check_domains(
        self,
        assigned_course: Course,
        assigned_date: date,
        unassigned: set[Course],
        domains: dict[Course, tuple[date, ...]],
        conflict_graph: dict[Course, set[Course]],
        metrics: GenerationMetrics,
    ) -> bool:
        for neighbour in conflict_graph[assigned_course] & unassigned:
            domain = domains[neighbour]
            if assigned_date not in domain:
                continue

            reduced = tuple(day for day in domain if day != assigned_date)
            if not reduced:
                metrics.domain_prunes += 1
                return False

            domains[neighbour] = reduced
            metrics.conflict_prunes += 1

        return True

    def _build_threshold_context(
        self,
        courses: list[Course],
        exam_period: ExamPeriod,
    ) -> _ThresholdContext:
        entries = {
            entry.criterion: entry.k
            for entry in self._threshold_settings.entries
            if entry.enabled
        }
        prog_set = set(self._selected_programs)

        mandatory_groups_by_course: dict[Course, tuple[tuple[str, int], ...]] = {}
        all_groups_by_course: dict[Course, tuple[tuple[str, int], ...]] = {}
        elective_programs_by_course: dict[Course, tuple[str, ...]] = {}

        for course in courses:
            mandatory_groups: set[tuple[str, int]] = set()
            all_groups: set[tuple[str, int]] = set()
            elective_programs: set[str] = set()

            for offering in relevant_offerings(course, prog_set, exam_period.semester):
                group = (offering.program_id, offering.year)
                all_groups.add(group)
                if offering.requirement.strip().lower() == "obligatory":
                    mandatory_groups.add(group)
                elif offering.requirement.strip().lower() == "elective":
                    elective_programs.add(offering.program_id)

            mandatory_groups_by_course[course] = tuple(sorted(mandatory_groups))
            all_groups_by_course[course] = tuple(sorted(all_groups))
            elective_programs_by_course[course] = tuple(sorted(elective_programs))

        return _ThresholdContext(
            max_exams_per_day=entries.get(Criterion.MAX_EXAMS_PER_DAY),
            max_elective_collisions=entries.get(Criterion.MAX_ELECTIVE_COLLISIONS),
            min_days_mandatory=entries.get(
                Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS
            ),
            min_days_any=entries.get(Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS),
            mandatory_groups_by_course=mandatory_groups_by_course,
            all_groups_by_course=all_groups_by_course,
            elective_programs_by_course=elective_programs_by_course,
        )

    def _partial_thresholds_are_safe(
        self,
        assignment: dict[Course, date],
        context: _ThresholdContext,
    ) -> bool:
        if context.max_exams_per_day is not None:
            day_counts = Counter(assignment.values())
            if day_counts and max(day_counts.values()) > context.max_exams_per_day:
                return False

        if (
            context.min_days_mandatory is not None
            and not self._group_gaps_are_safe(
                assignment,
                context.mandatory_groups_by_course,
                context.min_days_mandatory,
            )
        ):
            return False

        if (
            context.min_days_any is not None
            and not self._group_gaps_are_safe(
                assignment,
                context.all_groups_by_course,
                context.min_days_any,
            )
        ):
            return False

        if (
            context.max_elective_collisions is not None
            and not self._elective_collisions_are_safe(
                assignment,
                context.elective_programs_by_course,
                context.max_elective_collisions,
            )
        ):
            return False

        return True

    def _group_gaps_are_safe(
        self,
        assignment: dict[Course, date],
        groups_by_course: dict[Course, tuple[tuple[str, int], ...]],
        min_days: int,
    ) -> bool:
        dates_by_group: dict[tuple[str, int], list[date]] = {}
        for course, exam_date in assignment.items():
            for group in groups_by_course[course]:
                dates_by_group.setdefault(group, []).append(exam_date)

        for dates in dates_by_group.values():
            if len(dates) < 2:
                continue
            for first, second in combinations(dates, 2):
                if abs((second - first).days) < min_days:
                    return False

        return True

    def _elective_collisions_are_safe(
        self,
        assignment: dict[Course, date],
        elective_programs_by_course: dict[Course, tuple[str, ...]],
        max_collisions: int,
    ) -> bool:
        dates_by_program: dict[str, list[date]] = {}
        for course, exam_date in assignment.items():
            for program_id in elective_programs_by_course[course]:
                dates_by_program.setdefault(program_id, []).append(exam_date)

        for dates in dates_by_program.values():
            collisions = sum(
                1 for first, second in combinations(dates, 2)
                if first == second
            )
            if collisions > max_collisions:
                return False

        return True

    def _log_metrics(self, metrics: GenerationMetrics) -> None:
        logger.info(
            "Generation metrics: period=%s nodes=%s schedules=%s "
            "domain_prunes=%s conflict_prunes=%s threshold_prunes=%s "
            "prefilter_removed=%s elapsed=%.3fs",
            metrics.period_key,
            metrics.nodes_visited,
            metrics.schedules_produced,
            metrics.domain_prunes,
            metrics.conflict_prunes,
            metrics.threshold_prunes,
            metrics.prefiltered_candidates_removed,
            metrics.elapsed_seconds,
        )
