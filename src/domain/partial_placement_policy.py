"""
Partial Placement Policy
------------------------
Business policy for "always place what you can, flag the gap" (SCRUM-390).

Keeps the decision of *whether* a period must route through the unassigned
classroom fallback — and *why* — out of AppController, which should stay a thin
orchestration layer rather than encoding business rules.

Two failure modes are deliberately distinguished:

- STRUCTURAL_CAPACITY_SHORTFALL: an exam's student count exceeds the combined
  usable capacity of every room, so it can never be placed under any room
  arrangement. Detected pre-flight by Feature4Validator.unplaceable_exams.
- RUNTIME_ASSIGNMENT_FAILURE: an exam fits the total capacity but no valid room
  combination is free at assignment time (e.g. slot/room contention with other
  exams scheduled on the same date). Surfaces only while assigning rooms.

Both can land an exam in ``unassigned_classroom_exams``, but they are different
problems and must not be represented as the same reason internally.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.domain.feature4_validator import UnplaceableExam


class PlacementFailureReason(str, Enum):
    """Why an exam was routed into the unassigned classroom fallback."""

    STRUCTURAL_CAPACITY_SHORTFALL = "STRUCTURAL_CAPACITY_SHORTFALL"
    RUNTIME_ASSIGNMENT_FAILURE = "RUNTIME_ASSIGNMENT_FAILURE"


@dataclass(frozen=True)
class PartialPlacementDecision:
    """Outcome of the policy for one exam period.

    allow_unassigned: whether ClassroomAssigner may flag un-placeable exams
        instead of dropping the whole schedule.
    reason: why the fallback is enabled, or None when it is not.
    unplaceable_exams: structural pre-flight shortfalls for this period.
    """

    allow_unassigned: bool
    reason: PlacementFailureReason | None
    unplaceable_exams: tuple[UnplaceableExam, ...]

    @property
    def structural_course_ids(self) -> frozenset[str]:
        """Course ids that are structurally un-placeable for this period."""
        return frozenset(exam.course_id for exam in self.unplaceable_exams)


class PartialPlacementPolicy:
    """Decides whether/why a period uses the unassigned classroom fallback."""

    @staticmethod
    def decide(
        manual_allow_unassigned: bool,
        unplaceable_exams: list[UnplaceableExam],
    ) -> PartialPlacementDecision:
        """Resolve the effective fallback behavior for one period.

        A structural shortfall forces the fallback regardless of the manual
        toggle and is the more specific reason. The manual toggle alone still
        enables the fallback so that *runtime* assignment failures are flagged
        rather than blanking the whole solution space.
        """
        structural = tuple(unplaceable_exams)

        if structural:
            reason: PlacementFailureReason | None = (
                PlacementFailureReason.STRUCTURAL_CAPACITY_SHORTFALL
            )
        elif manual_allow_unassigned:
            reason = PlacementFailureReason.RUNTIME_ASSIGNMENT_FAILURE
        else:
            reason = None

        return PartialPlacementDecision(
            allow_unassigned=reason is not None,
            reason=reason,
            unplaceable_exams=structural,
        )

    @staticmethod
    def classify(
        course_id: str,
        structural_course_ids: frozenset[str],
    ) -> PlacementFailureReason:
        """Classify why one unassigned exam ended up in the fallback.

        An exam known to be structurally un-placeable (flagged pre-flight) is a
        STRUCTURAL_CAPACITY_SHORTFALL; anything else that fails at assignment
        time is a RUNTIME_ASSIGNMENT_FAILURE.
        """
        if course_id in structural_course_ids:
            return PlacementFailureReason.STRUCTURAL_CAPACITY_SHORTFALL
        return PlacementFailureReason.RUNTIME_ASSIGNMENT_FAILURE
