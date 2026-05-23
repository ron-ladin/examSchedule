from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from src.domain.exam_period import ExamPeriod


class ExamPeriodDTO(BaseModel):
    """Represents an exam period with its date range and exclusion state.

    Cannot be built with model_validate(domain_period) directly because the
    domain ExamPeriod uses get_key() / get_valid_dates() methods and
    date_ranges (list of tuples) instead of flat start_date/end_date fields.
    Always use ExamPeriodDTO.from_domain(period) to convert from domain.
    """

    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    semester: str
    moed: str
    start_date: date
    end_date: date
    excluded: bool = False
    valid_dates: list[date] = []

    @classmethod
    def from_domain(
        cls,
        period: ExamPeriod,
        excluded: bool = False,
    ) -> ExamPeriodDTO:
        """Build a DTO from a v1.0 domain ExamPeriod.

        date_ranges is collapsed to one range: first start → last end.
        excluded is an API-level flag (not on the domain object), defaults to False.
        valid_dates is computed fresh from the domain's get_valid_dates().
        """
        from src.domain.semester import display_semester

        if not period.date_ranges:
            raise ValueError(f"ExamPeriod '{period.get_key()}' has no date ranges")
        start = period.date_ranges[0][0]
        end = period.date_ranges[-1][1]

        return cls(
            key=period.get_key(),
            name=f"{display_semester(period.semester)} - {period.moed}",
            semester=period.semester,
            moed=period.moed,
            start_date=start,
            end_date=end,
            excluded=excluded,
            valid_dates=period.get_valid_dates(),
        )


class PeriodRangeDTO(BaseModel):
    """Payload for updating the date range of an exam period."""

    start: date
    end: date


class ExclusionDTO(BaseModel):
    """Payload for toggling the excluded flag on an exam period."""

    excluded: bool
