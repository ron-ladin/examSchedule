from datetime import date

from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.placement_constraint import (
    MaxElectiveCollisionsConstraint,
    MaxExamsPerDayConstraint,
    MinDaysConstraint,
    PlacementConstraintSet,
)
from src.domain.threshold import Criterion, ThresholdEntry, ThresholdSettings


def _course(
    course_id: str,
    *offerings: CourseOffering,
) -> Course:
    return Course(
        id=course_id,
        name=f"Course {course_id}",
        instructor="Dr. Test",
        evaluation_type="Exam",
        offerings=list(offerings),
    )


def _offering(
    program_id: str = "83101",
    year: int = 1,
    semester: str = "FALL",
    requirement: str = "Obligatory",
) -> CourseOffering:
    return CourseOffering(program_id, year, semester, requirement)


def _period() -> ExamPeriod:
    return ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 9))])


def _settings(*entries: ThresholdEntry) -> ThresholdSettings:
    return ThresholdSettings(entries=entries)


def test_empty_constraint_set_allows_every_placement():
    course = _course("11111", _offering())
    constraints = PlacementConstraintSet([])

    assert constraints.allows(course, date(2026, 1, 5))
    constraints.record(course, date(2026, 1, 5))
    constraints.undo(course, date(2026, 1, 5))
    assert constraints.allows(course, date(2026, 1, 5))


def test_max_exams_per_day_blocks_second_exam_on_same_day_when_k_is_one():
    first = _course("11111", _offering())
    second = _course("22222", _offering("83102", 2))
    constraint = MaxExamsPerDayConstraint(k=1)
    exam_date = date(2026, 1, 5)

    assert constraint.allows(first, exam_date)
    constraint.record(first, exam_date)

    assert not constraint.allows(second, exam_date)
    assert constraint.allows(second, date(2026, 1, 6))


def test_max_exams_per_day_record_then_undo_fully_restores_state():
    course = _course("11111", _offering())
    constraint = MaxExamsPerDayConstraint(k=1)
    exam_date = date(2026, 1, 5)

    constraint.record(course, exam_date)
    constraint.undo(course, exam_date)

    assert constraint._day_counts == {}
    assert constraint.allows(course, exam_date)


def test_min_days_for_mandatory_exams_blocks_only_obligatory_groups():
    obligatory_a = _course("11111", _offering(requirement="Obligatory"))
    obligatory_b = _course("22222", _offering(requirement="Obligatory"))
    elective = _course("33333", _offering(requirement="Elective"))
    constraints = PlacementConstraintSet.build(
        _settings(
            ThresholdEntry(
                Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS,
                True,
                2,
            )
        ),
        [obligatory_a, obligatory_b, elective],
        ["83101"],
        _period(),
    )

    constraints.record(obligatory_a, date(2026, 1, 5))

    assert not constraints.allows(obligatory_b, date(2026, 1, 6))
    assert constraints.allows(elective, date(2026, 1, 6))


def test_min_days_for_any_exams_includes_obligatory_and_elective_offerings():
    obligatory = _course("11111", _offering(requirement="Obligatory"))
    elective = _course("22222", _offering(requirement="Elective"))
    constraints = PlacementConstraintSet.build(
        _settings(
            ThresholdEntry(Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS, True, 2)
        ),
        [obligatory, elective],
        ["83101"],
        _period(),
    )

    constraints.record(obligatory, date(2026, 1, 5))

    assert not constraints.allows(elective, date(2026, 1, 6))
    assert constraints.allows(elective, date(2026, 1, 7))


def test_min_days_with_k_zero_allows_everything():
    first = _course("11111", _offering())
    second = _course("22222", _offering())
    constraint = MinDaysConstraint(
        k=0,
        groups_by_course_id={
            "11111": (("83101", 1),),
            "22222": (("83101", 1),),
        },
    )
    exam_date = date(2026, 1, 5)

    constraint.record(first, exam_date)

    assert constraint.allows(second, exam_date)


def test_max_elective_collisions_blocks_second_same_day_collision_when_k_zero():
    first = _course("11111", _offering(requirement="Elective"))
    second = _course("22222", _offering(requirement="Elective"))
    constraints = PlacementConstraintSet.build(
        _settings(
            ThresholdEntry(Criterion.MAX_ELECTIVE_COLLISIONS, True, 0)
        ),
        [first, second],
        ["83101"],
        _period(),
    )

    constraints.record(first, date(2026, 1, 5))

    assert not constraints.allows(second, date(2026, 1, 5))
    assert constraints.allows(second, date(2026, 1, 6))


def test_max_elective_collisions_record_then_undo_fully_restores_state():
    first = _course("11111", _offering(requirement="Elective"))
    second = _course("22222", _offering(requirement="Elective"))
    constraint = MaxElectiveCollisionsConstraint(
        k=1,
        programs_by_course_id={
            "11111": ("83101",),
            "22222": ("83101",),
        },
    )
    exam_date = date(2026, 1, 5)

    constraint.record(first, exam_date)
    constraint.record(second, exam_date)
    constraint.undo(second, exam_date)
    constraint.undo(first, exam_date)

    assert constraint._date_counts_by_program == {}
    assert constraint._collisions_by_program == {}
    assert constraint.allows(first, exam_date)


def test_course_with_multiple_offerings_is_counted_in_all_relevant_groups():
    shared = _course(
        "11111",
        _offering("83101", 1, requirement="Obligatory"),
        _offering("83102", 2, requirement="Obligatory"),
    )
    first_program_peer = _course(
        "22222",
        _offering("83101", 1, requirement="Obligatory"),
    )
    second_program_peer = _course(
        "33333",
        _offering("83102", 2, requirement="Obligatory"),
    )
    constraints = PlacementConstraintSet.build(
        _settings(
            ThresholdEntry(
                Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS,
                True,
                2,
            )
        ),
        [shared, first_program_peer, second_program_peer],
        ["83101", "83102"],
        _period(),
    )

    constraints.record(shared, date(2026, 1, 5))

    assert not constraints.allows(first_program_peer, date(2026, 1, 6))
    assert not constraints.allows(second_program_peer, date(2026, 1, 6))


def test_exam_period_spread_is_not_installed_in_constraint_set():
    course = _course("11111", _offering())
    constraints = PlacementConstraintSet.build(
        _settings(
            ThresholdEntry(Criterion.MIN_DAYS_EXAM_PERIOD_SPREAD, True, 3)
        ),
        [course],
        ["83101"],
        _period(),
    )

    assert constraints.constraints == ()
    assert constraints.allows(course, date(2026, 1, 5))
