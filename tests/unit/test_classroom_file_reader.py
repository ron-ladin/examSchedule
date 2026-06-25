"""
Unit Tests: ClassroomFileReader (SCRUM-290, Feature 4 §2.2)
----------------------------------------------------------
A focused suite with sanity, edge, negative and boundary checks. Uses the
tmp_path fixture to write a temporary $$$$-delimited classrooms file.
"""

import pytest

from src.adapters.readers.classroom_file_reader import ClassroomFileReader


# Helper: write classrooms content to a temp file and return its path.
def _write(tmp_path, content):
    path = tmp_path / "classrooms.txt"
    path.write_text(content, encoding="utf-8")
    return path


# --- Sanity checks ---------------------------------------------------------

# A single valid record yields one Classroom with its name and capacity.
def test_reads_single_room(tmp_path):
    rooms = ClassroomFileReader(_write(tmp_path, "$$$$\nA-101\n50\n$$$$")).read()
    assert len(rooms) == 1
    assert rooms[0].room_id == "A-101"
    assert rooms[0].capacity == 50


# Multiple records are returned in file order.
def test_reads_multiple_rooms_in_order(tmp_path):
    content = "$$$$\nA-101\n50\n$$$$\nB-202\n30\n$$$$"
    rooms = ClassroomFileReader(_write(tmp_path, content)).read()
    assert [(r.room_id, r.capacity) for r in rooms] == [("A-101", 50), ("B-202", 30)]


# --- Edge cases ------------------------------------------------------------

# A room name is free text and may contain spaces and punctuation (§2.2.3).
def test_room_name_is_free_text(tmp_path):
    rooms = ClassroomFileReader(_write(tmp_path, "$$$$\nBuilding A - 101\n50\n$$$$")).read()
    assert rooms[0].room_id == "Building A - 101"


# Surrounding blank lines and whitespace are tolerated.
def test_whitespace_tolerated(tmp_path):
    rooms = ClassroomFileReader(_write(tmp_path, "\n$$$$\n  A-101  \n  50  \n$$$$\n\n")).read()
    assert rooms[0].room_id == "A-101"
    assert rooms[0].capacity == 50


# --- Negative checks -------------------------------------------------------

# Each malformed record must be rejected with a ValueError. Where the error
# message is part of the contract, the expected substring is asserted too.
@pytest.mark.parametrize(
    "content, match",
    [
        pytest.param("$$$$\nA-101\n0\n$$$$", None, id="zero_capacity"),
        pytest.param("$$$$\nA-101\n-5\n$$$$", None, id="negative_capacity"),
        pytest.param("$$$$\nA-101\nfifty\n$$$$", "positive integer", id="non_integer_capacity"),
        pytest.param("$$$$\nA-101\n$$$$", None, id="record_missing_capacity"),
        pytest.param("$$$$\nA-101\n50\nextra\n$$$$", None, id="record_with_extra_line"),
        pytest.param("$$$$\nA-101\n50\n$$$$\nA-101\n30\n$$$$", "Duplicate", id="duplicate_room_ids"),
    ],
)
def test_rejects_malformed_record(tmp_path, content, match):
    with pytest.raises(ValueError, match=match):
        ClassroomFileReader(_write(tmp_path, content)).read()


# An empty file yields 0 rooms instead of raising (§2.2.6): the caller shows a
# "No valid rooms in file" badge and keeps Generate blocked.
def test_empty_file_returns_no_rooms(tmp_path):
    assert ClassroomFileReader(_write(tmp_path, "")).read() == []


# A file with only delimiters/whitespace also yields 0 rooms (§2.2.6).
def test_whitespace_only_file_returns_no_rooms(tmp_path):
    assert ClassroomFileReader(_write(tmp_path, "$$$$\n   \n$$$$")).read() == []


# A missing file surfaces a file error.
def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ClassroomFileReader(tmp_path / "nope.txt").read()


# --- Boundary checks -------------------------------------------------------

# Capacity 1 is valid (smallest positive room).
def test_capacity_one_is_valid(tmp_path):
    rooms = ClassroomFileReader(_write(tmp_path, "$$$$\nA-101\n1\n$$$$")).read()
    assert rooms[0].capacity == 1
