"""
Unit Tests: ThresholdFilter  (SCRUM-282)
-----------------------------------------
TDD tests for ThresholdFilter.is_valid(schedule, courses, settings) based on
sprint3_source_of_truth.md sections 2.1–2.5.

The class is expected to live at:
    src.domain.threshold_filter.ThresholdFilter

Public contract assumed:
    ThresholdFilter.is_valid(
        schedule: Schedule,
        courses: List[Course],
        settings: ThresholdSettings,
    ) -> bool

All criteria are applied only when their ThresholdEntry.enabled is True.
"""

import pytest
from datetime import date

from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.domain.threshold import Criterion, ThresholdEntry, ThresholdSettings
from src.domain.threshold_filter import ThresholdFilter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROGRAM_A = "83101"
PROGRAM_B = "83102"
SEMESTER = "FALL"

BASE_PERIOD = ExamPeriod(
    semester=SEMESTER,
    moed="Aleph",
    date_ranges=[(date(2026, 1, 4), date(2026, 1, 31))],
)


def _offering(program: str, year: int, requirement: str) -> CourseOffering:
    return CourseOffering(
        program_id=program, year=year, semester=SEMESTER, requirement=requirement
    )


def _mandatory(course_id: str, program: str = PROGRAM_A, year: int = 1) -> Course:
    c = Course(
        id=course_id,
        name=f"Course {course_id}",
        instructor="Prof. X",
        evaluation_type="Exam",
    )
    c.add_offering(_offering(program, year, "Obligatory"))
    return c


def _elective(course_id: str, program: str = PROGRAM_A, year: int = 1) -> Course:
    c = Course(
        id=course_id,
        name=f"Elective {course_id}",
        instructor="Prof. Y",
        evaluation_type="Exam",
    )
    c.add_offering(_offering(program, year, "Elective"))
    return c


def _settings_only(criterion: Criterion, k: int, enabled: bool = True) -> ThresholdSettings:
    """Build a ThresholdSettings with exactly one active entry."""
    return ThresholdSettings(
        entries=(ThresholdEntry(criterion=criterion, enabled=enabled, k=k),)
    )


def _schedule(assignments: dict) -> Schedule:
    return Schedule(period=BASE_PERIOD, assignments=assignments)


# ---------------------------------------------------------------------------
# 2.1  MIN_DAYS_BETWEEN_MANDATORY_EXAMS
# ---------------------------------------------------------------------------

class TestMinDaysBetweenMandatoryExams:
    """Criterion 2.1: gap between mandatory course exams (same program, same year)."""

    CRITERION = Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS

    @pytest.mark.parametrize(
        "second_date, k, expected",
        [
            (date(2026, 1, 8), 3, True),   # gap == k
            (date(2026, 1, 12), 3, True),  # gap > k
            (date(2026, 1, 7), 3, False),  # gap < k
        ],
    )
    def test_gap_against_threshold(self, second_date, k, expected):
        courses = [_mandatory("11111"), _mandatory("22222")]
        schedule = _schedule({"11111": date(2026, 1, 5), "22222": second_date})
        settings = _settings_only(self.CRITERION, k=k)
        assert ThresholdFilter.is_valid(schedule, courses, settings) is expected

    def test_same_day_fails_when_k_is_1(self):
        courses = [_mandatory("11111"), _mandatory("22222")]
        schedule = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 5)})
        settings = _settings_only(self.CRITERION, k=1)
        assert ThresholdFilter.is_valid(schedule, courses, settings) is False

    def test_different_programs_not_compared(self):
        """Courses from different programs are not compared against each other."""
        c1 = _mandatory("11111", program=PROGRAM_A)
        c2 = _mandatory("22222", program=PROGRAM_B)
        schedule = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 5)})
        settings = _settings_only(self.CRITERION, k=5)
        assert ThresholdFilter.is_valid(schedule, [c1, c2], settings) is True

    def test_different_years_not_compared(self):
        """Year-1 vs year-2 within same program are not compared."""
        c1 = _mandatory("11111", program=PROGRAM_A, year=1)
        c2 = _mandatory("22222", program=PROGRAM_A, year=2)
        schedule = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 5)})
        settings = _settings_only(self.CRITERION, k=5)
        assert ThresholdFilter.is_valid(schedule, [c1, c2], settings) is True

    def test_elective_courses_are_ignored(self):
        """Criterion 2.1 only applies to mandatory (Obligatory) courses."""
        c1 = _mandatory("11111")
        c2 = _elective("22222")
        schedule = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 5)})
        settings = _settings_only(self.CRITERION, k=5)
        assert ThresholdFilter.is_valid(schedule, [c1, c2], settings) is True


