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

        Uses a conflict graph + dynamic MCV heuristic inside the backtracker.
        Yields lazily — never builds a list in memory.
        """
        valid_dates = exam_period.get_valid_dates()
        if not valid_dates or not courses:
            return

        # Build the conflict graph once — reused across every backtrack step
        conflict_graph = self._build_conflict_graph(courses)

        yield from self._backtrack({}, set(courses), valid_dates, conflict_graph, exam_period)

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
        unassigned: set[Course],
        valid_dates: list[date],
        conflict_graph: dict[Course, set[Course]],
        exam_period: ExamPeriod,
    ) -> Iterator[Schedule]:
        """Recursively assign dates to courses, yielding a Schedule when all are placed.

        Classic backtracking — choose, explore, un-choose — with a dynamic
        Most-Constrained-Variable heuristic: at each step we pick the unassigned
        course whose current remaining domain (valid dates not blocked by already-
        assigned conflicting neighbours) is smallest.  Choosing the tightest course
        first surfaces failures early and prunes large dead subtrees without any
        look-ahead cost beyond what the current assignment already tells us.

        `assignment` and `unassigned` are mutated in-place and fully restored after
        each branch — O(n) memory regardless of how many schedules exist.
        """
        if not unassigned:
            yield Schedule(period=exam_period, assignments={c.id: d for c, d in assignment.items()})
            return

        # Dynamic MCV: pick the course with the fewest remaining valid dates.
        # blocked_count = number of distinct dates already taken by assigned neighbours.
        # Maximising blocked_count is equivalent to minimising remaining domain size
        # (remaining = len(valid_dates) − blocked_count) while being cheaper to compute:
        # O(degree) per course instead of O(valid_dates × degree).
        course = max(
            unassigned,
            key=lambda c: (
                len({assignment[n] for n in conflict_graph[c] if n in assignment}),
                c.id,
            ),
        )
        unassigned.remove(course)

        blocked = {assignment[n] for n in conflict_graph[course] if n in assignment}
        for d in valid_dates:
            if d not in blocked:
                assignment[course] = d
                yield from self._backtrack(assignment, unassigned, valid_dates, conflict_graph, exam_period)
                del assignment[course]

        unassigned.add(course)
