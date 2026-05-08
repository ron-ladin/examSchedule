"""
Interface: IConflictStrategy
-----------------------------
Contract for determining whether two courses conflict.

Abstract methods to implement:
    - is_conflict(
          course1: Course,
          course2: Course,
          selected_programs: List[str],
          semester: str
      ) -> bool

        Returns True if scheduling both courses on the same date would cause a conflict.

        Conflict rule (Version 1.0):
            Two exams CONFLICT if:
                - They share at least one selected program_id
                - They are in the same study year
                - They are in the same semester
                - NOT both are marked as Elective

            In other words:
                conflict = same_selected_program AND same_year AND same_semester
                           AND NOT (course1_is_elective AND course2_is_elective)

        The date equality check is handled by the scheduling engine.
        This strategy only determines whether two courses are allowed to share a date.

Notes:
    - Use ABC and @abstractmethod from the abc module.
    - The engine uses this interface — it never calls ExactConflictStrategy directly.
    - Implementations live in adapters/ — NOT here.
"""

from abc import ABC, abstractmethod
from typing import List

from src.domain.course import Course


class IConflictStrategy(ABC):

    @abstractmethod
    def is_conflict(
        self,
        course1: Course,
        course2: Course,
        selected_programs: List[str],
        semester: str,
    ) -> bool:
        pass