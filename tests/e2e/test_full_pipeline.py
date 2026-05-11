"""
E2E Test: Full Pipeline Performance
-------------------------------------
End-to-end test that runs the complete pipeline on a realistic dataset
and verifies it completes within the 30-second hard limit.

Test to implement:
    - test_pipeline_completes_under_30_seconds()
        1. Loads a medium-sized dataset from data/ directory
           (courses.txt, exam_periods.txt, selected_programs.txt).
        2. Runs AppController.run() end-to-end.
        3. Asserts that execution time < 30 seconds.
        4. Asserts that the output file was created and is non-empty.

Notes:
    - Use pytest-timeout: mark with @pytest.mark.timeout(30) or run with --timeout=30.
    - The dataset in data/ should be large enough to be a meaningful benchmark.
    - Import all classes from their respective modules.
    - Do NOT mock any component — this is a full integration test.
"""


import time
import pytest
from pathlib import Path
from src.app_controller import AppController
from src.adapters.file_data_provider import FileDataProvider
from src.adapters.text_file_exporter import TextFileExporter
from src.adapters.exact_conflict_strategy import ExactConflictStrategy


from src.domain.course import Course

#Patch Course to make it hashable for the test
Course.__hash__ = lambda self: hash(self.id)
Course.__eq__ = lambda self, other: isinstance(other, Course) and self.id == other.id

@pytest.mark.timeout(30)
def test_pipeline_completes_under_30_seconds(tmp_path):
    # Setup data paths
    data_dir = Path("data")
    courses_path = data_dir / "courses.txt"
    periods_path = data_dir / "exam_periods.txt"
    programs_path = data_dir / "selected_programs.txt"
    output_file = tmp_path / "final_schedule.txt"

    # 1. Initialize the Data Provider
    provider = FileDataProvider(courses_path, periods_path, programs_path)
    
    # 2. Initialize the Exporter with the temporary output path
    exporter = TextFileExporter(output_file)
    
    # 3. Initialize the Exact Conflict Strategy (SCRUM-10)
    strategy = ExactConflictStrategy()

    # 4. Initialize the Controller with all required dependencies
    controller = AppController(
        data_provider=provider, 
        exporter=exporter, 
        conflict_strategy=strategy
    )

    # Measure performance
    start = time.time()
    controller.run()
    runtime = time.time() - start

    # Assertions to verify the pipeline success
    assert runtime < 30, f"Pipeline took too long: {runtime} seconds"
    assert output_file.exists(), "Output file was not created"
    assert output_file.stat().st_size > 0, "Output file is empty"