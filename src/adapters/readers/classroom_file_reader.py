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

The same parser is also exposed for manual GUI input via parse_text().
"""

from pathlib import Path
from typing import List

from src.domain.classroom import Classroom


class ClassroomFileReader:
    RECORD_LINE_COUNT = 2  # room name + capacity (specv4 §2.2.2)

    def __init__(self, classrooms_path: Path):
        self.classrooms_path = Path(classrooms_path)

    def read(self) -> List[Classroom]:
        """Read classrooms from a file path."""
        content = self.classrooms_path.read_text(encoding="utf-8")
        return self.parse_text(content)

    @classmethod
    def parse_text(cls, text: str) -> List[Classroom]:
        """
        Parse classrooms from raw text.

        Used by:
            - read(), for file-based input
            - DesktopController.set_classrooms_from_text(), for manual GUI input

        Accepts the same format as the classrooms file.
        """
        records = cls._records_from_text(text)
        rooms = [cls._parse_classroom_record(record) for record in records]

        cls._validate_unique_room_ids(rooms)

        return rooms

    @classmethod
    def _records_from_text(cls, text: str) -> List[List[str]]:
        raw_records = text.split("$$$$")

        records: List[List[str]] = []

        for raw_record in raw_records:
            lines = [
                line.strip()
                for line in raw_record.splitlines()
                if line.strip()
            ]

            if lines:
                records.append(lines)

        # An empty file / empty manual input is NOT a hard parser error here.
        # The caller can surface "No valid rooms" and keep Generate blocked.
        return records

    @classmethod
    def _parse_classroom_record(cls, record: List[str]) -> Classroom:
        # A record is exactly a name line and a capacity line (specv4 §2.2.2).
        if len(record) != cls.RECORD_LINE_COUNT:
            raise ValueError(
                f"Classroom record must contain a room name and a capacity line: {record}"
            )

        room_id, capacity_text = record

        # Capacity must be a positive integer (specv4 §2.2.4). isdigit() rejects
        # negatives/decimals; the explicit > 0 check rejects "0" here at the
        # adapter boundary rather than deferring to the Classroom invariant.
        if not capacity_text.isdigit() or int(capacity_text) <= 0:
            raise ValueError(
                f"Classroom capacity must be a positive integer: {capacity_text}"
            )

        return Classroom(room_id=room_id, capacity=int(capacity_text))

    @classmethod
    def _validate_unique_room_ids(cls, rooms: List[Classroom]) -> None:
        seen_ids: set[str] = set()

        for room in rooms:
            if room.room_id in seen_ids:
                raise ValueError(f"Duplicate room id found: {room.room_id}")
            seen_ids.add(room.room_id)
