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

from datetime import date

from src.domain.course import Course
from src.interfaces.i_conflict_strategy import IConflictStrategy


class ExactConflictStrategy(IConflictStrategy):
    """Conflict rule: same program + same year + same semester + not both elective = conflict."""

    def is_conflict(self, course1: Course, course2: Course, exam_date: date) -> bool:
        """Return True if course1 and course2 cannot share the same exam date.

        The exam_date argument is accepted for interface compatibility but unused
        in v1.0 -- conflicts depend only on program/year/semester overlap.
        """
        for o1 in course1.offerings:
            for o2 in course2.offerings:
                # Students overlap only if same program, same year, and same semester
                same_group = (
                    o1.program_id == o2.program_id
                    and o1.year == o2.year
                    and o1.semester == o2.semester
                )
                if same_group:
                    # Two electives never conflict -- students choose only one of them
                    both_elective = (
                        o1.requirement == "Elective"
                        and o2.requirement == "Elective"
                    )
                    if not both_elective:
                        return True
        return False
