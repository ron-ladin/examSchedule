"""
Unit Tests: DesktopController — result caching, resort, and §4.4 rejection.

Covers cache_generated_results keeping _last_results in sync (C2 load-more
fix) and the engine-level schedule rejection path (M4).
"""

from datetime import date, time

from src.controller import DesktopController

from tests.unit._controller_helpers import _exam_course


# ── C2: cache_generated_results keeps _last_results in sync ──────────────────

def test_cache_generated_results_stores_sorted_schedules():
    """cache_generated_results must populate _last_results so resort() works."""
    from src.domain.schedule import Schedule
    from src.domain.exam_period import ExamPeriod

    ctrl = DesktopController()
    ctrl._courses = [_exam_course(30)]

    period = ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 9))])
    s1 = Schedule(period, {"11111": date(2026, 1, 5)})
    s2 = Schedule(period, {"11111": date(2026, 1, 6)})

    result = ctrl.cache_generated_results({"FALL_Aleph": [s1, s2]})

    # Return value matches what was stored
    assert result == {"FALL_Aleph": [s1, s2]}
    # _last_results must be populated — otherwise resort() raises
    assert ctrl._last_results is not None
    assert ctrl._last_results == result


def test_cache_generated_results_enables_resort():
    """After cache_generated_results, resort() must include ALL cached schedules."""
    from src.domain.schedule import Schedule
    from src.domain.exam_period import ExamPeriod
    from src.domain.sorting import SortingConfig

    ctrl = DesktopController()
    ctrl._courses = [_exam_course(30)]

    period = ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 9))])
    s1 = Schedule(period, {"11111": date(2026, 1, 5)})
    s2 = Schedule(period, {"11111": date(2026, 1, 6)})

    ctrl.cache_generated_results({"FALL_Aleph": [s1, s2]})

    # resort() must not raise and must return both schedules
    resorted = ctrl.resort(SortingConfig(rules=[]))
    assert len(resorted["FALL_Aleph"]) == 2


def test_cache_generated_results_with_load_more_includes_extra_schedules():
    """Simulates the C2 bug: load-more schedules must survive a subsequent resort."""
    from src.domain.schedule import Schedule
    from src.domain.exam_period import ExamPeriod
    from src.domain.sorting import SortingConfig

    ctrl = DesktopController()
    ctrl._courses = [_exam_course(30)]

    period = ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 9))])
    initial = [Schedule(period, {"11111": date(2026, 1, 5)})]
    extra = [Schedule(period, {"11111": date(2026, 1, 6)})]

    # Simulate initial generation
    ctrl.cache_generated_results({"FALL_Aleph": initial})

    # Simulate load-more appending extra schedules and then re-caching (C2 fix)
    all_schedules = {"FALL_Aleph": initial + extra}
    ctrl.cache_generated_results(all_schedules)

    # Both schedules must be present after re-sort
    resorted = ctrl.resort(SortingConfig(rules=[]))
    assert len(resorted["FALL_Aleph"]) == 2


# ── M4: engine-level schedule rejection count ─────────────────────────────────

def test_pipeline_rejects_unassignable_schedules(tmp_path):
    """Schedules where any exam cannot be assigned rooms must be dropped (spec §4.4).

    Guarantee that the generator emits at least one candidate before the assigner
    runs: one course + one valid date (Monday 2026-01-05) → exactly one schedule
    produced by backtracking. Classrooms are intentionally undersized so the
    assigner must return None for that schedule, proving the §4.4 rejection path.
    """
    from queue import Queue
    from src.controller import _run_generation_process
    from src.domain.exam_period import ExamPeriod
    from src.domain.classroom import Classroom
    from src.domain.time_slot import TimeSlot
    from src.domain.proctor import ProctorConfig
    from src.domain.course import Course
    from src.domain.course_offering import CourseOffering

    # One course with 200 students, one weekday in the period window → the generator
    # MUST emit exactly one schedule (there is only one valid date assignment).
    big_course = Course(
        "99999",
        "Huge Exam",
        "Dr. Test",
        "Exam",
        [CourseOffering("83101", 1, "FALL", "Obligatory", 200)],
    )
    # 2026-01-05 is a Monday — guaranteed valid date; single-day window forces
    # exactly one generated schedule before the assigner is exercised.
    period = ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 5))])
    classrooms = [Classroom("Room A", 25), Classroom("Room B", 25)]  # total 50 < 200
    slots = [TimeSlot(time(9, 0))]

    q: Queue = Queue()
    _run_generation_process(
        q,
        [big_course],
        [period],
        ["83101"],
        classrooms=classrooms,
        time_slots=slots,
        proctor_config=ProctorConfig(20),
        allow_unassigned_classrooms=False,
    )

    result = q.get_nowait()
    schedules_by_period = result.schedules_by_period
    assert result.success is True
    # The period key must be present — the generator produced a candidate but the
    # assigner rejected it (rooms too small), so the list is empty, not missing.
    period_key = "FALL - Aleph"
    assert period_key in schedules_by_period, (
        "Period key missing: generator produced no candidates — "
        "test fixture must guarantee at least one schedule before assigner runs"
    )
    assert schedules_by_period[period_key] == [], (
        "Schedules with unassignable exams must be rejected by the assigner (spec §4.4)"
    )
