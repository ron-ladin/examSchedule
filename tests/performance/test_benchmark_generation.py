import os

import pytest

if os.environ.get("RUN_PERFORMANCE") != "1":
    pytest.skip(
        "Set RUN_PERFORMANCE=1 to run manual benchmark validation.",
        allow_module_level=True,
    )

pytestmark = pytest.mark.performance


def test_manual_generation_benchmarks_run():
    from scripts.benchmark_generation import DEFAULT_BENCHMARK_BATCH_SIZE, _cases, run_case

    rows = [run_case(case, DEFAULT_BENCHMARK_BATCH_SIZE) for case in _cases()]

    assert rows
    assert all(row["generation_seconds"] >= 0 for row in rows)
    assert all(row["sqlite_rows"] == row["stored"] for row in rows)
