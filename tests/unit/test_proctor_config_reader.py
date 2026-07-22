"""
Unit Tests: ProctorConfigReader (SCRUM-292, Feature 4 §2.4)
----------------------------------------------------------
A focused suite with a few checks of each kind: sanity, edge, negative,
and boundary. Uses the tmp_path fixture to write a temporary ratio file.
"""

import pytest

from src.adapters.readers.proctor_config_reader import ProctorConfigReader
from src.domain.proctor import ProctorConfig


# Helper: write ratio content to a temp file and return its path.
def _write(tmp_path, content):
    path = tmp_path / "proctors.txt"
    path.write_text(content, encoding="utf-8")
    return path


# --- Sanity checks ---------------------------------------------------------

# A valid "1:X" line yields a ProctorConfig holding X.
def test_reads_valid_ratio(tmp_path):
    config = ProctorConfigReader(_write(tmp_path, "1:20")).read()
    assert config.students_per_proctor == 20


# proctors_for rounds up: ceil(students / X) (spec 2.4.3).
def test_proctors_for_rounds_up(tmp_path):
    config = ProctorConfigReader(_write(tmp_path, "1:20")).read()
    assert config.proctors_for(20) == 1
    assert config.proctors_for(21) == 2
    assert config.proctors_for(40) == 2


# --- Edge cases ------------------------------------------------------------

# Whitespace around the tokens and a trailing blank line are tolerated.
def test_whitespace_tolerated(tmp_path):
    config = ProctorConfigReader(_write(tmp_path, "  1 : 20  \n\n")).read()
    assert config.students_per_proctor == 20


# --- Negative checks -------------------------------------------------------

# A line without a colon is rejected.
def test_rejects_missing_colon(tmp_path):
    with pytest.raises(ValueError):
        ProctorConfigReader(_write(tmp_path, "120")).read()


# The ratio must start with "1:" (spec 5.3) — pin the specific branch.
def test_rejects_numerator_not_one(tmp_path):
    with pytest.raises(ValueError, match="must start with"):
        ProctorConfigReader(_write(tmp_path, "2:20")).read()


# A non-integer denominator is rejected.
def test_rejects_non_integer_denominator(tmp_path):
    with pytest.raises(ValueError, match="positive integer"):
        ProctorConfigReader(_write(tmp_path, "1:abc")).read()


# An empty denominator (e.g. "1:") is rejected.
def test_rejects_empty_denominator(tmp_path):
    with pytest.raises(ValueError, match="positive integer"):
        ProctorConfigReader(_write(tmp_path, "1:")).read()


# More than two colon-separated parts is rejected.
def test_rejects_extra_parts(tmp_path):
    with pytest.raises(ValueError):
        ProctorConfigReader(_write(tmp_path, "1:2:3")).read()


# More than one ratio line is rejected.
def test_rejects_multiple_lines(tmp_path):
    with pytest.raises(ValueError):
        ProctorConfigReader(_write(tmp_path, "1:20\n1:30")).read()


# An empty file is rejected.
def test_rejects_empty_file(tmp_path):
    with pytest.raises(ValueError):
        ProctorConfigReader(_write(tmp_path, "")).read()


# A missing file surfaces a file error.
def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ProctorConfigReader(tmp_path / "nope.txt").read()


# --- Boundary checks -------------------------------------------------------

# X == 1 is valid (one proctor per student).
def test_ratio_one_to_one_valid(tmp_path):
    config = ProctorConfigReader(_write(tmp_path, "1:1")).read()
    assert config.students_per_proctor == 1


# X == 0 is rejected (must be greater than 0, spec 2.4.1).
def test_rejects_zero_denominator(tmp_path):
    with pytest.raises(ValueError, match="positive integer"):
        ProctorConfigReader(_write(tmp_path, "1:0")).read()


# A room with zero students needs zero proctors (spec 7.5).
def test_proctors_for_zero_students(tmp_path):
    config = ProctorConfig(students_per_proctor=20)
    assert config.proctors_for(0) == 0


# A negative student count is rejected at the value-object boundary.
def test_proctors_for_rejects_negative(tmp_path):
    config = ProctorConfig(students_per_proctor=20)
    with pytest.raises(ValueError):
        config.proctors_for(-1)


# ProctorConfig with students_per_proctor=0 raises ValueError at construction,
# preventing a ZeroDivisionError from proctors_for().
def test_proctor_config_rejects_zero_students_per_proctor():
    with pytest.raises(ValueError):
        ProctorConfig(students_per_proctor=0)


# bool is a subclass of int; True == 1 would silently pass without the guard.
def test_proctor_config_rejects_bool_students_per_proctor():
    with pytest.raises(ValueError):
        ProctorConfig(students_per_proctor=True)
