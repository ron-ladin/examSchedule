import time
from pathlib import Path

import pytest

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.adapters.file_data_provider import FileDataProvider
from src.adapters.text_file_exporter import TextFileExporter
from src.engine.app_controller import AppController


@pytest.mark.timeout(30)
def test_pipeline_completes_under_30_seconds(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    data_dir = project_root / "data"
    output_path = tmp_path / "schedules.txt"

    data_provider = FileDataProvider(
        courses_path=data_dir / "courses.txt",
        periods_path=data_dir / "dates.txt",
        programs_path=data_dir / "programs.txt",
    )
    selected_programs = data_provider.get_selected_programs()
    controller = AppController(
        data_provider=data_provider,
        exporter=TextFileExporter(output_path),
        conflict_strategy=ExactConflictStrategy(selected_programs),
    )

    start = time.perf_counter()
    controller.run()
    elapsed = time.perf_counter() - start

    assert elapsed < 30
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8").strip()
