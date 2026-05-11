import pytest
from pathlib import Path
from src.adapters.file_data_provider import FileDataProvider

def test_provider_missing_separator_error(tmp_path):
    """
    This test checks if the system handles a malformed file 
    (missing the $$$$ separator) without crashing.
    """
    # 1. Create a "broken" courses file
    courses_file = tmp_path / "broken_courses.txt"
    periods_file = tmp_path / "periods.txt"
    programs_file = tmp_path / "programs.txt"

    # We write a course but "forget" to add $$$$ at the end
    courses_file.write_text("Course Name\n12345\nInstructor\nProgram,1,A,Obligatory\nExam")
    periods_file.write_text("FALL,A\n01-01-2025,31-01-2025\n$$$$")
    programs_file.write_text("12345")

    # 2. Initialize the provider with the broken file
    provider = FileDataProvider(courses_file, periods_file, programs_file)

    # 3. We expect the system to raise an error instead of returning partial data
    with pytest.raises((ValueError, IndexError, StopIteration)):
        provider.get_courses()