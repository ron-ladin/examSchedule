"""
Interface: IConflictStrategy
-----------------------------
Contract for determining whether two courses conflict on a given date.

Abstract methods to implement:
    - is_conflict(course1: Course, course2: Course, date: date) -> bool
        Returns True if scheduling both courses on the same date causes a conflict.

        Conflict rule (Version 1.0):
            Two courses conflict if:
                - They share at least one (program_id, year) pair in their offerings, AND
                - NOT both courses are marked as "Elective" in that shared offering.

Notes:
    - Use ABC and @abstractmethod from the abc module.
    - The engine uses this interface -- never calls ExactConflictStrategy directly.
    - Implementations live in adapters/ -- NOT here.
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.course import Course


class IConflictStrategy(ABC):
    """Contract for conflict detection between two courses on the same date."""

    @abstractmethod
    def is_conflict(self, course1: "Course", course2: "Course", exam_date: date) -> bool:
        """Return True if assigning both courses to exam_date causes a conflict."""
