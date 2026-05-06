"""
Infrastructure Adapter: ExactConflictStrategy
----------------------------------------------
Implements IConflictStrategy using the Version 1.0 conflict rule.

Methods to implement:

    is_conflict(course1: Course, course2: Course, date: date) -> bool
        Returns True if placing both courses on the same date is a conflict.

        Conflict rule:
            Two courses conflict if:
                1. They share at least one (program_id, year) pair across their offerings, AND
                2. NOT both courses are "Elective" in that shared offering.

            Logic:
                for each offering1 in course1.offerings:
                    for each offering2 in course2.offerings:
                        if offering1.program_id == offering2.program_id
                           and offering1.year == offering2.year:
                            if NOT (offering1.requirement == "Elective"
                                    and offering2.requirement == "Elective"):
                                return True
                return False

        The `date` parameter is accepted for interface compatibility
        but is not used in version 1.0 (conflicts are date-agnostic).

Notes:
    - Implements IConflictStrategy from interfaces/.
    - Keep this class thin -- conflict logic only, no file I/O.
"""

from src.interfaces.i_conflict_strategy import IConflictStrategy


class ExactConflictStrategy(IConflictStrategy):
    pass
