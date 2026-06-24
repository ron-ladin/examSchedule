"""
Generation Result DTO
----------------------
Strongly-typed contract for the payload returned by background generation
workers (date-option generation and classroom-variant generation).

Replaces the hand-rolled tuples previously passed over multiprocessing queues:
    success: (True, schedules_by_period, courses_by_id, truncated_periods)
    failure: (False, error_message)

The dataclass is frozen and contains only picklable data, so it crosses the
multiprocessing boundary safely. Use the ``ok`` / ``failure`` constructors at
producer sites and the ``success`` flag plus typed attributes at consumer sites
instead of structural ``isinstance`` / ``len == 4`` checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.course import Course
from src.domain.schedule import Schedule


@dataclass(frozen=True)
class GenerationResult:
    """Typed result of a background generation task."""

    success: bool
    schedules_by_period: dict[str, list[Schedule]] = field(default_factory=dict)
    courses_by_id: dict[str, Course] = field(default_factory=dict)
    truncated_periods: set[str] = field(default_factory=set)
    error: str | None = None

    @classmethod
    def ok(
        cls,
        schedules_by_period: dict[str, list[Schedule]],
        courses_by_id: dict[str, Course],
        truncated_periods: set[str],
    ) -> "GenerationResult":
        """Build a successful result."""
        return cls(
            success=True,
            schedules_by_period=dict(schedules_by_period),
            courses_by_id=dict(courses_by_id),
            truncated_periods=set(truncated_periods),
        )

    @classmethod
    def failure(cls, error: str) -> "GenerationResult":
        """Build a failed result carrying an error message."""
        return cls(success=False, error=error)


@dataclass(frozen=True)
class GenerationDone:
    """Terminal marker for streaming generation.

    When a worker streams one ``GenerationResult`` per exam period as each
    period finishes, it puts a single ``GenerationDone`` on the queue afterwards
    so the consumer knows generation is complete (even when zero periods were
    produced). It carries the final ``truncated_periods`` set so the consumer can
    finalise has-more state. Picklable; crosses the multiprocessing boundary
    safely. Distinct type — not a ``GenerationResult`` — so partial results and
    the final marker are never confused.
    """

    truncated_periods: set[str] = field(default_factory=set)

    @classmethod
    def done(cls, truncated_periods: set[str] | None = None) -> "GenerationDone":
        """Build the terminal marker carrying the final truncated-period set."""
        return cls(truncated_periods=set(truncated_periods or set()))
