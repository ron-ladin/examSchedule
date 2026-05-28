from datetime import date
from collections.abc import Iterator

from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.interfaces.i_conflict_strategy import IConflictStrategy
from src.interfaces.i_schedule_generator import IScheduleGenerator


class ScheduleGenerator(IScheduleGenerator):
    """Generates all conflict-free exam schedules via backtracking."""

    def __init__(self, conflict_strategy: IConflictStrategy) -> None:
        # Inject the conflict rule — engine never touches ExactConflictStrategy directly
        self._strategy = conflict_strategy

    def generate_schedules(
        self,
        courses: list[Course],
        exam_period: ExamPeriod,
    ) -> Iterator[Schedule]:
        """Yield every valid conflict-free schedule for the given exam period.

        Uses a conflict graph + MCV heuristic to prune the search space before
        starting backtracking. Yields lazily — never builds a list in memory.
        """
        # Resolve the allowed dates from the period (excludes weekends & holidays)
        valid_dates = exam_period.get_valid_dates()
        if not valid_dates or not courses:
            return

        # Build the conflict graph once — reused across every backtrack step
        conflict_graph = self._build_conflict_graph(courses)

        # Most-Constrained-Variable (MCV) heuristic:
        # courses with more conflicts are harder to place, so assign them first.
        # This causes failures to surface early, pruning large branches of the search tree.
        ordered = sorted(courses, key=lambda c: len(conflict_graph[c]), reverse=True)

        # Hand off to the recursive backtracker with an empty initial assignment
        yield from self._backtrack({}, ordered, valid_dates, conflict_graph, exam_period)

    def _build_conflict_graph(self, courses: list[Course]) -> dict[Course, set[Course]]:
        """Return an adjacency map: course → set of courses it conflicts with.

        Iterates every pair exactly once (i, j where j > i) to avoid double-work.
        The result is symmetric: if A conflicts with B then B also conflicts with A.

        This O(n²) pass is done once so the backtracker can do O(1) neighbor lookups
        instead of re-running the strategy on every step.
        """
        graph: dict[Course, set[Course]] = {c: set() for c in courses}
        for i, a in enumerate(courses):
            for b in courses[i + 1:]:
                if self._strategy.is_conflict(a, b):
                    graph[a].add(b)
                    graph[b].add(a)
        return graph

    def _backtrack(
        self,
        assignment: dict[Course, date],
        remaining: list[Course],
        valid_dates: list[date],
        conflict_graph: dict[Course, set[Course]],
        exam_period: ExamPeriod,
    ) -> Iterator[Schedule]:
        """Recursively assign dates to courses, yielding a Schedule when all are placed.

        Classic backtracking pattern — choose, explore, un-choose:
          1. Pick the next unassigned course (head of `remaining`).
          2. Try every valid date that isn't blocked by an already-assigned neighbor.
          3. Recurse with the new assignment; yield any complete schedules found.
          4. Undo the assignment before trying the next date (backtrack).

        `assignment` is mutated in-place and restored after each branch, so it never
        holds more than one partial solution at a time — O(n) memory regardless of
        how many schedules exist.
        """
        # Base case: every course has been assigned — emit one complete schedule
        if not remaining:
            # Copy assignment so the yielded Schedule is independent of future mutations
            yield Schedule(period=exam_period, assignments={c.id: d for c, d in assignment.items()})
            return

        course = remaining[0]

        # Collect dates already taken by conflicting neighbors (already assigned).
        # Building this set once per call keeps the inner loop O(1) per date.
        blocked = {assignment[n] for n in conflict_graph[course] if n in assignment}

        for d in valid_dates:
            if d not in blocked:
                # Choose: tentatively place this course on date d
                assignment[course] = d

                # Explore: recurse on the remaining courses
                yield from self._backtrack(
                    assignment, remaining[1:], valid_dates, conflict_graph, exam_period
                )

                # Un-choose: remove the assignment so the next iteration starts clean
                del assignment[course]
