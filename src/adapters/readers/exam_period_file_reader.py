"""
Reader: ExamPeriodFileReader
-----------------------------
Reads the exam periods file and converts each record into an ExamPeriod object.

Responsible only for:
    - Reading ExamDates.txt
    - Parsing exam period records
    - Parsing included and excluded date ranges
    - Creating ExamPeriod objects
"""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Set, Tuple

from src.domain.exam_period import ExamPeriod
from src.domain.semester import normalize_semester


class ExamPeriodFileReader:
    DATE_FORMAT = "%d-%m-%Y"

    VALID_MOEDS = {
        "aleph": "Aleph",
        "bet": "Bet",
        "gimel": "Gimel",
    }

    def __init__(self, periods_path: Path):
        self.periods_path = Path(periods_path)

    def read(self) -> List[ExamPeriod]:
        records = self._read_records()
        periods: List[ExamPeriod] = []

        for record in records:
            periods.append(self._parse_exam_period_record(record))

        return periods

    def _read_records(self) -> List[List[str]]:
        content = self.periods_path.read_text(encoding="utf-8")
        raw_records = content.split("$$$$")

        records: List[List[str]] = []

        for raw_record in raw_records:
            lines = [
                line.strip()
                for line in raw_record.splitlines()
                if line.strip()
            ]

            if lines:
                records.append(lines)

        if not records:
            raise ValueError(f"No exam period records found in file: {self.periods_path}")

        return records

    def _parse_exam_period_record(self, record: List[str]) -> ExamPeriod:
        if len(record) < 2:
            raise ValueError(f"Exam period record must contain at least 2 lines: {record}")

        semester, moed = self._parse_period_header(record[0])
        start_date, end_date = self._parse_date_range(record[1])

        excluded_dates: Set[date] = set()

        for line in record[2:]:
            excluded_dates.update(self._parse_excluded_dates(line))

        return ExamPeriod(
            semester=semester,
            moed=moed,
            date_ranges=[(start_date, end_date)],
            excluded_dates=excluded_dates,
        )

    def _parse_period_header(self, line: str) -> Tuple[str, str]:
        parts = [
            part.strip()
            for part in line.split(",")
        ]

        if len(parts) != 2:
            raise ValueError(f"Invalid exam period header: {line}")

        semester, moed = parts

        semester = normalize_semester(semester)
        moed = self._normalize_moed(moed)

        return semester, moed

    def _normalize_moed(self, moed: str) -> str:
        key = moed.strip().lower()

        if key not in self.VALID_MOEDS:
            raise ValueError(f"Invalid moed: {moed}")

        return self.VALID_MOEDS[key]

    def _parse_excluded_dates(self, line: str) -> Set[date]:
        clean_line = line.strip()

        if clean_line.startswith("-"):
            clean_line = clean_line[1:].strip()

        if not clean_line:
            return set()

        if "," in clean_line:
            start_date, end_date = self._parse_date_range(clean_line)
            return self._build_date_set(start_date, end_date)

        first_token = clean_line.split()[0]
        return {self._parse_date(first_token)}

    def _parse_date_range(self, line: str) -> Tuple[date, date]:
        parts = [
            part.strip()
            for part in line.split(",")
        ]

        if len(parts) != 2:
            raise ValueError(f"Invalid date range: {line}")

        start_date = self._parse_date(parts[0])

        end_token = parts[1].split()[0]
        end_date = self._parse_date(end_token)

        if start_date >= end_date:
            raise ValueError(f"Start date must be before end date: {line}")

        return start_date, end_date

    def _parse_date(self, value: str) -> date:
        return datetime.strptime(value, self.DATE_FORMAT).date()

    def _build_date_set(self, start_date: date, end_date: date) -> Set[date]:
        dates: Set[date] = set()
        current_date = start_date

        while current_date <= end_date:
            dates.add(current_date)
            current_date += timedelta(days=1)

        return dates