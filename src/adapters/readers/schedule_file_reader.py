"""Parse a generated schedules.txt file back into Schedule domain objects."""

import re
from datetime import date
from pathlib import Path

from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule

_SCHEDULE_HEADER = re.compile(r"^Schedule #\d+:\s*$")
_PERIOD_HEADER = re.compile(r"^\s+\[(.+)\]\s*$")
_ENTRY_LINE = re.compile(
    r"^\s+-\s+.+\|\s+Course ID:\s+(\S+)\s+\|\s+Date:\s+(\d{2}-\d{2}-\d{4})"
)


def _parse_date(text: str) -> date:
    day, month, year = text.split("-")
    return date(int(year), int(month), int(day))


def _stub_period(key: str) -> ExamPeriod:
    """Build a minimal ExamPeriod from a period key string like 'FALL - Aleph'."""
    if " - " in key:
        semester, moed = key.split(" - ", 1)
    else:
        semester, moed = key, ""
    return ExamPeriod(semester=semester, moed=moed, date_ranges=[])


def _flush(
    result: dict[str, list[Schedule]],
    schedule: Schedule,
    period: str,
) -> None:
    if schedule.assignments:
        result.setdefault(period, []).append(schedule)


class ScheduleFileReader:
    """Read a schedules.txt output file into a dict of period_key → [Schedule]."""

    def read(self, path: Path) -> dict[str, list[Schedule]]:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        result: dict[str, list[Schedule]] = {}
        current_schedule: Schedule | None = None
        current_period: str | None = None

        for line in lines:
            if _SCHEDULE_HEADER.match(line):
                if current_schedule is not None and current_period is not None:
                    _flush(result, current_schedule, current_period)
                current_schedule = None
                current_period = None
            elif current_schedule is None and current_period is None:
                period_match = _PERIOD_HEADER.match(line)
                if period_match:
                    current_period = period_match.group(1)
                    current_schedule = Schedule(period=_stub_period(current_period))
            elif current_schedule is not None:
                period_match = _PERIOD_HEADER.match(line)
                if period_match:
                    _flush(result, current_schedule, current_period)
                    current_period = period_match.group(1)
                    current_schedule = Schedule(period=_stub_period(current_period))
                    continue
                entry_match = _ENTRY_LINE.match(line)
                if entry_match:
                    course_id = entry_match.group(1)
                    exam_date = _parse_date(entry_match.group(2))
                    current_schedule.assignments[course_id] = exam_date

        if current_schedule is not None and current_period is not None:
            _flush(result, current_schedule, current_period)

        return result
