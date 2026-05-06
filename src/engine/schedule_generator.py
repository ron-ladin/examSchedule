"""
Core Engine: ScheduleGenerator

--------------------------------
Generates ALL valid, conflict-free exam schedules using backtracking.

Constructor args:
    - conflict_strategy (IConflictStrategy) : injected strategy for conflict checking

Main method to implement:
    - generate_schedules(courses: List[Course], exam_period: ExamPeriod) -> Iterator[Schedule]
        Uses backtracking to assign one valid date per course.
        MUST use `yield` -- never build a full list in memory.
        Performance requirement: must complete in < 30 seconds on medium datasets.

Internal helpers to implement:
    - _build_conflict_graph(courses: List[Course]) -> Dict[Course, Set[Course]]
        Builds the conflict graph ONCE before backtracking starts.
        Key: course -> set of courses it potentially conflicts with (date-independent).
        Used during backtracking to prune the search space early.

    - _backtrack(assignment, remaining, valid_dates, ...) -> Iterator[Schedule]
        Recursive core. For each unassigned course, tries every valid date
        from the exam period. Yields a Schedule when all courses are assigned
        without conflict.

Notes:
    - Build the conflict graph ONCE -- do NOT recompute per recursive call.
    - Use IConflictStrategy.is_conflict() -- never hardcode conflict logic here.
    - Valid dates come from ExamPeriod.get_valid_dates().
"""

from datetime import date
from typing import Dict, Iterator, List, Set

from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.interfaces.i_conflict_strategy import IConflictStrategy


class ScheduleGenerator:
    """Generates all conflict-free exam schedules via backtracking."""

    def __init__(self, conflict_strategy: IConflictStrategy) -> None:
        # Save the rule-checker (strategy) so we can use it later to find conflicts.
        self._conflict_strategy = conflict_strategy

    def generate_schedules(
        self, courses: List[Course], exam_period: ExamPeriod
    ) -> Iterator[Schedule]:
        # Step 1: Get all the days we are allowed to have exams on (no holidays/weekends).
        valid_dates = exam_period.get_valid_dates()
        
        # Step 2: Safety check. If there are no valid days or no courses, stop right here.
        if not valid_dates or not courses:
            return

        # Step 3: Build a map of "enemies" (courses that cannot be on the same day).
        # We do this only ONCE before the hard work begins, to save time.
        conflict_graph = self._build_conflict_graph(courses)
        
        # Step 4: Start the backtracking process. 
        # 'yield from' means we will pass the found schedules directly to the outside world,
        # one by one, without saving them all in a massive list in our computer's memory.
        yield from self._backtrack({}, list(courses), valid_dates, conflict_graph)

    def _build_conflict_graph(
        self, courses: List[Course]
    ) -> Dict[Course, Set[Course]]:
        # Create an empty dictionary. Every course gets an empty set of "enemies".
        graph: Dict[Course, Set[Course]] = {c: set() for c in courses}

        # Check every possible pair of courses to see if they conflict.
        for i, course_a in enumerate(courses):
            for course_b in courses[i + 1:]:
                # We use date.min (a fake date) because in Version 1.0, 
                # conflicts depend only on the program and year, not the actual date.
                if self._conflict_strategy.is_conflict(course_a, course_b, date.min):
                    # If they conflict, add them to each other's enemy list.
                    graph[course_a].add(course_b)
                    graph[course_b].add(course_a)

        return graph

    def _backtrack(
        self,
        assignment: Dict[Course, date],
        remaining: List[Course],
        valid_dates: List[date],
        conflict_graph: Dict[Course, Set[Course]],
    ) -> Iterator[Schedule]:
        
        # BASE CASE: Are we out of courses? 
        # If 'remaining' is empty, it means we successfully scheduled everything!
        if not remaining:
            # We must make a copy of our dictionary using dict(assignment).
            # If we don't copy it, the backtracking will accidentally delete our correct answers later.
            yield Schedule(assignments=dict(assignment))
            return

        # Get the very first course from the remaining list.
        current_course = remaining[0]
        # Keep the rest of the list for the next recursive calls.
        rest = remaining[1:]

        # Try to put 'current_course' on every possible allowed date.
        for candidate_date in valid_dates:
            
            # PRUNING (Optimization): Check if this date is safe.
            # Look at all the courses we already scheduled. 
            # If any of them is an "enemy" of 'current_course' AND is scheduled on this exact date,
            # then we have a conflict.
            conflict_found = any(
                assigned_date == candidate_date
                for neighbor, assigned_date in assignment.items()
                if neighbor in conflict_graph[current_course]
            )

            # If the date is safe (no enemies on this day):
            if not conflict_found:
                # 1. CHOOSE: Assign the course to this date.
                assignment[current_course] = candidate_date
                
                # 2. EXPLORE: Call this same function again to schedule the 'rest' of the courses.
                yield from self._backtrack(assignment, rest, valid_dates, conflict_graph)
                
                # 3. UN-CHOOSE (Backtrack): We finished exploring this path. 
                # Remove the course from this date so the loop can try the next date.
                del assignment[current_course]