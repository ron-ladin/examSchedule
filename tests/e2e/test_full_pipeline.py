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