# ---------------------------------------------------------------------------
# 2.2  MIN_DAYS_BETWEEN_ANY_EXAMS
# ---------------------------------------------------------------------------

class TestMinDaysBetweenAnyExams:
    """Criterion 2.2: gap between ANY two exams (same program, same year)."""

    CRITERION = Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS

    def test_passes_when_gap_equals_k(self):
        courses = [_mandatory("11111"), _elective("22222")]
        schedule = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 8)})
        settings = _settings_only(self.CRITERION, k=3)
        assert ThresholdFilter.is_valid(schedule, courses, settings) is True

    @pytest.mark.parametrize(
        "courses_factory",
        [
            pytest.param(
                lambda: [_mandatory("11111"), _elective("22222")],
                id="elective_too_close_to_mandatory",
            ),
            pytest.param(
                lambda: [_elective("11111"), _elective("22222")],
                id="two_electives_too_close",
            ),
        ],
    )
    def test_fails_when_any_pair_too_close(self, courses_factory):
        courses = courses_factory()
        schedule = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 6)})
        settings = _settings_only(self.CRITERION, k=3)
        assert ThresholdFilter.is_valid(schedule, courses, settings) is False

    def test_different_programs_not_compared(self):
        c1 = _elective("11111", program=PROGRAM_A)
        c2 = _elective("22222", program=PROGRAM_B)
        schedule = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 5)})
        settings = _settings_only(self.CRITERION, k=7)
        assert ThresholdFilter.is_valid(schedule, [c1, c2], settings) is True


# ---------------------------------------------------------------------------
# 2.3  MAX_ELECTIVE_COLLISIONS  (k is non-negative; k=0 means none allowed)
# ---------------------------------------------------------------------------

class TestMaxElectiveCollisions:
    """Criterion 2.3: number of same-day elective-elective pairs (same program)."""

    CRITERION = Criterion.MAX_ELECTIVE_COLLISIONS

    def test_passes_when_collision_count_equals_k(self):
        # Two electives on the same day = 1 collision; k=1 → pass
        courses = [_elective("11111"), _elective("22222")]
        schedule = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 5)})
        settings = _settings_only(self.CRITERION, k=1)
        assert ThresholdFilter.is_valid(schedule, courses, settings) is True

    def test_fails_when_collision_count_exceeds_k(self):
        # Two electives on the same day = 1 collision; k=0 → fail
        courses = [_elective("11111"), _elective("22222")]
        schedule = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 5)})
        settings = _settings_only(self.CRITERION, k=0)
        assert ThresholdFilter.is_valid(schedule, courses, settings) is False

    def test_mandatory_elective_collision_not_counted(self):
        """Criterion 2.3 only counts elective-elective pairs, not mandatory-elective."""
        courses = [_mandatory("11111"), _elective("22222")]
        schedule = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 5)})
        settings = _settings_only(self.CRITERION, k=0)
        assert ThresholdFilter.is_valid(schedule, courses, settings) is True

    def test_k_zero_no_elective_collision_passes(self):
        courses = [_elective("11111"), _elective("22222")]
        schedule = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 6)})
        settings = _settings_only(self.CRITERION, k=0)
        assert ThresholdFilter.is_valid(schedule, courses, settings) is True

    def test_multiple_electives_same_day_counts_pairs(self):
        """3 electives on the same day → 3 pairs; k=2 → fail."""
        courses = [_elective("11111"), _elective("22222"), _elective("33333")]
        schedule = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 5),
            "33333": date(2026, 1, 5),
        })
        settings = _settings_only(self.CRITERION, k=2)
        assert ThresholdFilter.is_valid(schedule, courses, settings) is False

    def test_different_programs_not_compared(self):
        c1 = _elective("11111", program=PROGRAM_A)
        c2 = _elective("22222", program=PROGRAM_B)
        schedule = _schedule({"11111": date(2026, 1, 5), "22222": date(2026, 1, 5)})
        settings = _settings_only(self.CRITERION, k=0)
        assert ThresholdFilter.is_valid(schedule, [c1, c2], settings) is True


# ---------------------------------------------------------------------------
# 2.4  MIN_DAYS_EXAM_PERIOD_SPREAD
# ---------------------------------------------------------------------------

