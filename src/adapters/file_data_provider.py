"""
Infrastructure Adapter: FileDataProvider
-----------------------------------------
Implements IDataProvider by reading data from text files.

Constructor args:
    - courses_path  (Path) : path to courses.txt
    - periods_path  (Path) : path to exam_periods.txt
    - programs_path (Path) : path to selected_programs.txt

Methods to implement:

    get_courses() -> List[Course]
        Parses courses.txt ($$$$-separated records).
        Each record structure:
            $$$$
            <Course Name>
            <5-digit Course ID>
            <Instructor Name>
            <program_id>,<year>,<semester>,<requirement>  ← one or more lines
            <Evaluation>
        Maps "SPRI" → "SPRING" in semester field before building CourseOffering.
        Returns a list of Course objects with their offerings populated.

    get_exam_periods() -> List[ExamPeriod]
        Parses exam_periods.txt ($$$$-separated records).
        Each record structure:
            $$$$
            <Semester>,<Moed>
            <StartDate>, <EndDate>
            <ExcludedDate or Range> <Optional Comment>
        Uses datetime.strptime() with format "%d-%m-%Y" for all date parsing.
        Excluded entries may be a single date or a "start, end comment" range.

    get_selected_programs() -> List[str]
        Parses selected_programs.txt (comma-separated 5-digit IDs on one line).
        Validates that each entry is exactly 5 digits.
        Raises ValueError if count > 5 or any entry is not a valid program ID.

Notes:
    - Use pathlib.Path for all file access — never os.path.
    - Use logging for warnings (e.g., skipped records) — no print().
    - All parsing logic belongs here, not in domain classes.
"""

from src.interfaces.i_data_provider import IDataProvider


class FileDataProvider(IDataProvider):
    pass
