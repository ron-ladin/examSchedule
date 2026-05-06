"""
Domain Entity: Course
----------------------
Represents a university course that may require an exam.

Fields:
    - id              (str)                   : unique 5-digit course identifier
    - name            (str)                   : full course name
    - instructor      (str)                   : instructor name
    - evaluation_type (str)                   : "Exam" | "Project" | "Attendance"
    - offerings       (List[CourseOffering])  : list of programs/years that take this course

Notes:
    - Use @dataclass or Pydantic BaseModel.
    - Only courses where evaluation_type == "Exam" are scheduled.
    - No file I/O here -- pure data container.
"""


class Course:
    pass
