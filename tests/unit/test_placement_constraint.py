from datetime import date

import pytest

from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.placement_constraint import (
    MaxElectiveCollisionsConstraint,
    MaxExamsPerDayConstraint,
    MinDaysConstraint,
    PlacementConstraint,
    PlacementConstraintSet,
)
from src.domain.threshold import Criterion, ThresholdEntry, ThresholdSettings


def _course(
    course_id: str,
    offerings: list[CourseOffering] | None = None,
) -> Course:
    course = Course(
        id=course_id,
        name=f"Course {course_id}",
        instructor="Dr. Test",
        evaluation_type="Exam",
    )
    for offering in offerings or []:
        course.add_offering(offering)
    return course


def _offering(
    program_id: str = "83101",
    year: int = 1,
    semester: str = "FALL",
    requirement: str = "Obligatory",
) -> CourseOffering:
    return CourseOffering(
        program_id=program_id,
        year=year,
        semester=semester,
        requirement=requirement,
    )


def _period() -> ExamPeriod:
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 9))],
        excluded_dates=set(),
    )


def _settings(criterion: Criterion, k: int) -> ThresholdSettings:
    return ThresholdSettings(entries=(ThresholdEntry(criterion, True, k),))


def test_empty_constraint_set_always_allows_placements():
    constraints = PlacementConstraintSet([])
    course = _course("11111")
    exam_date = date(2026, 1, 5)

    assert constraints.allows(course, exam_date)

    constraints.record(course, exam_date)
    constraints.undo(course, exam_date)

    assert constraints.allows(course, exam_date)


def test_max_exams_per_day_allows_first_and_blocks_second_same_day_for_k1():
    first = _course("11111")
    second = _course("22222")
    exam_date = date(2026, 1, 5)
    constraint = MaxExamsPerDayConstraint(1)

    assert constraint.allows(first, exam_date)
    constraint.record(first, exam_date)

    assert not constraint.allows(second, exam_date)
    assert constraint.allows(second, date(2026, 1, 6))


def test_max_exams_per_day_with_k0_blocks_every_placement():
    constraint = MaxExamsPerDayConstraint(0)

    assert not constraint.allows(_course("11111"), date(2026, 1, 5))


def test_max_exams_per_day_record_then_undo_fully_restores_state():
    course = _course("11111")
    exam_date = date(2026, 1, 5)
    constraint = MaxExamsPerDayConstraint(2)

    constraint.record(course, exam_date)
    constraint.undo(course, exam_date)

    assert constraint._date_counts == {}


def test_min_days_with_k0_allows_everything():
    first = _course("11111")
    second = _course("22222")
    constraint = MinDaysConstraint(
        0,
        {
            first.id: (("83101", 1),),
            second.id: (("83101", 1),),
        },
    )

    constraint.record(first, date(2026, 1, 5))

    assert constraint.allows(second, date(2026, 1, 5))
    assert constraint.allows(second, date(2026, 1, 6))
    assert constraint._date_counts_by_group == {}


def test_min_days_with_k1_blocks_same_day_only():
    first = _course("11111")
    second = _course("22222")
    constraint = MinDaysConstraint(
        1,
        {
            first.id: (("83101", 1),),
            second.id: (("83101", 1),),
        },
    )

    constraint.record(first, date(2026, 1, 5))

    assert not constraint.allows(second, date(2026, 1, 5))
    assert constraint.allows(second, date(2026, 1, 6))


def test_min_days_with_k2_blocks_same_day_and_adjacent_day():
    first = _course("11111")
    second = _course("22222")
    constraint = MinDaysConstraint(
        2,
        {
            first.id: (("83101", 1),),
            second.id: (("83101", 1),),
        },
    )

    constraint.record(first, date(2026, 1, 5))

    assert not constraint.allows(second, date(2026, 1, 5))
    assert not constraint.allows(second, date(2026, 1, 6))
    assert constraint.allows(second, date(2026, 1, 7))


