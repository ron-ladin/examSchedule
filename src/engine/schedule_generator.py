from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.domain.placement_constraint import PlacementConstraintSet
from src.domain.schedule import Schedule
from src.domain.threshold import ThresholdSettings
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
        constraints = PlacementConstraintSet.build(
            self._threshold_settings,
            courses,
            self._selected_programs,
            exam_period,
        )

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
                    constraints=constraints,
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
        constraints: PlacementConstraintSet,
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
            if constraints and not constraints.allows(course, exam_date):
                metrics.threshold_prunes += 1
                continue

            assignment[course] = exam_date
            if constraints:
                constraints.record(course, exam_date)

            try:
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
                        continue
                    if constraints and not self._forward_check_constraints(
                        next_unassigned,
                        next_domains,
                        constraints,
                        metrics,
                    ):
                        continue

                yield from self._backtrack(
                    assignment,
                    next_unassigned,
                    next_domains,
                    conflict_graph,
                    original_order,
                    exam_period,
                    metrics,
                    constraints,
                )
            finally:
                if constraints:
                    constraints.undo(course, exam_date)
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

    def _forward_check_constraints(
        self,
        unassigned: set[Course],
        domains: dict[Course, tuple[date, ...]],
        constraints: PlacementConstraintSet,
        metrics: GenerationMetrics,
    ) -> bool:
        for future_course in unassigned:
            domain = domains[future_course]
            reduced = tuple(
                day for day in domain
                if constraints.allows(future_course, day)
            )
            removed = len(domain) - len(reduced)
            if removed:
                metrics.threshold_prunes += removed

            if not reduced:
                metrics.domain_prunes += 1
                return False

            if removed:
                domains[future_course] = reduced

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
