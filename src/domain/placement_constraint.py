from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.domain.schedule_metrics import relevant_offerings
from src.domain.threshold import Criterion, ThresholdSettings


class PlacementConstraint(ABC):
    """Mutable placement constraint used during one generation traversal."""

    @abstractmethod
    def allows(self, course: Course, exam_date: date) -> bool:
        """Return whether placing ``course`` on ``exam_date`` is still valid."""

    @abstractmethod
    def record(self, course: Course, exam_date: date) -> None:
        """Record an accepted placement."""

    @abstractmethod
    def undo(self, course: Course, exam_date: date) -> None:
        """Undo a previously recorded placement."""


class PlacementConstraintSet:
    """Collection of placement constraints with null-object empty behavior."""

    def __init__(self, constraints: list[PlacementConstraint]) -> None:
        self._constraints = list(constraints)

    @property
    def constraints(self) -> tuple[PlacementConstraint, ...]:
        return tuple(self._constraints)

    def __bool__(self) -> bool:
        return bool(self._constraints)

    @classmethod
    def build(
        cls,
        threshold_settings: ThresholdSettings,
        courses: list[Course],
        selected_programs: list[str],
        exam_period: ExamPeriod,
    ) -> "PlacementConstraintSet":
        entries = {
            entry.criterion: entry.k
            for entry in threshold_settings.entries
            if entry.enabled
        }
        selected_set = set(selected_programs)
        constraints: list[PlacementConstraint] = []

        if Criterion.MAX_EXAMS_PER_DAY in entries:
            constraints.append(
                MaxExamsPerDayConstraint(entries[Criterion.MAX_EXAMS_PER_DAY])
            )

        if Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS in entries:
            constraints.append(
                MinDaysConstraint(
                    entries[Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS],
                    _groups_by_course_id(
                        courses,
                        selected_set,
                        exam_period.semester,
                        requirement="obligatory",
                    ),
                )
            )

        if Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS in entries:
            constraints.append(
                MinDaysConstraint(
                    entries[Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS],
                    _groups_by_course_id(
                        courses,
                        selected_set,
                        exam_period.semester,
                        requirement=None,
                    ),
                )
            )

        if Criterion.MAX_ELECTIVE_COLLISIONS in entries:
            constraints.append(
                MaxElectiveCollisionsConstraint(
                    entries[Criterion.MAX_ELECTIVE_COLLISIONS],
                    _elective_programs_by_course_id(
                        courses,
                        selected_set,
                        exam_period.semester,
                    ),
                )
            )

        return cls(constraints)

    def allows(self, course: Course, exam_date: date) -> bool:
        return all(
            constraint.allows(course, exam_date)
            for constraint in self._constraints
        )

    def record(self, course: Course, exam_date: date) -> None:
        for constraint in self._constraints:
            constraint.record(course, exam_date)

    def undo(self, course: Course, exam_date: date) -> None:
        for constraint in reversed(self._constraints):
            constraint.undo(course, exam_date)


class MaxExamsPerDayConstraint(PlacementConstraint):
    """Limit the total number of exams placed on any one date."""

    def __init__(self, k: int) -> None:
        self._k = k
        self._day_counts: dict[date, int] = {}

    def allows(self, course: Course, exam_date: date) -> bool:
        return self._day_counts.get(exam_date, 0) < self._k

    def record(self, course: Course, exam_date: date) -> None:
        self._day_counts[exam_date] = self._day_counts.get(exam_date, 0) + 1

    def undo(self, course: Course, exam_date: date) -> None:
        remaining = self._day_counts[exam_date] - 1
        if remaining:
            self._day_counts[exam_date] = remaining
        else:
            del self._day_counts[exam_date]


