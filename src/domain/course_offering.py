"""
Domain Entity: CourseOffering
------------------------------
Represents a single program's enrollment in a course.

Fields:
    - program_id  (str)  : 5-digit program code (e.g. "83101")
    - year        (int)  : study year within the program (e.g. 1, 2, 3)
    - semester    (str)  : "FALL" | "SPRING" | "SUMMER"
    - requirement (str)  : "Obligatory" | "Elective"

Notes:
    - Use @dataclass or Pydantic BaseModel.
    - No file I/O here -- pure data container.
    - "SPRI" from the file must be mapped to "SPRING" BEFORE constructing this object.
"""


class CourseOffering:
    pass
