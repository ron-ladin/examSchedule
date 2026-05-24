"""
Infrastructure Adapter: TextFileExporter
-----------------------------------------
Implements IOutputExporter by writing schedules to a human-readable text file.

Constructor args:
    - output_path (Path) : path to the output file (e.g. schedules.txt)

Methods to implement:

    export_schedules(
        schedules_by_period: Dict[str, Iterable[Schedule]],
        courses_by_id: Dict[str, Course]
    ) -> None
        Writes generated schedules to output_path.

        Input contract:
            - schedules_by_period: keys are period keys in the format
              "<SEMESTER> - <Moed>" (e.g. "FALL - Aleph", "SPRI - Bet").
              Values are Iterable[Schedule] that must be consumed one at a time
              — do NOT convert to list.
            - courses_by_id: maps course_id (str) → Course. Use this to look up
              the course name and instructor for each assignment.

        Output structure (written to output_path):
            === SEMESTER: FALL ===
            --- Moed: Aleph ---

            Schedule #1:
              - <Course Name> | Course ID: <id> | Date: DD-MM-YYYY | Instructor: <Name>
              - ...

            Schedule #2:
              - ...

            --- Moed: Bet ---
            ...

            === SEMESTER: SPRING ===
            ...

        Rules:
            - Group by Semester first, then by Moed (one header pair per period key).
            - Within each period, number schedules starting from 1.
            - Within each schedule, sort course lines chronologically by exam date.
            - If a period produces zero schedules, write "No valid schedules found."
            - If schedules_by_period is empty, write "No exam periods found."
            - "SPRI" from period keys must appear as "SPRING" in output
              (use display_semester from src.domain.semester).
            - Use f-strings for all line formatting.
            - Use pathlib.Path.open() for file writing — never hardcoded paths.
            - Use logging (logger.info / logger.warning) — no print() calls.
            - Log a warning and skip the line if a course_id is not in courses_by_id.

    _write_period_header(file, semester: str, moed: str) -> None
        Writes the two header lines for one exam period block:
            === SEMESTER: <display_semester(semester)> ===
            --- Moed: <moed> ---

        Followed by a blank line.

    _write_schedule(file, schedule_number: int, schedule: Schedule,
                    courses_by_id: Dict[str, Course]) -> None
        Writes one numbered schedule block:
            Schedule #<n>:
              - <name> | Course ID: <id> | Date: DD-MM-YYYY | Instructor: <name>
              ...
        Courses must be sorted chronologically (earliest exam date first).
        Ends with a blank line.
        Logs a warning (and skips the line) for any course_id not in courses_by_id.

    _split_period_key(period_key: str) -> tuple[str, str]
        Splits a period key string of the form "<SEMESTER> - <Moed>"
        into (semester, moed).
        If the separator " - " is missing, return (period_key, "Unknown").

Notes:
    - Use logging — no print() calls.
    - This exporter receives schedules grouped by period as iterables, so schedules
      can be consumed one by one without loading all schedules into memory at once.
"""

import logging
from itertools import product as cartesian_product
from pathlib import Path
from typing import Dict, List

from src.domain.course import Course
from src.domain.schedule import Schedule
from src.domain.semester import display_semester
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
        logger.info("Writing schedules to %s", self.output_path)

        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        with self.output_path.open("w", encoding="utf-8") as file:
            if not schedules_by_period:
                file.write("No valid schedules found.\n")
                return

            period_keys = list(schedules_by_period.keys())
            schedule_lists = [schedules_by_period[k] for k in period_keys]

            count = 0
            for combo in cartesian_product(*schedule_lists):
                count += 1
                file.write(f"Schedule #{count}:\n")
                for period_key, schedule in zip(period_keys, combo):
                    semester, moed = self._split_period_key(period_key)
                    file.write(f"  [{display_semester(semester)} - {moed}]\n")
                    self._write_schedule(file, schedule, courses_by_id)
                file.write("\n")

            if count == 0:
                file.write("No valid schedules found.\n")

    def _write_schedule(
        self,
        file,
        schedule: Schedule,
        courses_by_id: Dict[str, Course],
    ) -> None:
        sorted_assignments = sorted(schedule.assignments.items(), key=lambda item: item[1])

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