class TestMinDaysExamPeriodSpread:
    """Criterion 2.4: gap between first and last mandatory exam (same program, year, term)."""

    CRITERION = Criterion.MIN_DAYS_EXAM_PERIOD_SPREAD

    def test_passes_when_spread_equals_k(self):
        courses = [
            _mandatory("11111"), _mandatory("22222"), _mandatory("33333"),
        ]
        schedule = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 10),
            "33333": date(2026, 1, 12),
        })
        # spread = 12 - 5 = 7 days; k=7 → pass
        settings = _settings_only(self.CRITERION, k=7)
        assert ThresholdFilter.is_valid(schedule, courses, settings) is True

    def test_fails_when_spread_below_k(self):
        courses = [_mandatory("11111"), _mandatory("22222")]
        schedule = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 7),
        })
        settings = _settings_only(self.CRITERION, k=10)
        assert ThresholdFilter.is_valid(schedule, courses, settings) is False

    def test_single_mandatory_exam_spread_zero_fails_k1(self):
        """A single mandatory exam has a spread of 0; k=1 should fail."""
        courses = [_mandatory("11111")]
        schedule = _schedule({"11111": date(2026, 1, 5)})
        settings = _settings_only(self.CRITERION, k=1)
        assert ThresholdFilter.is_valid(schedule, courses, settings) is False

    def test_electives_not_counted_in_spread(self):
        """Spread is only first-to-last mandatory; electives are ignored."""
        mandatory = _mandatory("11111")
        elective = _elective("22222")
        # Only one mandatory on Jan 5 → spread = 0; k=3 → fail
        schedule = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 20),
        })
        settings = _settings_only(self.CRITERION, k=3)
        assert ThresholdFilter.is_valid(schedule, [mandatory, elective], settings) is False


# ---------------------------------------------------------------------------
# 2.5  MAX_EXAMS_PER_DAY
# ---------------------------------------------------------------------------

class TestMaxExamsPerDay:
    """Criterion 2.5: maximum number of exams on the same day (global)."""

    CRITERION = Criterion.MAX_EXAMS_PER_DAY

    def test_passes_when_day_count_equals_k(self):
        courses = [_mandatory("11111"), _mandatory("22222")]
        schedule = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 5),
        })
        settings = _settings_only(self.CRITERION, k=2)
        assert ThresholdFilter.is_valid(schedule, courses, settings) is True

    def test_fails_when_day_count_exceeds_k(self):
        courses = [_mandatory("11111"), _mandatory("22222"), _mandatory("33333")]
        schedule = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 5),
            "33333": date(2026, 1, 5),
        })
        settings = _settings_only(self.CRITERION, k=2)
        assert ThresholdFilter.is_valid(schedule, courses, settings) is False

    def test_courses_on_different_days_each_within_k(self):
        courses = [_mandatory("11111"), _mandatory("22222"), _mandatory("33333")]
        schedule = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 6),
            "33333": date(2026, 1, 7),
        })
        settings = _settings_only(self.CRITERION, k=1)
        assert ThresholdFilter.is_valid(schedule, courses, settings) is True

    def test_electives_and_mandatories_counted_together(self):
        """Criterion 2.5 is global — all exams on the same day count."""
        courses = [_mandatory("11111"), _elective("22222")]
        schedule = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 5),
        })
        settings = _settings_only(self.CRITERION, k=1)
        assert ThresholdFilter.is_valid(schedule, courses, settings) is False


# ---------------------------------------------------------------------------
# Disabled criteria never affect validation (was repeated per-criterion class)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "criterion, k, courses, assignments",
    [
        pytest.param(
            Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS, 5,
            [_mandatory("11111"), _mandatory("22222")],
            {"11111": date(2026, 1, 5), "22222": date(2026, 1, 5)},
            id="min_days_between_mandatory",
        ),
        pytest.param(
            Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS, 5,
            [_mandatory("11111"), _elective("22222")],
            {"11111": date(2026, 1, 5), "22222": date(2026, 1, 6)},
            id="min_days_between_any",
        ),
        pytest.param(
            Criterion.MAX_ELECTIVE_COLLISIONS, 0,
            [_elective("11111"), _elective("22222")],
            {"11111": date(2026, 1, 5), "22222": date(2026, 1, 5)},
            id="max_elective_collisions",
        ),
        pytest.param(
            Criterion.MIN_DAYS_EXAM_PERIOD_SPREAD, 30,
            [_mandatory("11111"), _mandatory("22222")],
            {"11111": date(2026, 1, 5), "22222": date(2026, 1, 6)},
            id="min_days_exam_period_spread",
        ),
        pytest.param(
            Criterion.MAX_EXAMS_PER_DAY, 1,
            [_mandatory("11111"), _mandatory("22222"), _mandatory("33333")],
            {
                "11111": date(2026, 1, 5),
                "22222": date(2026, 1, 5),
                "33333": date(2026, 1, 5),
            },
            id="max_exams_per_day",
        ),
    ],
)
def test_disabled_criterion_always_passes(criterion, k, courses, assignments):
    """A disabled entry must pass even on data that would violate it when enabled."""
    schedule = _schedule(assignments)
    settings = _settings_only(criterion, k=k, enabled=False)
    assert ThresholdFilter.is_valid(schedule, courses, settings) is True


