from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class ExamPeriodDTO(BaseModel):
    """Represents an exam period with its date range and exclusion state."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    semester: str
    moed: str
    start_date: date
    end_date: date
    excluded: bool = False
    valid_dates: list[date] = []


class PeriodRangeDTO(BaseModel):
    """Payload for updating the date range of an exam period."""

    start: date
    end: date


class ExclusionDTO(BaseModel):
    """Payload for toggling the excluded flag on an exam period."""

    excluded: bool
