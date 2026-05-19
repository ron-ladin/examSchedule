"""
Infrastructure Adapter: ExactConflictStrategy
----------------------------------------------
Implements IConflictStrategy using the Version 1.0 conflict rule.

Method:
    is_conflict(course1: Course, course2: Course) -> bool

        Returns True if both courses cannot share the same exam date.

        Conflict rule:
            Two courses conflict if:
                1. They share at least one selected program_id,
                2. They are in the same study year,
                3. They are in the same semester,
                4. NOT both courses are "Elective" in that shared offering.

            In code terms:
                for each offering1 in course1 (in selected programs):
                    for each offering2 in course2 (in selected programs):
                        if same program, same year, same semester:
                            if NOT both elective → return True
                return False

Notes:
    - Implements IConflictStrategy from interfaces/.
    - Only offerings belonging to selected programs are checked — prevents
      false conflicts from programs not selected for this run.
    - Keep this class thin — conflict logic only, no file I/O.
"""

from typing import List

from src.domain.course import Course
from src.interfaces.i_conflict_strategy import IConflictStrategy


class ExactConflictStrategy(IConflictStrategy):

    def __init__(self, selected_programs: List[str]) -> None:
        self._selected_programs = set(selected_programs)

    def is_conflict(self, course1: Course, course2: Course) -> bool:
        for o1 in course1.offerings:
            if o1.program_id not in self._selected_programs:
                continue
            for o2 in course2.offerings:
                if o2.program_id not in self._selected_programs:
                    continue
                if o1.same_program_year_semester(o2):
                    if not (o1.is_elective() and o2.is_elective()):
                        return True
        return False
