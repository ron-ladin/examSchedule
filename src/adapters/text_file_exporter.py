"""
Infrastructure Adapter: TextFileExporter
-----------------------------------------
Implements IOutputExporter by writing schedules to a human-readable text file.
"""

import logging
from collections.abc import Iterable
from itertools import islice, product as cartesian_product
from pathlib import Path

from src.domain.course import Course
from src.domain.schedule import Schedule
from src.domain.semester import display_semester
from src.interfaces.i_output_exporter import IOutputExporter


logger = logging.getLogger(__name__)

DEFAULT_MAX_COMBINATIONS: int = 200


class TextFileExporter(IOutputExporter):
    """
    Writes generated schedules to a text file.

    Multiple periods are exported as a Cartesian product:
        period A option 1 + period B option 1
        period A option 1 + period B option 2
        ...

    The default export is capped to prevent accidental huge files or OOM when
    callers pass all generated schedules.
    Pass max_combinations=None only when an uncapped export is intentional.
    """

    def __init__(
        self,
        output_path: Path,
        max_combinations: int | None = DEFAULT_MAX_COMBINATIONS,
    ):
        self.output_path = Path(output_path)
        self.max_combinations = max_combinations

    def export_schedules(
        self,
        schedules_by_period: dict[str, Iterable[Schedule]],
        courses_by_id: dict[str, Course],
    ) -> None:
        logger.info("Writing schedules to %s", self.output_path)

        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        with self.output_path.open("w", encoding="utf-8") as file:
            if not schedules_by_period:
                file.write("No valid schedules found.\n")
                return

            period_keys = list(schedules_by_period.keys())
            schedule_lists, input_truncated = self._collect_schedule_lists(
                schedules_by_period,
                period_keys,
            )

            if any(not schedules for schedules in schedule_lists):
                for key, schedules in zip(period_keys, schedule_lists):
                    if not schedules:
                        logger.warning(
                            "Period '%s' produced no valid schedules; combined output suppressed.",
                            key,
                        )
                file.write("No valid schedules found.\n")
                return

            count = 0
            output_truncated = False

            for combo in cartesian_product(*schedule_lists):
                if (
                    self.max_combinations is not None
                    and count >= self.max_combinations
                ):
                    output_truncated = True
                    break

                count += 1
                file.write(f"Schedule #{count}:\n")

                for period_key, schedule in zip(period_keys, combo):
                    semester, moed = self._split_period_key(period_key)
                    file.write(f"  [{display_semester(semester)} - {moed}]\n")
                    self._write_schedule(file, schedule, courses_by_id)

                file.write("\n")

            if count == 0:
                file.write("No valid schedules found.\n")
            elif input_truncated or output_truncated:
                self._write_truncation_notice(file)

    def _collect_schedule_lists(
        self,
        schedules_by_period: dict[str, Iterable[Schedule]],
        period_keys: list[str],
    ) -> tuple[list[list[Schedule]], bool]:
        """
        Collect schedules into bounded lists.

        itertools.product stores input pools internally, so each period iterable
        must be bounded when max_combinations is set. Otherwise a lazy generator
        could still be fully materialised before the output cap is applied.
        """
        schedule_lists: list[list[Schedule]] = []
        input_truncated = False

        for period_key in period_keys:
            schedules_iter = iter(schedules_by_period[period_key])

            if self.max_combinations is None:
                schedules = list(schedules_iter)
            else:
                schedules = list(islice(schedules_iter, self.max_combinations + 1))
                if len(schedules) > self.max_combinations:
                    input_truncated = True
                    schedules = schedules[: self.max_combinations]

            schedule_lists.append(schedules)

        return schedule_lists, input_truncated

    def _write_truncation_notice(self, file) -> None:
        if self.max_combinations is None:
            return

        logger.warning(
            "Output capped at %d combinations.",
            self.max_combinations,
        )
        file.write(
            f"\n[Output capped at {self.max_combinations} "
            "schedule combinations. There may be more.]\n"
        )

    def _write_schedule(
        self,
        file,
        schedule: Schedule,
        courses_by_id: dict[str, Course],
    ) -> None:
        sorted_assignments = sorted(
            schedule.assignments.items(),
            key=lambda item: item[1],
        )

        for course_id, exam_date in sorted_assignments:
            course = courses_by_id.get(course_id)
            if course is None:
                logger.warning("Course id %s was not found in courses_by_id", course_id)
                continue

            file.write(
                f"  - {course.name} | Course ID: {course.id} | "
                f"Date: {exam_date.strftime('%d-%m-%Y')} | "
                f"Instructor: {course.instructor}\n"
            )

            self._write_course_offerings(file, course)
            self._write_classroom_details(file, schedule, course_id)

    def _write_course_offerings(self, file, course: Course) -> None:
        """
        Persist enough course metadata so a later Load Schedule can reconstruct
        the detail table without requiring the original courses.txt file.

        These lines are intentionally indented under the course line.
        ScheduleFileReader will parse them back into CourseOffering objects.
        """
        for offering in course.offerings:
            students = (
                str(offering.student_count)
                if offering.student_count is not None
                else ""
            )

            file.write(
                f"    Offering: Program: {offering.program_id} | "
                f"Year: {offering.year} | "
                f"Semester: {offering.semester} | "
                f"Requirement: {offering.requirement} | "
                f"Students: {students}\n"
            )

    def _write_classroom_details(
        self,
        file,
        schedule: Schedule,
        course_id: str,
    ) -> None:
        classroom_assignments = schedule.classroom_assignments.get(course_id, [])

        for assignment in classroom_assignments:
            file.write(
                f"    Slot: {assignment.slot.time.strftime('%H:%M')} | "
                f"Room: {assignment.room.room_id} | "
                f"Capacity: {assignment.students_assigned}/{assignment.room.capacity} | "
                f"Proctors: {assignment.proctor_count}\n"
            )

        unassigned_count = schedule.unassigned_classroom_exams.get(course_id)
        if unassigned_count:
            file.write(
                f"    Unassigned classroom students: {unassigned_count}\n"
            )

    def _split_period_key(self, period_key: str) -> tuple[str, str]:
        if " - " not in period_key:
            return period_key, "Unknown"

        semester, moed = period_key.split(" - ", 1)
        return semester.strip(), moed.strip()
