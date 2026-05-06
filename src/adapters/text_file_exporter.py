"""
Infrastructure Adapter: TextFileExporter
-----------------------------------------
Implements IOutputExporter by writing schedules to a human-readable text file.

Constructor args:
    - output_path (Path) : path to the output file (e.g. schedules.txt)

Methods to implement:

    export_schedules(schedules: Iterator[Schedule]) -> None
        Consumes the schedule generator and writes to output_path.

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
            - Use itertools.groupby for grouping logic.
            - Use f-strings for all line formatting.
            - Use pathlib.Path.open() for writing — never hardcoded paths.

Notes:
    - Must stream — do NOT collect all schedules into a list before writing.
    - Use logging — no print() calls.
"""

from src.interfaces.i_output_exporter import IOutputExporter


class TextFileExporter(IOutputExporter):
    pass
