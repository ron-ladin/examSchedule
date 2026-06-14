"""
Domain Entity: Schedule
------------------------
Represents one complete exam schedule for a specific exam period.

Fields:
    - period      (ExamPeriod)      : the exam period this schedule belongs to
    - assignments (Dict[str, date]) : maps course_id → assigned exam date
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Dict

from src.domain.classroom_assignment import ClassroomAssignment
from src.domain.exam_period import ExamPeriod


@dataclass
class Schedule:
    period: ExamPeriod
    assignments: Dict[str, date] = field(default_factory=dict)
    classroom_assignments: Dict[str, list[ClassroomAssignment]] = field(
        default_factory=dict
    )
    unassigned_classroom_exams: Dict[str, int] = field(default_factory=dict)
