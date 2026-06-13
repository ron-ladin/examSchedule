"""
Unit Tests: SettingsFileReader (THRESHOLD + SORT — SCRUM-275 / SCRUM-276)
------------------------------------------------------------------------
A focused suite with a few checks of each kind: sanity, edge, negative,
and boundary. Uses the tmp_path fixture to write a temporary settings file.
"""

import pytest

from src.adapters.readers.settings_file_reader import SettingsFileReader
from src.domain import Criterion, SortCriterion


# Helper: write settings content to a temp file and return its path.
def _write(tmp_path, content):
    path = tmp_path / "settings.txt"
    path.write_text(content, encoding="utf-8")
    return path


# A known-good file: THRESHOLD (ON/OFF + the k>=0 elective case) plus a SORT block.
VALID_SETTINGS = """THRESHOLD
MIN_DAYS_BETWEEN_MANDATORY_EXAMS, ON, 3
MIN_DAYS_BETWEEN_ANY_EXAMS, OFF, 1
MAX_ELECTIVE_COLLISIONS, ON, 0
MIN_DAYS_EXAM_PERIOD_SPREAD, ON, 2
MAX_EXAMS_PER_DAY, ON, 2
SORT
1, SORT_MAX_EXAMS_PER_DAY
2, SORT_MIN_DAYS_MANDATORY
"""


# --- Sanity checks ---------------------------------------------------------

# A valid file yields one entry per THRESHOLD line and priority-ordered sort rules.
def test_reads_threshold_and_sort(tmp_path):
    settings = SettingsFileReader(_write(tmp_path, VALID_SETTINGS)).read()

    assert len(settings.thresholds.entries) == 5
    mandatory = settings.thresholds.for_criterion(
        Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS
    )
    assert mandatory is not None
    assert mandatory.enabled is True
    assert mandatory.k == 3
    assert settings.sorting.criteria_in_order() == [
        SortCriterion.SORT_MAX_EXAMS_PER_DAY,
        SortCriterion.SORT_MIN_DAYS_MANDATORY,
    ]


# An OFF criterion is parsed as disabled.
def test_off_entry_disabled(tmp_path):
    settings = SettingsFileReader(_write(tmp_path, VALID_SETTINGS)).read()
    entry = settings.thresholds.for_criterion(Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS)
    assert entry is not None
    assert entry.enabled is False


# --- Edge cases ------------------------------------------------------------

# Headers, criterion names, ON/OFF tokens are case-insensitive; whitespace is trimmed.
def test_case_insensitive_and_whitespace(tmp_path):
    settings = SettingsFileReader(
        _write(tmp_path, "threshold\n  max_exams_per_day ,  on , 2 \n")
    ).read()
    entry = settings.thresholds.for_criterion(Criterion.MAX_EXAMS_PER_DAY)
    assert entry is not None
    assert entry.enabled is True


# The SORT block is optional: a threshold-only file yields no sort rules.
def test_sort_block_optional(tmp_path):
    settings = SettingsFileReader(
        _write(tmp_path, "THRESHOLD\nMAX_EXAMS_PER_DAY, ON, 2\n")
    ).read()
    assert settings.sorting.rules == []


# Sort rules are ordered by priority, not by their order in the file.
def test_sort_ordered_by_priority(tmp_path):
    content = (
        "THRESHOLD\nMAX_EXAMS_PER_DAY, ON, 2\n"
        "SORT\n2, SORT_MIN_DAYS_MANDATORY\n1, SORT_AVG_DAYS_ANY\n"
    )
    settings = SettingsFileReader(_write(tmp_path, content)).read()
    assert settings.sorting.criteria_in_order()[0] == SortCriterion.SORT_AVG_DAYS_ANY


# --- Negative checks -------------------------------------------------------

# An unknown threshold criterion is rejected.
def test_rejects_unknown_criterion(tmp_path):
    with pytest.raises(ValueError):
        SettingsFileReader(_write(tmp_path, "THRESHOLD\nNOPE, ON, 2\n")).read()


