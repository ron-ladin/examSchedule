"""
Unit Tests: SlotsFileReader (SCRUM-291, Feature 4 §2.3)
------------------------------------------------------
A focused suite with sanity, edge, negative and boundary checks. Uses the
tmp_path fixture to write a temporary $$$$-wrapped slots file.
"""

from datetime import time

import pytest

from src.adapters.readers.slots_file_reader import SlotsFileReader


# Helper: write slots content to a temp file and return its path.
def _write(tmp_path, content):
    path = tmp_path / "slots.txt"
    path.write_text(content, encoding="utf-8")
    return path


# --- Sanity checks ---------------------------------------------------------

# A valid ascending line yields one TimeSlot per time, in order.
def test_reads_valid_slots(tmp_path):
    slots = SlotsFileReader(_write(tmp_path, "$$$$\n9:00, 13:00, 19:00\n$$$$")).read()
    assert [s.time for s in slots] == [time(9, 0), time(13, 0), time(19, 0)]


# A single time is a valid (trivially ordered) sequence.
def test_reads_single_slot(tmp_path):
    slots = SlotsFileReader(_write(tmp_path, "$$$$\n9:00\n$$$$")).read()
    assert [s.time for s in slots] == [time(9, 0)]


# --- Edge cases ------------------------------------------------------------

# Zero-padded times parse the same as unpadded ones.
def test_zero_padded_time(tmp_path):
    slots = SlotsFileReader(_write(tmp_path, "$$$$\n09:00, 13:00\n$$$$")).read()
    assert slots[0].time == time(9, 0)


# Extra whitespace around tokens and a trailing comma are tolerated.
def test_whitespace_and_trailing_comma_tolerated(tmp_path):
    slots = SlotsFileReader(_write(tmp_path, "$$$$\n  9:00 ,  13:00 ,\n$$$$")).read()
    assert [s.time for s in slots] == [time(9, 0), time(13, 0)]


# --- Negative checks -------------------------------------------------------

# A gap smaller than 4 hours is rejected (§2.3.4.a).
def test_rejects_small_gap(tmp_path):
    with pytest.raises(ValueError):
        SlotsFileReader(_write(tmp_path, "$$$$\n9:00, 11:00\n$$$$")).read()


# A descending sequence is rejected (§2.3.4.b).
def test_rejects_descending(tmp_path):
    with pytest.raises(ValueError, match="ascending"):
        SlotsFileReader(_write(tmp_path, "$$$$\n19:00, 13:00, 9:00\n$$$$")).read()


# More than 3 slots is rejected (§2.3.3).
def test_rejects_more_than_three_slots(tmp_path):
    with pytest.raises(ValueError):
        SlotsFileReader(_write(tmp_path, "$$$$\n6:00, 10:00, 14:00, 18:00\n$$$$")).read()


# A malformed time is rejected.
@pytest.mark.parametrize("bad", ["25:00", "9:60", "nine", "9-00"])
def test_rejects_malformed_time(tmp_path, bad):
    with pytest.raises(ValueError):
        SlotsFileReader(_write(tmp_path, f"$$$$\n{bad}\n$$$$")).read()


# More than one content line is rejected (§2.3.6 shows a single line).
def test_rejects_multiple_lines(tmp_path):
    with pytest.raises(ValueError):
        SlotsFileReader(_write(tmp_path, "$$$$\n9:00\n13:00\n$$$$")).read()


# An empty file is rejected.
def test_rejects_empty_file(tmp_path):
    with pytest.raises(ValueError):
        SlotsFileReader(_write(tmp_path, "")).read()


# A missing file surfaces a file error.
def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        SlotsFileReader(tmp_path / "nope.txt").read()


# --- Boundary checks -------------------------------------------------------

# An exactly 4-hour gap is accepted (§2.3.4.a boundary).
def test_accepts_exact_four_hour_gap(tmp_path):
    slots = SlotsFileReader(_write(tmp_path, "$$$$\n9:00, 13:00\n$$$$")).read()
    assert len(slots) == 2


# Exactly 3 slots with valid gaps are accepted; midnight and late times parse.
def test_accepts_three_slots_with_edges(tmp_path):
    slots = SlotsFileReader(_write(tmp_path, "$$$$\n0:00, 8:00, 23:00\n$$$$")).read()
    assert [s.time for s in slots] == [time(0, 0), time(8, 0), time(23, 0)]
