"""
Infrastructure Adapter: TextFileExporter
-----------------------------------------
Implements IOutputExporter by writing schedules to a human-readable text file.
"""

import logging
from itertools import product as cartesian_product
from pathlib import Path
from typing import Iterable

from src.domain.course import Course
from src.domain.schedule import Schedule
from src.domain.semester import display_semester
from src.interfaces.i_output_exporter import IOutputExporter


logger = logging.getLogger(__name__)


class TextFileExporter(IOutputExporter):
    """
    Writes generated schedules to a text file.

    Multiple periods are exported as a Cartesian product:
        period A option 1 + period B option 1
        period A option 1 + period B option 2
        ...

    By default, export is not capped. A cap may be supplied through
    max_combinations if a caller wants to limit very large output files.
    """

    def __init__(self, output_path: Path, max_combinations: int | None = None):
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
            schedule_lists = [list(schedules_by_period[key]) for key in period_keys]

            if any(not schedules for schedules in schedule_lists):
                file.write("No valid schedules found.\n")
                return

            count = 0
            truncated = False

            for combo in cartesian_product(*schedule_lists):
                if (
                    self.max_combinations is not None
                    and count >= self.max_combinations
                ):
                    truncated = True
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
            elif truncated:
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

    def _split_period_key(self, period_key: str) -> tuple[str, str]:
        if " - " not in period_key:
            return period_key, "Unknown"

        semester, moed = period_key.split(" - ", 1)
        return semester.strip(), moed.strip()