class MinDaysConstraint(PlacementConstraint):
    """Enforce a minimum gap within each configured program/year group."""

    def __init__(
        self,
        k: int,
        groups_by_course_id: dict[str, tuple[tuple[str, int], ...]],
    ) -> None:
        self._k = k
        self._groups_by_course_id = dict(groups_by_course_id)
        self._date_counts_by_group: dict[tuple[str, int], dict[date, int]] = {}

    def allows(self, course: Course, exam_date: date) -> bool:
        if self._k <= 0:
            return True

        for group in self._groups_by_course_id.get(course.id, ()):
            date_counts = self._date_counts_by_group.get(group, {})
            if any(
                abs((exam_date - placed_date).days) < self._k
                for placed_date in date_counts
            ):
                return False

        return True

    def record(self, course: Course, exam_date: date) -> None:
        for group in self._groups_by_course_id.get(course.id, ()):
            date_counts = self._date_counts_by_group.setdefault(group, {})
            date_counts[exam_date] = date_counts.get(exam_date, 0) + 1

    def undo(self, course: Course, exam_date: date) -> None:
        for group in self._groups_by_course_id.get(course.id, ()):
            date_counts = self._date_counts_by_group[group]
            remaining = date_counts[exam_date] - 1
            if remaining:
                date_counts[exam_date] = remaining
            else:
                del date_counts[exam_date]

            if not date_counts:
                del self._date_counts_by_group[group]


class MaxElectiveCollisionsConstraint(PlacementConstraint):
    """Limit same-day elective collision pairs per program."""

    def __init__(
        self,
        k: int,
        programs_by_course_id: dict[str, tuple[str, ...]],
    ) -> None:
        self._k = k
        self._programs_by_course_id = dict(programs_by_course_id)
        self._date_counts_by_program: dict[str, dict[date, int]] = {}
        self._collisions_by_program: dict[str, int] = {}

    def allows(self, course: Course, exam_date: date) -> bool:
        for program_id in self._programs_by_course_id.get(course.id, ()):
            date_counts = self._date_counts_by_program.get(program_id, {})
            added_collisions = date_counts.get(exam_date, 0)
            current_collisions = self._collisions_by_program.get(program_id, 0)
            if current_collisions + added_collisions > self._k:
                return False

        return True

    def record(self, course: Course, exam_date: date) -> None:
        for program_id in self._programs_by_course_id.get(course.id, ()):
            date_counts = self._date_counts_by_program.setdefault(program_id, {})
            existing_same_day = date_counts.get(exam_date, 0)
            date_counts[exam_date] = existing_same_day + 1

            if existing_same_day:
                self._collisions_by_program[program_id] = (
                    self._collisions_by_program.get(program_id, 0)
                    + existing_same_day
                )

    def undo(self, course: Course, exam_date: date) -> None:
        for program_id in self._programs_by_course_id.get(course.id, ()):
            date_counts = self._date_counts_by_program[program_id]
            remaining_same_day = date_counts[exam_date] - 1

            if remaining_same_day:
                date_counts[exam_date] = remaining_same_day
            else:
                del date_counts[exam_date]

            if remaining_same_day:
                remaining_collisions = (
                    self._collisions_by_program[program_id]
                    - remaining_same_day
                )
                if remaining_collisions:
                    self._collisions_by_program[program_id] = remaining_collisions
                else:
                    del self._collisions_by_program[program_id]

            if not date_counts:
                del self._date_counts_by_program[program_id]


def _groups_by_course_id(
    courses: list[Course],
    selected_programs: set[str],
    semester: str,
    requirement: str | None,
) -> dict[str, tuple[tuple[str, int], ...]]:
    groups_by_course_id: dict[str, tuple[tuple[str, int], ...]] = {}

    for course in courses:
        groups: set[tuple[str, int]] = set()
        for offering in relevant_offerings(course, selected_programs, semester):
            if (
                requirement is not None
                and offering.requirement.strip().lower() != requirement
            ):
                continue
            groups.add((offering.program_id, offering.year))

        groups_by_course_id[course.id] = tuple(sorted(groups))

    return groups_by_course_id


def _elective_programs_by_course_id(
    courses: list[Course],
    selected_programs: set[str],
    semester: str,
) -> dict[str, tuple[str, ...]]:
    programs_by_course_id: dict[str, tuple[str, ...]] = {}

    for course in courses:
        programs = {
            offering.program_id
            for offering in relevant_offerings(course, selected_programs, semester)
            if offering.requirement.strip().lower() == "elective"
        }
        programs_by_course_id[course.id] = tuple(sorted(programs))

    return programs_by_course_id
