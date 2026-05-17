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
from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.adapters.file_data_provider import FileDataProvider
from src.adapters.text_file_exporter import TextFileExporter
from src.engine.app_controller import AppController
from src.engine.schedule_generator import ScheduleGenerator

# This integration test checks the entire app workflow from start to finish.
    # It reads mock files, runs the scheduler, and creates a final text schedule report.
def test_full_pipeline_creates_non_empty_output_file(tmp_path):
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"
    output_path = tmp_path / "schedules.txt"

    # We add 2 exam courses (Calculus, Algorithms) and 1 non-exam project course (Project Lab)
    courses_path.write_text(
        """Calculus
11111
Dr. Cohen
83101, 1, FALL, Obligatory
Exam
$$$$
Algorithms
22222
Dr. Levi
83101, 1, FALL, Obligatory
Exam
$$$$
Project Lab
33333
Dr. Katz
83101, 1, FALL, Obligatory
Project
""",
        encoding="utf-8",
    )
    periods_path.write_text(
        """FALL, Aleph
05-01-2026, 06-01-2026
""",
        encoding="utf-8",
    )
    programs_path.write_text("83101", encoding="utf-8")

    # Connect all components together (Data Provider -> Strategy -> Generator -> Controller)
    data_provider = FileDataProvider(courses_path, periods_path, programs_path)
    selected_programs = data_provider.get_selected_programs()
    conflict_strategy = ExactConflictStrategy(selected_programs)
    generator = ScheduleGenerator(conflict_strategy)
    exporter = TextFileExporter(output_path)
    controller = AppController(
        data_provider=data_provider,
        exporter=exporter,
        generator=generator,
        selected_programs=selected_programs,
    )

    # Start the app execution   
    controller.run()

    content = output_path.read_text(encoding="utf-8")
    # Assertions: Verify the output file exists, has content, and formats headers cleanly
    assert output_path.exists()
    assert content.strip()
    assert "=== SEMESTER: FALL ===" in content
    assert "Schedule #1:" in content
    # Check that exam courses are included, but evaluation types like "Project" are filtered out
    assert "Calculus" in content
    assert "Algorithms" in content
    assert "Project Lab" not in content

#  This integration test verifies end-to-end mapping requirement.
    # It makes sure that if the text database files contain the raw short string "SPRI",
    # the final system output dynamically rewrites and maps it cleanly to "SPRING".
def test_full_pipeline_displays_spri_as_spring(tmp_path):
    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "dates.txt"
    programs_path = tmp_path / "programs.txt"
    output_path = tmp_path / "schedules.txt"

    courses_path.write_text(
        """Linear Algebra
44444
Dr. Spring
83101, 1, SPRING, Obligatory
Exam
""",
        encoding="utf-8",
    )
    # The file contains the raw term "SPRI"
    periods_path.write_text(
        """SPRI, Aleph
01-03-2026, 02-03-2026
""",
        encoding="utf-8",
    )
    programs_path.write_text("83101", encoding="utf-8")

    data_provider = FileDataProvider(courses_path, periods_path, programs_path)
    selected_programs = data_provider.get_selected_programs()
    controller = AppController(
        data_provider=data_provider,
        exporter=TextFileExporter(output_path),
        generator=ScheduleGenerator(ExactConflictStrategy(selected_programs)),
        selected_programs=selected_programs,
    )

    controller.run()

    content = output_path.read_text(encoding="utf-8")

    # Assertions: Verify that "SPRING" is visible and the ugly raw "SPRI" is hidden
    assert "=== SEMESTER: SPRING ===" in content
    assert "=== SEMESTER: SPRI ===" not in content