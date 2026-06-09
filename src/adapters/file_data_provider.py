"""
Infrastructure Adapter: FileDataProvider
-----------------------------------------
Implements IDataProvider by delegating file reading to three focused readers.

Readers:
    - CourseFileReader
    - ExamPeriodFileReader
    - ProgramSelectorReader

This class is responsible only for adapting those readers to the IDataProvider
interface expected by the rest of the system.
"""

from pathlib import Path
from typing import List

from src.adapters.readers.course_file_reader import CourseFileReader
from src.adapters.readers.exam_period_file_reader import ExamPeriodFileReader
from src.adapters.readers.program_selector_reader import ProgramSelectorReader
from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.interfaces.i_data_provider import IDataProvider


class FileDataProvider(IDataProvider):

    def __init__(
        self,
        courses_path: Path,
        periods_path: Path,
        programs_path: Path,
    ):
        self.course_reader = CourseFileReader(courses_path)
        self.exam_period_reader = ExamPeriodFileReader(periods_path)
        self.program_reader = ProgramSelectorReader(programs_path)

    def get_courses(self) -> List[Course]:
        return self.course_reader.read()

    def get_exam_periods(self) -> List[ExamPeriod]:
        return self.exam_period_reader.read()

    def get_selected_programs(self) -> List[str]:
        return self.program_reader.read()
