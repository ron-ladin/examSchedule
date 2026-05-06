"""
Unit Tests: FileDataProvider
------------------------------
Tests for parsing logic in FileDataProvider.

Test cases to implement:
    1. Valid courses.txt → correct Course and CourseOffering objects returned.
    2. Missing $$$$ separator in courses.txt → raises appropriate error or skips record.
    3. Wrong date format in exam_periods.txt → raises ValueError.
    4. "SPRI" in semester field → mapped to "SPRING" in CourseOffering.
    5. selected_programs.txt with > 5 programs → raises ValueError.
    6. selected_programs.txt with non-5-digit entry → raises ValueError.
    7. Excluded date range in exam_periods.txt → parsed into excluded_dates set correctly.

Notes:
    - Use tmp_path pytest fixture to create temporary input files.
    - Write minimal valid file content as strings in each test.
    - Import FileDataProvider from src.adapters.file_data_provider.
"""
