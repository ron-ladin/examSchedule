"""
Reader: ClassroomFileReader
----------------------------
Reads the classrooms file and converts each record into a Classroom object.

Responsible only for:
    - Reading Classrooms.txt (specv4 §2.2)
    - Parsing each $$$$-delimited room record
    - Validating capacity and rejecting duplicate room ids
    - Creating Classroom objects

File format (specv4 §2.2.2):
    $$$$
    [Room Name]      # free text (§2.2.3)
    [Capacity]       # positive integer (§2.2.4)
    $$$$
"""

from pathlib import Path
from typing import List

from src.domain.classroom import Classroom


class ClassroomFileReader:
    RECORD_LINE_COUNT = 2  # room name + capacity (specv4 §2.2.2)

    def __init__(self, classrooms_path: Path):
        self.classrooms_path = Path(classrooms_path)

    def read(self) -> List[Classroom]:
        records = self._read_records()
        rooms = [self._parse_classroom_record(record) for record in records]

        self._validate_unique_room_ids(rooms)

        return rooms

    def _read_records(self) -> List[List[str]]:
        content = self.classrooms_path.read_text(encoding="utf-8")
        raw_records = content.split("$$$$")

        records: List[List[str]] = []

        for raw_record in raw_records:
            lines = [
                line.strip()
                for line in raw_record.splitlines()
                if line.strip()
            ]

            if lines:
                records.append(lines)

        # An empty file / file with no records is NOT a hard error here
        # (spec §2.2.6): the caller surfaces a "No valid rooms in file" badge
        # and keeps Generate blocked. Returning [] lets read() yield 0 rooms.
        return records

    def _parse_classroom_record(self, record: List[str]) -> Classroom:
        # A record is exactly a name line and a capacity line (specv4 §2.2.2).
        if len(record) != self.RECORD_LINE_COUNT:
            raise ValueError(
                f"Classroom record must contain a room name and a capacity line: {record}"
            )

        room_id, capacity_text = record

        # Capacity must be a positive integer (specv4 §2.2.4). isdigit() rejects
        # negatives/decimals; the explicit > 0 check rejects "0" here at the
        # adapter boundary rather than deferring to the Classroom invariant.
        if not capacity_text.isdigit() or int(capacity_text) <= 0:
            raise ValueError(f"Classroom capacity must be a positive integer: {capacity_text}")

        return Classroom(room_id=room_id, capacity=int(capacity_text))

    def _validate_unique_room_ids(self, rooms: List[Classroom]) -> None:
        seen_ids: set[str] = set()

        for room in rooms:
            if room.room_id in seen_ids:
                raise ValueError(f"Duplicate room id found: {room.room_id}")
            seen_ids.add(room.room_id)
