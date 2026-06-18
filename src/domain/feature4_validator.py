"""
Feature 4 Validator
--------------------
Pure, stateless validation logic for Feature 4 (classroom assignment):
relevance filtering, missing-student-count detection, per-exam student totals,
and the pre-generation capacity-shortfall check (spec 4.1–4.4).

Extracted from DesktopController so the rules can be unit-tested without
constructing the full controller / UI stack. All functions take their inputs
explicitly and never mutate them. DesktopController delegates its Feature 4
methods here.
"""

from __future__ import annotations

from src.domain.classroom import Classroom
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.semester import normalize_semester


class Feature4Validator:
    """Stateless Feature 4 validation rules (spec 4.3/4.4)."""

    @staticmethod
    def relevant_offerings_for_course(
        course: Course,
        selected_programs: list[str],
        exam_periods: list[ExamPeriod],
    ) -> list[CourseOffering]:
        """
        Offerings of an exam course relevant to the current run: selected
        programmes AND the semester of any loaded exam period (spec 4.3/4.4).
        Mirrors ClassroomAssigner.get_relevant_offerings so the pre-generation
        checks and the engine agree on which exams matter.
        """
        semesters = {period.semester for period in exam_periods}
        seen: set[tuple] = set()
        relevant: list[CourseOffering] = []
        for semester in semesters:
            for offering in course.get_relevant_offerings(selected_programs, semester):
                key = (
                    offering.program_id,
                    offering.year,
                    normalize_semester(offering.semester),
                )
                if key not in seen:
                    seen.add(key)
                    relevant.append(offering)
        return relevant

    @staticmethod
    def any_exam_missing_student_count(courses: list[Course]) -> bool:
        """
        True if ANY exam course has an offering without a StudentCount,
        regardless of programme selection (spec 4.3 file-load abort).
        """
        return any(
            offering.student_count is None
            for course in courses
            if course.has_exam()
            for offering in course.offerings
        )

    @classmethod
    def missing_student_counts(
        cls,
        courses: list[Course],
        selected_programs: list[str],
        exam_periods: list[ExamPeriod],
    ) -> bool:
        """
        True if any *relevant* exam offering lacks a StudentCount (spec 4.3).

        When no programmes are selected yet, relevance cannot be determined, so
        fall back to the unfiltered check — otherwise the warning would be
        vacuously suppressed and the engine would raise at generate time.
        """
        if not selected_programs:
            return cls.any_exam_missing_student_count(courses)
        return any(
            offering.student_count is None
            for course in courses
            if course.has_exam()
            for offering in cls.relevant_offerings_for_course(
                course, selected_programs, exam_periods
            )
        )

    @classmethod
    def exam_student_totals(
        cls,
        courses: list[Course],
        selected_programs: list[str],
        exam_periods: list[ExamPeriod],
    ) -> dict[tuple[str, str], int]:
        """
        Total students per exam instance (spec 4.3/4.4): for each "Exam" course,
        sum the StudentCount across only its *relevant* program lines, grouped by
        semester. Offerings from different semesters are distinct exams and must
        NOT be summed together. Keyed by (course id, normalized semester).
        Courses with no relevant offering are excluded; missing counts are zero.
        """
        totals: dict[tuple[str, str], int] = {}
        for course in courses:
            if not course.has_exam():
                continue
            for offering in cls.relevant_offerings_for_course(
                course, selected_programs, exam_periods
            ):
                key = (course.id, normalize_semester(offering.semester))
                totals[key] = totals.get(key, 0) + (offering.student_count or 0)
        return totals

    @classmethod
    def capacity_shortfall(
        cls,
        courses: list[Course],
        selected_programs: list[str],
        exam_periods: list[ExamPeriod],
        classrooms: list[Classroom],
        is_active: bool,
    ) -> tuple[int, int] | None:
        """
        Pre-generation capacity warning (spec 4.4).

        Returns (total classroom capacity, largest single-exam student count)
        when total capacity of ALL rooms is less than the StudentCount of ANY
        single exam — the binding constraint is the largest single exam, not the
        sum. Returns None when Feature 4 is inactive or capacity suffices.
        """
        if not is_active:
            return None

        exam_totals = cls.exam_student_totals(courses, selected_programs, exam_periods)
        if not exam_totals:
            return None

        total_capacity = sum(room.capacity for room in classrooms)
        largest_exam = max(exam_totals.values())

        if total_capacity < largest_exam:
            return total_capacity, largest_exam
        return None
