"""
Core Engine: ScheduleGenerator
--------------------------------
Generates ALL valid, conflict-free exam schedules using backtracking.

Constructor args:
    - conflict_strategy (IConflictStrategy) : injected strategy for conflict checking

Main method to implement:
    - generate_schedules(courses: List[Course], exam_period: ExamPeriod) -> Iterator[Schedule]
        Uses backtracking to assign one valid date per course.
        MUST use `yield` — never build a full list in memory.
        Performance requirement: must complete in < 30 seconds on medium datasets.

Internal helpers to implement:
    - _build_conflict_graph(courses: List[Course]) -> Dict[Course, Set[Course]]
        Builds a graph once before backtracking starts.
        Key: course → set of courses it conflicts with (regardless of date).
        Used during backtracking to prune the search space early.

    - _backtrack(assignment: Dict[Course, date], remaining: List[Course], ...) -> Iterator[Schedule]
        Recursive backtracking core. For each unassigned course, tries every
        valid date from the exam period. Yields a Schedule when all courses
        are assigned without conflict.

Notes:
    - Build the conflict graph ONCE before starting — do NOT recompute per recursive call.
    - Use IConflictStrategy.is_conflict() — never hardcode conflict logic here.
    - Valid dates come from ExamPeriod.get_valid_dates().
"""


class ScheduleGenerator:
    pass