def test_mandatory_min_days_includes_only_obligatory_offerings():
    mandatory = _course("11111", [_offering(requirement="Obligatory")])
    elective = _course("22222", [_offering(requirement="Elective")])
    constraints = PlacementConstraintSet.build(
        _settings(Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS, 1),
        [mandatory, elective],
        ["83101"],
        _period(),
    )

    constraints.record(mandatory, date(2026, 1, 5))

    assert constraints.allows(elective, date(2026, 1, 5))


def test_any_min_days_includes_obligatory_and_elective_offerings():
    mandatory = _course("11111", [_offering(requirement="Obligatory")])
    elective = _course("22222", [_offering(requirement="Elective")])
    constraints = PlacementConstraintSet.build(
        _settings(Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS, 1),
        [mandatory, elective],
        ["83101"],
        _period(),
    )

    constraints.record(mandatory, date(2026, 1, 5))

    assert not constraints.allows(elective, date(2026, 1, 5))


def test_course_with_multiple_relevant_offerings_counts_in_all_groups():
    shared = _course(
        "11111",
        [
            _offering(program_id="83101", year=1),
            _offering(program_id="83102", year=2),
        ],
    )
    same_first_group = _course("22222", [_offering(program_id="83101", year=1)])
    same_second_group = _course("33333", [_offering(program_id="83102", year=2)])
    constraints = PlacementConstraintSet.build(
        _settings(Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS, 1),
        [shared, same_first_group, same_second_group],
        ["83101", "83102"],
        _period(),
    )

    constraints.record(shared, date(2026, 1, 5))

    assert not constraints.allows(same_first_group, date(2026, 1, 5))
    assert not constraints.allows(same_second_group, date(2026, 1, 5))


def test_max_elective_collisions_with_k0_blocks_second_same_day_pair():
    first = _course("11111")
    second = _course("22222")
    constraint = MaxElectiveCollisionsConstraint(
        0,
        {
            first.id: ("83101",),
            second.id: ("83101",),
        },
    )

    constraint.record(first, date(2026, 1, 5))

    assert not constraint.allows(second, date(2026, 1, 5))
    assert constraint.allows(second, date(2026, 1, 6))


def test_max_elective_collisions_record_then_undo_fully_restores_state():
    first = _course("11111")
    second = _course("22222")
    constraint = MaxElectiveCollisionsConstraint(
        10,
        {
            first.id: ("83101",),
            second.id: ("83101",),
        },
    )

    constraint.record(first, date(2026, 1, 5))
    constraint.record(second, date(2026, 1, 5))
    constraint.undo(second, date(2026, 1, 5))
    constraint.undo(first, date(2026, 1, 5))

    assert constraint._date_counts_by_program == {}
    assert constraint._collisions_by_program == {}


def test_exam_period_spread_is_not_installed_in_constraint_set():
    courses = [_course("11111", [_offering()])]
    constraints = PlacementConstraintSet.build(
        _settings(Criterion.MIN_DAYS_EXAM_PERIOD_SPREAD, 5),
        courses,
        ["83101"],
        _period(),
    )

    assert constraints._constraints == []

class _RecordingConstraint(PlacementConstraint):
    def __init__(self) -> None:
        self.recorded: list[tuple[Course, date]] = []
        self.undone: list[tuple[Course, date]] = []

    def allows(self, course: Course, exam_date: date) -> bool:
        return True

    def record(self, course: Course, exam_date: date) -> None:
        self.recorded.append((course, exam_date))

    def undo(self, course: Course, exam_date: date) -> None:
        self.undone.append((course, exam_date))
        self.recorded.remove((course, exam_date))


class _FailingRecordConstraint(PlacementConstraint):
    def allows(self, course: Course, exam_date: date) -> bool:
        return True

    def record(self, course: Course, exam_date: date) -> None:
        raise RuntimeError("record failed")

    def undo(self, course: Course, exam_date: date) -> None:
        raise AssertionError("undo must not be called for an unrecorded constraint")


def test_constraint_set_rolls_back_prior_records_when_composite_record_fails():
    course = _course("11111")
    exam_date = date(2026, 1, 5)
    first = _RecordingConstraint()
    constraints = PlacementConstraintSet([first, _FailingRecordConstraint()])

    with pytest.raises(RuntimeError, match="record failed"):
        constraints.record(course, exam_date)

    assert first.recorded == []
    assert first.undone == [(course, exam_date)]
