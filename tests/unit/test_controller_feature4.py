"""
Unit Tests: DesktopController — Feature 4 (classroom assignment) gating.

Covers spec 4.3/4.4 capacity warnings, missing-StudentCount detection,
engine-input gating by the toggle, and programme-change staleness.
"""

import pytest

from src.controller import DesktopController
from src.domain.course import Course
from src.domain.course_offering import CourseOffering

from tests.unit._controller_helpers import _active_feature4_controller, _exam_course


@pytest.mark.parametrize(
    "capacity, mutate, expected",
    [
        # Capacity below the largest exam -> warn with (capacity, largest).
        (40, None, (40, 75)),
        # Sufficient capacity -> no warning.
        (100, None, None),
        # Feature 4 inactive (no proctor config) -> no warning regardless of capacity.
        (40, "clear_proctor_config", None),
        # Toggle disabled -> no warning even with files loaded.
        (40, "disable_toggle", None),
    ],
    ids=["low_capacity_warns", "sufficient_none", "inactive_none", "toggle_off_none"],
)
def test_feature4_capacity_shortfall_branches(capacity, mutate, expected):
    """Spec 4.4 pre-generation capacity warning across all gating branches."""
    ctrl = _active_feature4_controller(total_capacity=capacity, student_count=75)
    if mutate == "clear_proctor_config":
        ctrl.clear_proctor_config()
    elif mutate == "disable_toggle":
        ctrl.set_feature4_enabled(False)
    assert ctrl.feature4_capacity_shortfall() == expected


def test_feature4_capacity_compares_largest_single_exam_not_sum():
    """Spec 4.4: warn when capacity < ANY single exam, not the sum of exams."""
    ctrl = _active_feature4_controller(total_capacity=120, student_count=80)
    # Second exam: 100 students across two program lines (60 + 40).
    ctrl._courses.append(
        Course(
            id="22222",
            name="Physics",
            instructor="Dr. Levi",
            evaluation_type="Exam",
            offerings=[
                CourseOffering("83101", 1, "FALL", "Obligatory", 60),
                CourseOffering("83102", 1, "FALL", "Obligatory", 40),
            ],
        )
    )
    # Sum of all students = 180 > 120, but the largest single exam is 100 < 120,
    # so per spec 4.4 no warning should fire.
    assert ctrl.feature4_capacity_shortfall() is None


def test_feature4_ready_requires_student_counts_on_exam_courses():
    ctrl = _active_feature4_controller(total_capacity=200, student_count=50)
    assert ctrl.feature4_ready() is True

    ctrl._courses[0].offerings[0] = CourseOffering(
        "83101", 1, "FALL", "Obligatory", None
    )
    assert ctrl.feature4_missing_student_counts() is True
    assert ctrl.feature4_ready() is False


# ── §2: Feature 4 toggle gates engine inputs ─────────────────────────────────

def test_engine_inputs_pass_feature4_data_when_active():
    ctrl = _active_feature4_controller(total_capacity=200, student_count=50)
    assert ctrl.feature4_active is True
    assert ctrl.engine_classrooms() == ctrl.classrooms
    assert ctrl.engine_time_slots() == ctrl.time_slots
    assert ctrl.engine_proctor_config() is ctrl.proctor_config


def test_engine_inputs_empty_when_toggle_disabled_but_files_loaded():
    """§2: disabling the toggle must disable classroom assignment even though
    classroom/slot/proctor files remain loaded in memory."""
    ctrl = _active_feature4_controller(total_capacity=200, student_count=50)
    ctrl.set_feature4_enabled(False)

    assert ctrl.feature4_active is False
    assert ctrl.engine_classrooms() == []
    assert ctrl.engine_time_slots() == []
    assert ctrl.engine_proctor_config() is None


# ── §3: missing StudentCount is filtered by selected programmes/semester ──────

