"""
Domain Entity: Classroom
-------------------------
Represents a single examination room available during the exam period
(Feature 4, spec section 2.2).

Fields:
    - room_id  (str) : free-text room name (e.g. "Building A - 101")
    - capacity (int) : maximum number of seats; must be a positive integer

Notes:
    - Immutable value object. No file I/O here.
    - The capacity invariant is enforced here so a Classroom can never hold an
      illegal value; the ClassroomFileReader additionally checks for duplicate
      room IDs across the file (a collection-level concern).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Classroom:
    room_id: str
    capacity: int

    def __post_init__(self) -> None:
        if not self.room_id.strip():
            raise ValueError("Classroom room_id must not be empty")

        # Capacity is the number of seats, so it must be a positive integer (spec 2.2.4).
        # bool is a subclass of int, so reject it explicitly (True would pass as 1).
        if isinstance(self.capacity, bool) or self.capacity <= 0:
            raise ValueError(f"Classroom capacity must be a positive integer: {self.capacity}")
