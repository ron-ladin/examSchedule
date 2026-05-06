"""
Domain Entity: Schedule
------------------------
Represents one complete, conflict-free exam schedule assignment.

Fields:
    - assignments (Dict[Course, date]) : mapping from each course to its assigned exam date

Notes:
    - Use @dataclass or Pydantic BaseModel.
    - This object is YIELDED by ScheduleGenerator — never stored in a list.
    - Immutable after construction (use frozen=True if dataclass).
"""


class Schedule:
    pass
