"""
Domain Entity: TimeSlot
------------------------
A single point in time at which an exam may start (Feature 4, spec section 2.3).

Fields:
    - time (datetime.time) : a single HH:MM point — NOT a start/end range.

Notes:
    - Immutable value object. No file I/O here.
    - An exam may last up to 4 hours, so consecutive slots in a day must be at
      least 4 hours apart and listed in ascending order (spec 2.3.4 / 7.3).
      That rule applies to a *sequence* of slots, so it lives in the
      validate_sequence() helper rather than on a single TimeSlot.
"""

from dataclasses import dataclass
from datetime import time as dt_time  # aliased so the `time` field does not shadow it
from typing import List

MINUTES_PER_HOUR = 60
MIN_GAP_HOURS = 4  # an exam can last up to 4 hours (spec 2.3.4 / 7.3)
MAX_SLOTS_PER_DAY = 3  # at most 3 slots may be defined per day (spec 2.3.3)


@dataclass(frozen=True)
class TimeSlot:
    time: dt_time

    @staticmethod
    def validate_sequence(slots: List["TimeSlot"]) -> None:
        """
        Validate a day's slots: at most MAX_SLOTS_PER_DAY of them (spec 2.3.3),
        in ascending order with at least MIN_GAP_HOURS between each consecutive
        pair (spec 2.3.4).

        Raises ValueError on the first violation. An empty or single-slot
        sequence is trivially valid.
        """
        if len(slots) > MAX_SLOTS_PER_DAY:
            raise ValueError(
                f"At most {MAX_SLOTS_PER_DAY} time slots are allowed per day: got {len(slots)}"
            )

        minimum_gap = MIN_GAP_HOURS * MINUTES_PER_HOUR

        for current, following in zip(slots, slots[1:]):
            gap = TimeSlot._minutes(following.time) - TimeSlot._minutes(current.time)

            if gap < minimum_gap:
                raise ValueError(
                    "Time slots must be ascending and at least "
                    f"{MIN_GAP_HOURS} hours apart: {current.time} -> {following.time}"
                )

    @staticmethod
    def _minutes(value: dt_time) -> int:
        return value.hour * MINUTES_PER_HOUR + value.minute
