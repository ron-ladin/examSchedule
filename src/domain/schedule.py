"""
Domain Entity: Schedule
------------------------
Represents one complete exam schedule for a specific exam period.

Fields:
    - period      (ExamPeriod)      : the exam period this schedule belongs to
    - assignments (dict[str, date]) : maps course_id → assigned exam date
"""

from dataclasses import dataclass, field
from datetime import date
from src.domain.classroom_assignment import ClassroomAssignment
from src.domain.exam_period import ExamPeriod


@dataclass
class Schedule:
    period: ExamPeriod
    assignments: dict[str, date] = field(default_factory=dict)
    classroom_assignments: dict[str, list[ClassroomAssignment]] = field(
        default_factory=dict
    )
    unassigned_classroom_exams: dict[str, int] = field(default_factory=dict)
