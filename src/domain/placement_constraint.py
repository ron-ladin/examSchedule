from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from datetime import date

from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.domain.schedule_metrics import relevant_offerings
from src.domain.threshold import Criterion, ThresholdSettings


class PlacementConstraint(ABC):
    """Stateful, reversible constraint for one partial schedule search."""

    @abstractmethod
    def allows(self, course: Course, exam_date: date) -> bool:
        """Return whether placing ``course`` on ``exam_date`` is still possible."""

    @abstractmethod
    def record(self, course: Course, exam_date: date) -> None:
        """Record a placement that has already been accepted."""

    @abstractmethod
    def undo(self, course: Course, exam_date: date) -> None:
        """Undo a previous ``record`` call for the same placement."""


class PlacementConstraintSet:
    """Composite placement constraint with a null-object empty state."""

    def __init__(self, constraints: Iterable[PlacementConstraint]) -> None:
        self._constraints = list(constraints)

    @property
    def is_empty(self) -> bool:
        """Return True when no placement constraints are active.

        Schedule generation can use this as a fast path to skip all
        constraint-related checks when thresholds are disabled.
        """
        return not self._constraints

    def __bool__(self) -> bool:
        """Return True when at least one placement constraint is active."""
        return bool(self._constraints)

    @classmethod
    def build(
        cls,
        threshold_settings: ThresholdSettings,
        courses: list[Course],
        selected_programs: list[str],
        exam_period: ExamPeriod,
    ) -> "PlacementConstraintSet":
        enabled_entries = {
            entry.criterion: entry.k
            for entry in threshold_settings.entries
            if entry.enabled
        }
        prog_set = set(selected_programs)
        constraints: list[PlacementConstraint] = []

        max_exams_per_day = enabled_entries.get(Criterion.MAX_EXAMS_PER_DAY)
        if max_exams_per_day is not None:
            constraints.append(MaxExamsPerDayConstraint(max_exams_per_day))

        min_days_mandatory = enabled_entries.get(
            Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS
        )
        if min_days_mandatory is not None:
            constraints.append(
                MinDaysConstraint(
                    min_days_mandatory,
                    _groups_by_course_id(
                        courses,
                        prog_set,
                        exam_period.semester,
                        requirement="obligatory",
                    ),
                )
            )

        min_days_any = enabled_entries.get(Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS)
        if min_days_any is not None:
            constraints.append(
                MinDaysConstraint(
                    min_days_any,
                    _groups_by_course_id(courses, prog_set, exam_period.semester),
                )
            )

        max_elective_collisions = enabled_entries.get(
            Criterion.MAX_ELECTIVE_COLLISIONS
        )
        if max_elective_collisions is not None:
            constraints.append(
                MaxElectiveCollisionsConstraint(
                    max_elective_collisions,
                    _elective_programs_by_course_id(
                        courses,
                        prog_set,
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
    """Limit the number of exams assigned to any one calendar date."""

    def __init__(self, max_exams: int) -> None:
        self._max_exams = max_exams
        self._date_counts: dict[date, int] = {}

    def allows(self, course: Course, exam_date: date) -> bool:
        return self._date_counts.get(exam_date, 0) < self._max_exams

    def record(self, course: Course, exam_date: date) -> None:
        self._date_counts[exam_date] = self._date_counts.get(exam_date, 0) + 1

    def undo(self, course: Course, exam_date: date) -> None:
        self._decrement_date(exam_date)

    def _decrement_date(self, exam_date: date) -> None:
        count = self._date_counts[exam_date] - 1
        if count:
            self._date_counts[exam_date] = count
        else:
            del self._date_counts[exam_date]


class MinDaysConstraint(PlacementConstraint):
    """Limit how close exam dates may be inside each program/year group."""

    def __init__(
        self,
        min_days: int,
        groups_by_course_id: Mapping[str, Iterable[tuple[str, int]]],
    ) -> None:
        self._min_days = min_days
        self._groups_by_course_id = {
            course_id: tuple(groups)
            for course_id, groups in groups_by_course_id.items()
        }
        self._date_counts_by_group: dict[tuple[str, int], dict[date, int]] = {}

    def allows(self, course: Course, exam_date: date) -> bool:
        if self._min_days == 0:
            return True

        for group in self._groups_by_course_id.get(course.id, ()):
            for placed_date in self._date_counts_by_group.get(group, {}):
                if abs((exam_date - placed_date).days) < self._min_days:
                    return False
        return True

    def record(self, course: Course, exam_date: date) -> None:
        if self._min_days == 0:
            return

        for group in self._groups_by_course_id.get(course.id, ()):
            date_counts = self._date_counts_by_group.setdefault(group, {})
            date_counts[exam_date] = date_counts.get(exam_date, 0) + 1

    def undo(self, course: Course, exam_date: date) -> None:
        if self._min_days == 0:
            return

        for group in self._groups_by_course_id.get(course.id, ()):
            date_counts = self._date_counts_by_group[group]
            count = date_counts[exam_date] - 1
            if count:
                date_counts[exam_date] = count
                continue

            del date_counts[exam_date]
            if not date_counts:
                del self._date_counts_by_group[group]


class MaxElectiveCollisionsConstraint(PlacementConstraint):
    """Limit same-day elective pairs per program."""

    def __init__(
        self,
        max_collisions: int,
        programs_by_course_id: Mapping[str, Iterable[str]],
    ) -> None:
        self._max_collisions = max_collisions
        self._programs_by_course_id = {
            course_id: tuple(programs)
            for course_id, programs in programs_by_course_id.items()
        }
        self._date_counts_by_program: dict[str, dict[date, int]] = {}
        self._collisions_by_program: dict[str, int] = {}

    def allows(self, course: Course, exam_date: date) -> bool:
        for program_id in self._programs_by_course_id.get(course.id, ()):
            date_counts = self._date_counts_by_program.get(program_id, {})
            same_day_count = date_counts.get(exam_date, 0)
            current_collisions = self._collisions_by_program.get(program_id, 0)
            if current_collisions + same_day_count > self._max_collisions:
                return False
        return True

    def record(self, course: Course, exam_date: date) -> None:
        for program_id in self._programs_by_course_id.get(course.id, ()):
            date_counts = self._date_counts_by_program.setdefault(program_id, {})
            same_day_count = date_counts.get(exam_date, 0)
            if same_day_count:
                self._collisions_by_program[program_id] = (
                    self._collisions_by_program.get(program_id, 0)
                    + same_day_count
                )
            date_counts[exam_date] = same_day_count + 1

    def undo(self, course: Course, exam_date: date) -> None:
        for program_id in self._programs_by_course_id.get(course.id, ()):
            date_counts = self._date_counts_by_program[program_id]
            same_day_count = date_counts[exam_date]

            if same_day_count > 1:
                remaining_collisions = (
                    self._collisions_by_program[program_id]
                    - (same_day_count - 1)
                )
                if remaining_collisions:
                    self._collisions_by_program[program_id] = remaining_collisions
                else:
                    del self._collisions_by_program[program_id]

            if same_day_count > 1:
                date_counts[exam_date] = same_day_count - 1
            else:
                del date_counts[exam_date]

            if not date_counts:
                del self._date_counts_by_program[program_id]


def _groups_by_course_id(
    courses: list[Course],
    prog_set: set[str],
    semester: str,
    requirement: str | None = None,
) -> dict[str, tuple[tuple[str, int], ...]]:
    groups_by_course_id: dict[str, tuple[tuple[str, int], ...]] = {}
    for course in courses:
        groups = set()
        for offering in relevant_offerings(course, prog_set, semester):
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
    prog_set: set[str],
    semester: str,
) -> dict[str, tuple[str, ...]]:
    programs_by_course_id: dict[str, tuple[str, ...]] = {}
    for course in courses:
        programs = {
            offering.program_id
            for offering in relevant_offerings(course, prog_set, semester)
            if offering.requirement.strip().lower() == "elective"
        }
        programs_by_course_id[course.id] = tuple(sorted(programs))
    return programs_by_course_id
