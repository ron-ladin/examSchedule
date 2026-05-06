"""
Interface: IConflictStrategy
-----------------------------
Contract for determining whether two courses conflict on a given date.

Abstract methods to implement:
    - is_conflict(course1: Course, course2: Course, date: date) -> bool
        Returns True if scheduling both courses on the same date causes a conflict.

        Conflict rule (Version 1.0):
            Two exams CONFLICT if:
                - They share the same date AND
                - They share at least one (program_id, year) pair in their offerings AND
                - NOT both are marked as Elective

            In other words:
                conflict = same_date AND same_program AND same_year
                           AND NOT (course1_is_elective AND course2_is_elective)

Notes:
    - Use ABC and @abstractmethod from the abc module.
    - The engine uses this interface — it never calls ExactConflictStrategy directly.
    - Implementations live in adapters/ — NOT here.
"""

from abc import ABC, abstractmethod


class IConflictStrategy(ABC):
    pass
