"""
Unit Tests: PartialPlacementPolicy (SCRUM-390 refinement)
---------------------------------------------------------
The policy holds the "always place what you can, flag the gap" business rule
extracted out of AppController. It also distinguishes the two internal failure
reasons: STRUCTURAL_CAPACITY_SHORTFALL vs RUNTIME_ASSIGNMENT_FAILURE.

Pure unit tests — no controller, no UI, no file I/O.
"""

from src.domain.feature4_validator import UnplaceableExam
from src.domain.partial_placement_policy import (
    PartialPlacementPolicy,
    PlacementFailureReason,
)


def _unplaceable(course_id="10004", name="Advanced Materials"):
    return UnplaceableExam(
        course_id=course_id,
        name=name,
        student_count=400,
        max_usable_capacity=187,
    )


# --- decide() -------------------------------------------------------------

# No structural shortfall and no manual toggle: the fallback stays off.
def test_decide_no_shortfall_no_manual_disables_fallback():
    decision = PartialPlacementPolicy.decide(False, [])

    assert decision.allow_unassigned is False
    assert decision.reason is None
    assert decision.unplaceable_exams == ()


# A structural shortfall forces the fallback on, with the structural reason.
def test_decide_structural_shortfall_forces_structural_reason():
    decision = PartialPlacementPolicy.decide(False, [_unplaceable()])

    assert decision.allow_unassigned is True
    assert decision.reason is PlacementFailureReason.STRUCTURAL_CAPACITY_SHORTFALL
    assert decision.structural_course_ids == frozenset({"10004"})


# The manual toggle alone enables the fallback under the runtime-failure reason.
def test_decide_manual_only_uses_runtime_reason():
    decision = PartialPlacementPolicy.decide(True, [])

    assert decision.allow_unassigned is True
    assert decision.reason is PlacementFailureReason.RUNTIME_ASSIGNMENT_FAILURE
    assert decision.unplaceable_exams == ()


# When both apply, the structural reason wins (it is the more specific cause).
def test_decide_structural_takes_precedence_over_manual():
    decision = PartialPlacementPolicy.decide(True, [_unplaceable()])

    assert decision.allow_unassigned is True
    assert decision.reason is PlacementFailureReason.STRUCTURAL_CAPACITY_SHORTFALL


# --- classify() -----------------------------------------------------------

# An exam in the structural set is a capacity shortfall.
def test_classify_structural_course_is_capacity_shortfall():
    reason = PartialPlacementPolicy.classify("10004", frozenset({"10004"}))

    assert reason is PlacementFailureReason.STRUCTURAL_CAPACITY_SHORTFALL


# An exam not in the structural set failed at assignment time (runtime).
def test_classify_non_structural_course_is_runtime_failure():
    reason = PartialPlacementPolicy.classify("10002", frozenset({"10004"}))

    assert reason is PlacementFailureReason.RUNTIME_ASSIGNMENT_FAILURE
