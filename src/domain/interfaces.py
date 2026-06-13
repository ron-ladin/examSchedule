"""
Domain Interfaces
------------------
Abstract contracts for domain services.
"""

from abc import ABC, abstractmethod
from typing import List

from src.domain.course import Course
from src.domain.schedule import Schedule
from src.domain.threshold import ThresholdSettings


class IThresholdFilter(ABC):
    """Contract for filtering schedules against threshold criteria (spec 2.1–2.5)."""

    @staticmethod
    @abstractmethod
    def is_valid(
        schedule: Schedule,
        courses: List[Course],
        settings: ThresholdSettings,
    ) -> bool:
        """Return True if the schedule satisfies all enabled threshold criteria."""
