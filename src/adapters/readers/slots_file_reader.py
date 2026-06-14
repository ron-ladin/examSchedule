"""
Reader: SlotsFileReader
------------------------
Reads the exam time-slots file and converts it into a list of TimeSlot objects.

Responsible only for:
    - Reading the slots file (CLI input, specv4 §2.3.6)
    - Parsing the single comma-separated line of HH:MM times
    - Validating the slot sequence via TimeSlot.validate_sequence
    - Creating TimeSlot objects

File format (specv4 §2.3.6):
    $$$$
    9:00, 13:00, 19:00      # 24-hour HH:MM times, comma-separated (§2.3.1)
    $$$$
"""

from datetime import datetime, time
from pathlib import Path

from src.domain.time_slot import TimeSlot


class SlotsFileReader:
    TIME_FORMAT = "%H:%M"

    def __init__(self, slots_path: Path):
        self.slots_path = Path(slots_path)

    def read(self) -> list[TimeSlot]:
        line = self._read_slots_line()
        return self.parse_line(line)

    @classmethod
    def parse_line(cls, line: str) -> list[TimeSlot]:
        """
        Parse one comma-separated line of HH:MM times into validated TimeSlots.

        Shared by the file path (read) and the GUI text-input path so both
        enforce identical rules (specv4 §2.3): ascending order, ≤3 per day,
        ≥4h gaps. Raises ValueError on any malformed or invalid input.
        """
        # Keep input order: the spec requires ascending entry and
        # validate_sequence checks the list as given (specv4 §2.3.4.b).
        tokens = [token.strip() for token in line.split(",") if token.strip()]

        # At least one slot must be defined (specv4 §3.1.c).
        if not tokens:
            raise ValueError("No time slots provided")

        slots = [TimeSlot(time=SlotsFileReader._parse_time(token)) for token in tokens]

        # Enforces ≤3 slots, ascending order and ≥4h gaps in one place
        # (specv4 §2.3.3 / §2.3.4).
        TimeSlot.validate_sequence(slots)

        return slots

    def _read_slots_line(self) -> str:
        # Drop the $$$$ markers, then keep the non-empty content lines (specv4 §2.3.6).
        content = self.slots_path.read_text(encoding="utf-8").replace("$$$$", "")

        lines = [line.strip() for line in content.splitlines() if line.strip()]

        # Exactly one comma-separated line of times is expected (specv4 §2.3.6).
        if len(lines) != 1:
            raise ValueError(
                f"Slots file must contain exactly one line of times: {self.slots_path}"
            )

        return lines[0]

    @staticmethod
    def _parse_time(token: str) -> time:
        # %H:%M accepts "9:00" and "09:00" and rejects out-of-range/malformed
        # input (specv4 §2.3.1). Re-raise with the token for a clearer message.
        try:
            return datetime.strptime(token, SlotsFileReader.TIME_FORMAT).time()
        except ValueError as exc:
            raise ValueError(f"Invalid time '{token}', expected 24-hour HH:MM") from exc