@pytest.mark.parametrize(
    "mutate, expected",
    [
        # An unrelated programme (83999) with a missing count must be ignored.
        pytest.param(
            lambda c: c._courses.append(
                Course(
                    id="99999",
                    name="Unrelated",
                    instructor="Dr. X",
                    evaluation_type="Exam",
                    offerings=[CourseOffering("83999", 1, "FALL", "Obligatory", None)],
                )
            ),
            False,
            id="unselected_programme_ignored",
        ),
        # Selected programme + loaded FALL period → relevant, so it blocks.
        pytest.param(
            lambda c: c._courses[0].offerings.__setitem__(
                0, CourseOffering("83101", 1, "FALL", "Obligatory", None)
            ),
            True,
            id="selected_programme_blocks",
        ),
        # Selected programme but a SPRING offering — not relevant to the FALL
        # period, so its missing count must not block generation.
        pytest.param(
            lambda c: c._courses.append(
                Course(
                    id="77777",
                    name="Spring Course",
                    instructor="Dr. Y",
                    evaluation_type="Exam",
                    offerings=[CourseOffering("83101", 1, "SPRI", "Obligatory", None)],
                )
            ),
            False,
            id="other_semester_ignored",
        ),
        # A non-exam (Project) course is never assigned rooms, so it never blocks.
        pytest.param(
            lambda c: c._courses.append(
                Course(
                    id="88888",
                    name="Project Course",
                    instructor="Dr. Z",
                    evaluation_type="Project",
                    offerings=[CourseOffering("83101", 1, "FALL", "Obligatory", None)],
                )
            ),
            False,
            id="non_exam_ignored",
        ),
    ],
)
def test_feature4_missing_student_counts_relevance(mutate, expected):
    """§3: missing StudentCount only blocks for selected, in-semester exams."""
    ctrl = _active_feature4_controller(total_capacity=200, student_count=50)
    mutate(ctrl)
    assert ctrl.feature4_missing_student_counts() is expected
    if expected:
        assert ctrl.feature4_ready() is False


# ── §4: capacity warning uses only selected relevant offerings ────────────────

def test_capacity_warning_ignores_unselected_programme():
    """A large exam in an unselected programme must not trigger the warning."""
    ctrl = _active_feature4_controller(total_capacity=120, student_count=50)
    ctrl._selected_programs = ["83101"]
    ctrl._courses.append(
        Course(
            id="66666",
            name="Huge Unselected",
            instructor="Dr. Big",
            evaluation_type="Exam",
            offerings=[CourseOffering("83999", 1, "FALL", "Obligatory", 5000)],
        )
    )
    # Only the relevant 50-student exam counts; 120 capacity is enough.
    assert ctrl.feature4_capacity_shortfall() is None


def test_capacity_warning_fires_for_large_selected_exam():
    ctrl = _active_feature4_controller(total_capacity=40, student_count=75)
    ctrl._selected_programs = ["83101"]
    assert ctrl.feature4_capacity_shortfall() == (40, 75)


# ── §7: changing programmes marks results stale and blocks export ─────────────

def test_set_selected_programs_marks_results_stale():
    ctrl = _active_feature4_controller(total_capacity=200, student_count=50)
    ctrl.clear_results_stale()
    assert ctrl.results_stale is False

    ctrl.set_selected_programs(["83101"])

    assert ctrl.results_stale is True


def test_export_refuses_stale_results_after_programme_change(tmp_path):
    ctrl = _active_feature4_controller(total_capacity=200, student_count=50)
    ctrl.clear_results_stale()
    ctrl.set_selected_programs(["83101"])

    with pytest.raises(ValueError, match="stale"):
        ctrl.export({}, tmp_path / "out.txt")


def test_missing_student_counts_not_vacuous_without_selected_programmes():
    """HIGH-12: enabling Feature 4 before selecting programmes still flags gaps."""
    ctrl = DesktopController()
    ctrl._feature4_enabled = True
    ctrl._courses = [_exam_course(None)]
    # No selected programmes — must fall back to the unfiltered check.
    assert ctrl._selected_programs == []
    assert ctrl.feature4_missing_student_counts() is True


def test_set_feature4_enabled_round_trip():
    """set_feature4_enabled toggling OFF clears the feature4_enabled flag."""
    ctrl = DesktopController()
    ctrl.set_feature4_enabled(True)
    assert ctrl.feature4_enabled is True

    ctrl.set_feature4_enabled(False)
    assert ctrl.feature4_enabled is False
    # Disabling marks results stale (any toggle change is an input change)
    assert ctrl.results_stale is True