# ---------------------------------------------------------------------------
# Multiple criteria active simultaneously
# ---------------------------------------------------------------------------

class TestMultipleCriteriaActive:
    """All active criteria must pass for is_valid to return True."""

    def test_all_criteria_pass(self):
        courses = [_mandatory("11111"), _mandatory("22222"), _elective("33333")]
        schedule = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 12),
            "33333": date(2026, 1, 19),
        })
        settings = ThresholdSettings(
            entries=(
                ThresholdEntry(Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS, enabled=True, k=5),
                ThresholdEntry(Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS, enabled=True, k=5),
                ThresholdEntry(Criterion.MAX_ELECTIVE_COLLISIONS, enabled=True, k=0),
                ThresholdEntry(Criterion.MIN_DAYS_EXAM_PERIOD_SPREAD, enabled=True, k=5),
                ThresholdEntry(Criterion.MAX_EXAMS_PER_DAY, enabled=True, k=2),
            )
        )
        assert ThresholdFilter.is_valid(schedule, courses, settings) is True

    def test_one_failing_criterion_invalidates_schedule(self):
        courses = [_mandatory("11111"), _mandatory("22222")]
        schedule = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 5),  # same day → violates 2.1
        })
        settings = ThresholdSettings(
            entries=(
                ThresholdEntry(Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS, enabled=True, k=3),
                ThresholdEntry(Criterion.MAX_EXAMS_PER_DAY, enabled=True, k=3),
            )
        )
        assert ThresholdFilter.is_valid(schedule, courses, settings) is False

    def test_empty_settings_always_passes(self):
        courses = [_mandatory("11111"), _mandatory("22222")]
        schedule = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 5),
        })
        assert ThresholdFilter.is_valid(schedule, courses, ThresholdSettings()) is True

    def test_unassigned_courses_do_not_affect_threshold_validation(self):
        """Courses not assigned in a schedule must not affect threshold checks."""
        c1 = _mandatory("11111")
        c2 = _mandatory("22222")
        unrelated = _mandatory("99999")

        schedule = _schedule({
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 10),
        })

        settings = _settings_only(
            Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS,
            k=5,
        )

        assert ThresholdFilter.is_valid(
            schedule,
            [c1, c2, unrelated],
            settings,
        ) is True


# ---------------------------------------------------------------------------
# Regression: selected_programs isolation
# ---------------------------------------------------------------------------

class TestSelectedProgramsIsolation:
    """Offerings from unselected programs must not influence threshold metrics."""

    def _cross_listed(self, course_id: str, selected_prog: str, other_prog: str) -> Course:
        """Course with one offering in each of two programmes."""
        c = Course(
            id=course_id,
            name=f"Course {course_id}",
            instructor="Prof. X",
            evaluation_type="Exam",
        )
        c.add_offering(_offering(selected_prog, 1, "Obligatory"))
        c.add_offering(_offering(other_prog, 1, "Obligatory"))
        return c

    @pytest.mark.parametrize(
        "second_date, expected",
        [
            (date(2026, 1, 8), True),   # gap=3 → pass; unselected offering must not inflate groups
            (date(2026, 1, 6), False),  # gap=1 → fail; unselected offering must not hide failure
        ],
    )
    def test_unselected_offering_does_not_change_outcome(self, second_date, expected):
        course_a = self._cross_listed("11111", PROGRAM_A, PROGRAM_B)
        course_b = _mandatory("22222", program=PROGRAM_A, year=1)

        schedule = _schedule({
            "11111": date(2026, 1, 5),
            "22222": second_date,
        })
        settings = _settings_only(Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS, k=3)

        assert ThresholdFilter.is_valid(
            schedule, [course_a, course_b], settings, selected_programs=[PROGRAM_A]
        ) is expected


# ---------------------------------------------------------------------------
# Regression: schedule-period semester isolation
# ---------------------------------------------------------------------------

class TestSchedulePeriodSemesterIsolation:
    """Offerings from another semester must not influence Feature 3 thresholds."""

    def test_cross_semester_offering_does_not_create_fake_duplicate_exam(self):
        course = Course(
            id="55555",
            name="Cross Semester Course",
            instructor="Prof. Z",
            evaluation_type="Exam",
        )
        course.add_offering(
            CourseOffering(PROGRAM_A, 1, "FALL", "Obligatory")
        )
        course.add_offering(
            CourseOffering(PROGRAM_A, 1, "SPRI", "Obligatory")
        )

        schedule = _schedule({"55555": date(2026, 1, 5)})
        settings = _settings_only(Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS, k=1)

        assert ThresholdFilter.is_valid(
            schedule,
            [course],
            settings,
            selected_programs=[PROGRAM_A],
        ) is True