# An invalid ON/OFF token is rejected.
def test_rejects_invalid_toggle(tmp_path):
    with pytest.raises(ValueError):
        SettingsFileReader(
            _write(tmp_path, "THRESHOLD\nMAX_EXAMS_PER_DAY, MAYBE, 2\n")
        ).read()


# A non-integer k is rejected.
def test_rejects_non_integer_k(tmp_path):
    with pytest.raises(ValueError):
        SettingsFileReader(
            _write(tmp_path, "THRESHOLD\nMAX_EXAMS_PER_DAY, ON, two\n")
        ).read()


# A wrong field count on a THRESHOLD line is rejected.
def test_rejects_wrong_field_count(tmp_path):
    with pytest.raises(ValueError):
        SettingsFileReader(
            _write(tmp_path, "THRESHOLD\nMAX_EXAMS_PER_DAY, ON\n")
        ).read()


# A file missing the required THRESHOLD block is rejected.
def test_rejects_missing_threshold_block(tmp_path):
    with pytest.raises(ValueError):
        SettingsFileReader(
            _write(tmp_path, "SORT\n1, SORT_MAX_EXAMS_PER_DAY\n")
        ).read()


# An unknown sort criterion is rejected.
def test_rejects_unknown_sort_criterion(tmp_path):
    content = "THRESHOLD\nMAX_EXAMS_PER_DAY, ON, 2\nSORT\n1, NOPE\n"
    with pytest.raises(ValueError):
        SettingsFileReader(_write(tmp_path, content)).read()


# Content before any block header is rejected.
def test_rejects_line_outside_block(tmp_path):
    content = "MAX_EXAMS_PER_DAY, ON, 2\nTHRESHOLD\nMAX_EXAMS_PER_DAY, ON, 2\n"
    with pytest.raises(ValueError):
        SettingsFileReader(_write(tmp_path, content)).read()


# A missing settings file surfaces a file error.
def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        SettingsFileReader(tmp_path / "nope.txt").read()


# --- Boundary checks -------------------------------------------------------

# k == 0 is valid while ON only for MAX_ELECTIVE_COLLISIONS (spec 2.3).
def test_elective_collisions_allows_k_zero(tmp_path):
    settings = SettingsFileReader(
        _write(tmp_path, "THRESHOLD\nMAX_ELECTIVE_COLLISIONS, ON, 0\n")
    ).read()
    entry = settings.thresholds.for_criterion(Criterion.MAX_ELECTIVE_COLLISIONS)
    assert entry is not None
    assert entry.k == 0


# k == 0 while ON is rejected for a positive-only criterion.
def test_rejects_zero_k_for_positive_criterion(tmp_path):
    with pytest.raises(ValueError):
        SettingsFileReader(
            _write(tmp_path, "THRESHOLD\nMAX_EXAMS_PER_DAY, ON, 0\n")
        ).read()


# A THRESHOLD header with no entries beneath it is rejected.
def test_rejects_empty_threshold_block(tmp_path):
    with pytest.raises(ValueError):
        SettingsFileReader(_write(tmp_path, "THRESHOLD\n")).read()


# Sort priorities must be sequential from 1 with no gaps.
def test_rejects_priority_gap(tmp_path):
    content = (
        "THRESHOLD\nMAX_EXAMS_PER_DAY, ON, 2\n"
        "SORT\n1, SORT_MAX_EXAMS_PER_DAY\n3, SORT_MIN_DAYS_MANDATORY\n"
    )
    with pytest.raises(ValueError):
        SettingsFileReader(_write(tmp_path, content)).read()


# A sort priority below 1 is rejected.
def test_rejects_zero_priority(tmp_path):
    content = "THRESHOLD\nMAX_EXAMS_PER_DAY, ON, 2\nSORT\n0, SORT_MAX_EXAMS_PER_DAY\n"
    with pytest.raises(ValueError):
        SettingsFileReader(_write(tmp_path, content)).read()
