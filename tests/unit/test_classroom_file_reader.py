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

# Capacity 0 is rejected (must be positive, §2.2.4).
def test_rejects_zero_capacity(tmp_path):
    with pytest.raises(ValueError):
        ClassroomFileReader(_write(tmp_path, "$$$$\nA-101\n0\n$$$$")).read()


# A negative capacity is rejected.
def test_rejects_negative_capacity(tmp_path):
    with pytest.raises(ValueError):
        ClassroomFileReader(_write(tmp_path, "$$$$\nA-101\n-5\n$$$$")).read()


# A non-integer capacity is rejected.
def test_rejects_non_integer_capacity(tmp_path):
    with pytest.raises(ValueError, match="positive integer"):
        ClassroomFileReader(_write(tmp_path, "$$$$\nA-101\nfifty\n$$$$")).read()


# A record missing the capacity line is rejected.
def test_rejects_record_missing_capacity(tmp_path):
    with pytest.raises(ValueError):
        ClassroomFileReader(_write(tmp_path, "$$$$\nA-101\n$$$$")).read()


# A record with an extra line is rejected.
def test_rejects_record_with_extra_line(tmp_path):
    with pytest.raises(ValueError):
        ClassroomFileReader(_write(tmp_path, "$$$$\nA-101\n50\nextra\n$$$$")).read()


# Duplicate room ids across records are rejected.
def test_rejects_duplicate_room_ids(tmp_path):
    content = "$$$$\nA-101\n50\n$$$$\nA-101\n30\n$$$$"
    with pytest.raises(ValueError, match="Duplicate"):
        ClassroomFileReader(_write(tmp_path, content)).read()


# An empty file is rejected (at least one room required, §3.1.b).
def test_rejects_empty_file(tmp_path):
    with pytest.raises(ValueError):
        ClassroomFileReader(_write(tmp_path, "")).read()


# A missing file surfaces a file error.
def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ClassroomFileReader(tmp_path / "nope.txt").read()


# --- Boundary checks -------------------------------------------------------

# Capacity 1 is valid (smallest positive room).
def test_capacity_one_is_valid(tmp_path):
    rooms = ClassroomFileReader(_write(tmp_path, "$$$$\nA-101\n1\n$$$$")).read()
    assert rooms[0].capacity == 1
