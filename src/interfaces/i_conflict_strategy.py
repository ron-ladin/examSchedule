"""
Interface: IConflictStrategy
-----------------------------
Contract for determining whether two courses conflict.

Abstract methods:
    - is_conflict(course1: Course, course2: Course) -> bool

        Returns True if both courses cannot share the same exam date.

        Conflict rule (Version 1.0):
            Two courses conflict if:
                - They share at least one selected program_id,
                - They are in the same study year,
                - They are in the same semester,
                - NOT both are marked as Elective.

        Date equality is enforced by the scheduling engine — this strategy
        only decides whether two courses are structurally allowed to share a date.

Notes:
    - Use ABC and @abstractmethod from the abc module.
    - The engine depends only on this interface, never on ExactConflictStrategy directly.
    - Implementations live in adapters/ — NOT here.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.course import Course


class IConflictStrategy(ABC):

    @abstractmethod
    def is_conflict(self, course1: "Course", course2: "Course") -> bool:
        """Return True if both courses cannot share the same exam date."""
