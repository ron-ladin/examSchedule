"""
Engine Service: schedule_validator
-----------------------------------
Engine-level wiring that applies the domain ThresholdFilter to a stream of
candidate schedules, dropping any that violate an *enabled* threshold
criterion (spec sections 2.1-2.5).

This module deliberately holds no metric logic of its own — the criterion
checks live in src/domain/threshold_filter.py. Its only job is to connect the
generation pipeline to that domain service so thresholds are actually enforced.

Public API:
    filter_schedules(schedules, courses, settings) -> list[Schedule]
"""

from collections.abc import Iterable
from typing import List

from src.domain.course import Course
from src.domain.schedule import Schedule
from src.domain.threshold import ThresholdSettings
from src.domain.threshold_filter import ThresholdFilter


def filter_schedules(
    schedules: Iterable[Schedule],
    courses: List[Course],
    settings: ThresholdSettings,
) -> List[Schedule]:
    """Return a new list keeping only schedules that satisfy every enabled
    threshold criterion in ``settings``.

    When no criterion is enabled, ThresholdFilter.is_valid returns True for
    every schedule, so this is a faithful pass-through — preserving today's
    behavior when Sprint 3 thresholds are toggled off. The input is never
    mutated.
    """
    return [
        schedule
        for schedule in schedules
        if ThresholdFilter.is_valid(schedule, courses, settings)
    ]
