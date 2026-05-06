"""
Unit Tests: FileDataProvider
------------------------------
Tests for parsing logic in FileDataProvider.

Test cases to implement:
    1. Valid courses.txt                        -> correct Course objects returned.
    2. Missing $$$$ separator                   -> raises error or skips record.
    3. Wrong date format in exam_periods.txt    -> raises ValueError.
    4. "SPRI" in semester field                 -> mapped to "SPRING".
    5. More than 5 programs in programs file    -> raises ValueError.
    6. Non-5-digit entry in programs file       -> raises ValueError.
    7. Excluded date range in periods file      -> parsed into excluded_dates correctly.

Notes:
    - Use tmp_path pytest fixture to create temporary input files.
    - Write minimal valid file content as strings in each test.
    - Import FileDataProvider from src.adapters.file_data_provider.
"""
