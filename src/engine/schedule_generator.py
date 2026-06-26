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

        Classic backtracking — choose, explore, un-choose — with two pruning strategies:

        1. Dynamic MCV: at each step pick the unassigned course whose current remaining
           domain (valid dates not blocked by already-assigned conflicting neighbours) is
           smallest.  Ties are broken by course id for determinism (C2).  Choosing the
           tightest course first surfaces failures early without any look-ahead cost.

        2. Forward-checking (SCRUM-453): after each assignment verify that every still-
           unassigned course retains at least one valid date.  If any future domain is
           empty the branch cannot produce a valid schedule — prune it immediately.

        `assignment` and `unassigned` are mutated in-place and fully restored after each
        branch — O(n) memory regardless of how many schedules exist.
        """
        if not unassigned:
            yield Schedule(period=exam_period, assignments={c.id: d for c, d in assignment.items()})
            return

        # Dynamic MCV + deterministic tiebreaker (C2):
        # blocked_count = number of distinct dates taken by assigned neighbours.
        # max(blocked_count) ≡ min(remaining domain); secondary key c.id breaks ties.
        course = max(
            unassigned,
            key=lambda c: (
                len({assignment[n] for n in conflict_graph[c] if n in assignment}),
                c.id,
            ),
        )
        unassigned.remove(course)   # `unassigned` now contains exactly the future courses

        blocked = {assignment[n] for n in conflict_graph[course] if n in assignment}
        for d in valid_dates:
            if d not in blocked:
                assignment[course] = d
                # Forward-check: prune if any still-unassigned course's domain is now empty
                if self._forward_check(assignment, unassigned, valid_dates, conflict_graph):
                    yield from self._backtrack(
                        assignment, unassigned, valid_dates, conflict_graph, exam_period
                    )
                del assignment[course]

        unassigned.add(course)   # restore for caller's backtrack

    def _forward_check(
        self,
        assignment: dict[Course, date],
        unassigned: set[Course],
        valid_dates: list[date],
        conflict_graph: dict[Course, set[Course]],
    ) -> bool:
        """Return False if any still-unassigned course has no valid date left.

        Iterates `unassigned` (which already excludes the just-chosen course) so it
        examines exactly the future courses — semantically equivalent to the old
        remaining[next_index:] slice but without allocating a new list.

        Cost: O(n × k) per call (n = remaining courses, k = average degree).
        This overhead is negligible compared to the exponential subtrees it avoids
        on dense conflict graphs with tight date windows.
        """
        for future in unassigned:
            blocked_future = {assignment[nb] for nb in conflict_graph[future] if nb in assignment}
            if all(d in blocked_future for d in valid_dates):
                return False
        return True
