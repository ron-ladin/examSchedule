"""
Infrastructure Adapter: TextFileExporter
-----------------------------------------
Implements IOutputExporter by writing schedules to a human-readable text file.

Constructor args:
    - output_path (Path) : path to the output file (e.g. schedules.txt)

Methods to implement:

    export_schedules(
        schedules_by_period: Dict[str, List[Schedule]],
        courses_by_id: Dict[str, Course]
    ) -> None
        Writes generated schedules to output_path.

        Output structure:
            === SEMESTER: FALL ===
            --- Moed: Aleph ---
            Schedule #1:
              - <Course Name> | Date: DD-MM-YYYY | Instructor: <Name>
              - ...

            --- Moed: Bet ---
            Schedule #1:
              ...

            === SEMESTER: SPRING ===
            ...

        Rules:
            - Group by Semester first, then by Moed.
            - Within each moed, number schedules starting from #1.
            - Within each schedule, sort courses chronologically by exam date.
            - "SPRI" from domain data must appear as "SPRING" in output.
            - Use f-strings for all line formatting.
            - Use pathlib.Path.open() for writing — never hardcoded paths.

Notes:
    - Use logging — no print() calls.
    - This exporter receives schedules already grouped by period from the application layer.
"""

from pathlib import Path
from typing import Dict, List

import logging

from src.domain.course import Course
from src.domain.schedule import Schedule
from src.interfaces.i_output_exporter import IOutputExporter


logger = logging.getLogger(__name__)


class TextFileExporter(IOutputExporter):

    def __init__(self, output_path: Path):
        self.output_path = Path(output_path)

    def export_schedules(
        self,
        schedules_by_period: Dict[str, List[Schedule]],
        courses_by_id: Dict[str, Course],
    ) -> None:
        logger.info("Writing schedules output to %s", self.output_path)

        with self.output_path.open("w", encoding="utf-8") as file:
            if not schedules_by_period:
                file.write("No exam periods found.\n")
                return

            for period_key, schedules in schedules_by_period.items():
                semester, moed = self._split_period_key(period_key)

                self._write_period_header(
                    file=file,
                    semester=semester,
                    moed=moed,
                    schedules_count=len(schedules),
                )

                if not schedules:
                    file.write("No valid schedules found.\n\n")
                    continue

                for schedule_number, schedule in enumerate(schedules, start=1):
                    self._write_schedule(
                        file=file,
                        schedule_number=schedule_number,
                        schedule=schedule,
                        courses_by_id=courses_by_id,
                    )

    def _write_period_header(
        self,
        file,
        semester: str,
        moed: str,
        schedules_count: int,
    ) -> None:
        display_semester = self._display_semester(semester)

        file.write(f"=== SEMESTER: {display_semester} ===\n")
        file.write(f"--- Moed: {moed} ---\n")
        file.write(f"Total schedules found: {schedules_count}\n\n")

    def _write_schedule(
        self,
        file,
        schedule_number: int,
        schedule: Schedule,
        courses_by_id: Dict[str, Course],
    ) -> None:
        file.write(f"Schedule #{schedule_number}:\n")

        sorted_assignments = sorted(
            schedule.assignments.items(),
            key=lambda item: item[1],
        )

        for course_id, exam_date in sorted_assignments:
            course = courses_by_id[course_id]

            file.write(
                f"  - {course.name} | "
                f"Course ID: {course.id} | "
                f"Date: {exam_date.strftime('%d-%m-%Y')} | "
                f"Instructor: {course.instructor}\n"
            )

        file.write("\n")

    def _split_period_key(self, period_key: str) -> tuple[str, str]:
        if " - " not in period_key:
            return period_key, "Unknown"

        semester, moed = period_key.split(" - ", 1)
        return semester.strip(), moed.strip()

    def _display_semester(self, semester: str) -> str:
        semester_names = {
            "FALL": "FALL",
            "SPRI": "SPRING",
            "SUMM": "SUMMER",
        }

        return semester_names.get(semester, semester)