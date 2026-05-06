"""
Domain Entity: ExamPeriod
--------------------------
Represents an exam window for a specific semester and moed.

Fields:
    - semester       (str)           : "FALL" | "SPRING" | "SUMMER"
    - moed           (str)           : "Aleph" | "Bet" | "Gimel"
    - date_ranges    (List[Tuple[date, date]]) : list of (start, end) inclusive date ranges
    - excluded_dates (Set[date])     : individual dates that cannot be used

Methods to implement:
    - get_valid_dates() -> List[date]
        Returns all dates that fall within date_ranges,
        are NOT in excluded_dates, and are NOT on a weekend (Friday/Saturday in Israel,
        or Sunday depending on configuration).

Notes:
    - Use datetime.strptime() for all date parsing — never string compare.
    - Excluded entries can be a single date or a range (see exam_periods.txt format).
    - No file I/O here — pure domain logic.
"""


class ExamPeriod:
    pass
