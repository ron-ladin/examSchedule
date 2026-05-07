"""
Infrastructure Adapter: ExactConflictStrategy
----------------------------------------------
Implements IConflictStrategy using the Version 1.0 conflict rule.

Methods to implement:

    is_conflict(
        course1: Course,
        course2: Course,
        selected_programs: List[str],
        semester: str
    ) -> bool

        Returns True if placing both courses on the same date would be a conflict.

        Conflict rule:
            Two courses conflict on a date if:
                1. They share at least one selected program_id,
                2. They are in the same study year,
                3. They are in the same semester,
                4. NOT both courses are "Elective" in that shared offering.

            In code terms:
                for each relevant offering1 in course1:
                    for each relevant offering2 in course2:
                        if same program, same year, same semester:
                            if NOT both elective:
                                return True
                return False

        The date equality check is handled by ScheduleGenerator.
        This class only decides whether two courses are allowed to share a date.

Notes:
    - Implements IConflictStrategy from interfaces/.
    - Keep this class thin — conflict logic only, no file I/O.
"""

from typing import List

from src.domain.course import Course
from src.interfaces.i_conflict_strategy import IConflictStrategy


class ExactConflictStrategy(IConflictStrategy):

    def is_conflict(
        self,
        course1: Course,
        course2: Course,
        selected_programs: List[str],
        semester: str,
    ) -> bool:

        course1_offerings = course1.get_relevant_offerings(
            selected_programs=selected_programs,
            semester=semester,
        )

        course2_offerings = course2.get_relevant_offerings(
            selected_programs=selected_programs,
            semester=semester,
        )

        for offering1 in course1_offerings:
            for offering2 in course2_offerings:
                same_group = offering1.same_program_year_semester(offering2)

                both_elective = (
                    offering1.is_elective()
                    and offering2.is_elective()
                )

                if same_group and not both_elective:
                    return True

        return False