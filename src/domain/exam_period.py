"""
Domain Entity: ExamPeriod
--------------------------
Represents an exam window for a specific semester and moed.

Fields:
    - semester       (str)           : "FALL" | "SPRI" | "SUMM"
    - moed           (str)           : "Aleph" | "Bet" | "Gimel"
    - date_ranges    (List[Tuple[date, date]]) : list of (start, end) inclusive date ranges
    - excluded_dates (Set[date])     : individual dates that cannot be used

Methods to implement:
    - get_valid_dates() -> List[date]
        Returns all dates that fall within date_ranges,
        are NOT in excluded_dates,
        and are not Saturdays.

Notes:
    - Use datetime.strptime() for all date parsing in the file/data provider layer —
      never string compare dates.
    - Excluded entries can be a single date or a range.
    - Holidays should be listed in the input file as excluded dates
      when they cannot be used.
    - Saturdays are automatically excluded.
    - No file I/O here — pure domain logic.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from src.domain.semester import normalize_semester


@dataclass
class ExamPeriod:
    semester: str  # FALL / SPRI / SUMM
    moed: str      # Aleph / Bet / Gimel
    date_ranges: list[tuple[date, date]]
    excluded_dates: set[date] = field(default_factory=set)

    def get_valid_dates(self) -> list[date]:
        valid_dates: list[date] = []

        for start_date, end_date in self.date_ranges:
            current_date = start_date

            while current_date <= end_date:
                if not self._is_excluded_date(current_date):
                    valid_dates.append(current_date)

                current_date += timedelta(days=1)

        return valid_dates

    def _is_excluded_date(self, exam_date: date) -> bool:
        return (
            exam_date in self.excluded_dates
            or self._is_saturday(exam_date)
        )

    def _is_saturday(self, exam_date: date) -> bool:
        return exam_date.weekday() == 5

    def get_overall_date_boundaries(self) -> tuple[date, date]:
        """Return the earliest start and latest end across all date ranges."""
        if not self.date_ranges:
            raise ValueError("ExamPeriod has no date ranges.")
        return (
            min(s for s, _ in self.date_ranges),
            max(e for _, e in self.date_ranges),
        )

    def get_key(self) -> str:
        return f"{normalize_semester(self.semester)} - {self.moed}"
