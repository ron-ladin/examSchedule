"""
Domain Entity: ExamPeriod
--------------------------
Represents an exam window for a specific semester and moed.

Fields:
    - semester       (str)           : "FALL" | "SPRI" | "SUMM"
    - moed           (str)           : "Aleph" | "Bet" | "Gimel"
    - date_ranges    (List[Tuple[date, date]]) : list of (start, end) inclusive date ranges
    - excluded_dates (List[date])    : individual dates that cannot be used

Methods to implement:
    - get_valid_dates() -> List[date]
        Returns all dates that fall within date_ranges
        and are NOT in excluded_dates.

Notes:
    - Use datetime.strptime() for all date parsing in the file/data provider layer —
      never string compare dates.
    - Excluded entries can be a single date or a range.
    - Weekend dates or holidays should be listed in the input file as excluded dates
      when they cannot be used.
    - No file I/O here — pure domain logic.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Tuple

from src.domain.semester import normalize_semester


@dataclass(frozen=True)
class ExamPeriod:
    semester: str  # FALL / SPRI / SUMM
    moed: str      # Aleph / Bet / Gimel
    date_ranges: List[Tuple[date, date]]
    excluded_dates: List[date] = field(default_factory=list)

    def get_valid_dates(self) -> List[date]:
        valid_dates: List[date] = []

        for start_date, end_date in self.date_ranges:
            current_date = start_date

            while current_date <= end_date:
                if current_date not in self.excluded_dates:
                    valid_dates.append(current_date)

                current_date += timedelta(days=1)

        return valid_dates

    def get_key(self) -> str:
        return f"{normalize_semester(self.semester)} - {self.moed}"