"""
CombinedScheduleIndexer — Cartesian-product navigation helpers.

Pure static utilities; no state.  DesktopController delegates the two
combined-schedule query methods here.
"""

from src.domain.schedule import Schedule


class CombinedScheduleIndexer:
    """Cartesian-product index helpers for multi-period schedule navigation."""

    @staticmethod
    def count(schedules_by_period: dict[str, list[Schedule]]) -> int:
        """Return the Cartesian-product size of the loaded schedules per period."""
        if not schedules_by_period:
            return 0

        total = 1
        for schedules in schedules_by_period.values():
            if not schedules:
                return 0
            total *= len(schedules)

        return total

    @staticmethod
    def at(
        schedules_by_period: dict[str, list[Schedule]],
        index: int,
    ) -> dict[str, Schedule]:
        """Return one combined schedule by Cartesian-product index.

        Avoids materialising list(product(...)) in memory.
        """
        total = CombinedScheduleIndexer.count(schedules_by_period)

        if index < 0 or index >= total:
            raise IndexError(
                f"Combined schedule index {index} out of range for total {total}."
            )

        period_keys = list(schedules_by_period.keys())
        selected_indexes: dict[str, int] = {}
        remainder = index

        for period_key in reversed(period_keys):
            schedules = schedules_by_period[period_key]
            selected_indexes[period_key] = remainder % len(schedules)
            remainder //= len(schedules)

        return {
            period_key: schedules_by_period[period_key][selected_indexes[period_key]]
            for period_key in period_keys
        }
