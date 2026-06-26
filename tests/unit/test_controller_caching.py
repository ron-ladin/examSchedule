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


# ── SCRUM-393: incremental (streaming) caching ──────────────────────────────

def test_incremental_cache_merges_periods_across_batches():
    """Each streamed batch must accumulate, not replace, earlier periods."""
    from src.domain.schedule import Schedule
    from src.domain.exam_period import ExamPeriod
    from src.domain.sorting import SortingConfig

    ctrl = DesktopController()
    ctrl._courses = [_exam_course(30)]

    period = ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 9))])
    fall = [Schedule(period, {"11111": date(2026, 1, 5)})]
    spring_period = ExamPeriod("SPRI", "Aleph", [(date(2026, 6, 1), date(2026, 6, 5))])
    spring = [Schedule(spring_period, {"11111": date(2026, 6, 1)})]

    ctrl.begin_streaming_cache()
    first = ctrl.cache_generated_results_incremental({"FALL - Aleph": fall})
    second = ctrl.cache_generated_results_incremental({"SPRI - Aleph": spring})

    # Each call returns only its own batch …
    assert set(first) == {"FALL - Aleph"}
    assert set(second) == {"SPRI - Aleph"}

    # … but the cache holds every period streamed so far, so resort() sees all.
    resorted = ctrl.resort(SortingConfig(rules=[]))
    assert set(resorted) == {"FALL - Aleph", "SPRI - Aleph"}


def test_begin_streaming_cache_clears_previous_run():
    """A new streaming run must not inherit the previous run's results."""
    from src.domain.schedule import Schedule
    from src.domain.exam_period import ExamPeriod

    ctrl = DesktopController()
    ctrl._courses = [_exam_course(30)]

    period = ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 9))])
    ctrl.begin_streaming_cache()
    ctrl.cache_generated_results_incremental(
        {"FALL - Aleph": [Schedule(period, {"11111": date(2026, 1, 5)})]}
    )

    ctrl.begin_streaming_cache()
    assert ctrl._last_results == {}


# ── M4: engine-level schedule rejection count ─────────────────────────────────

def test_pipeline_flags_structurally_unplaceable_exam(tmp_path):
    """An exam too large for any room is flagged unassigned, not dropped (SCRUM-390).

    "Always place what you can, flag the gap": an exam whose student count
    structurally exceeds the combined usable room capacity must NOT blank the
    solution space. The pipeline auto-routes the shortfall through the unassigned
    fallback, so the schedule is still produced with the oversized exam recorded
    in ``unassigned_classroom_exams`` and given no room assignment.

    Guarantee that the generator emits exactly one candidate: one course + one
    valid date (Monday 2026-01-05). Classrooms are intentionally undersized so the
    exam cannot be placed, exercising the structural-shortfall fallback path.
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
    period_key = "FALL - Aleph"
    assert period_key in schedules_by_period

    # New policy: the schedule is kept, with the oversized exam flagged unassigned
    # instead of the whole candidate being dropped.
    schedules = schedules_by_period[period_key]
    assert len(schedules) == 1, (
        "Structurally unplaceable exam must be flagged, not blank the solution space"
    )
    flagged = schedules[0]
    assert flagged.unassigned_classroom_exams.get("99999") == 200
    assert not flagged.classroom_assignments.get("99999")
