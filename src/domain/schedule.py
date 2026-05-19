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

from src.domain.exam_period import ExamPeriod


@dataclass
class Schedule:
    period: ExamPeriod
    assignments: Dict[str, date] = field(default_factory=dict)
