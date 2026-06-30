"""
Navigation Model
-----------------
Plain-Python (no PyQt6) state machine for navigating loaded schedules in the
results panel. Owns the two navigation caches and the date/variant indexing
algorithms extracted from _ResultsPanel.

Two-level navigation:
    - Date option: a distinct set of exam dates (the "date signature").
    - Variant: a Feature 4 classroom/time-slot allocation for the same dates.

The model never holds its own copy of the schedules; it reads the live mapping
through a provider callback so it stays correct when the panel reassigns or
mutates its schedules dict. This keeps the logic unit-testable without a
QApplication.
"""

from __future__ import annotations
from collections.abc import Callable
from datetime import date

from src.domain.schedule import Schedule

# Date-only identity of a schedule, ignoring Feature 4 variants.
DateSignature = tuple[tuple[str, date], ...]


class NavigationModel:
    """Date/variant navigation indexing over the panel's loaded schedules."""

    def __init__(
        self,
        schedules_source: Callable[[], dict[str, list[Schedule]]],
    ) -> None:
        self._source = schedules_source
        self._date_option_cache: dict[str, list[tuple[DateSignature, list[int]]]] = {}
        self._index_nav_cache: dict[str, dict[int, tuple[int, int]]] = {}
        self._signature_pos_cache: dict[str, dict[DateSignature, int]] = {}

    def _schedules(self, period_key: str) -> list[Schedule]:
        return self._source().get(period_key, [])

    @staticmethod
    def date_signature(schedule: Schedule) -> DateSignature:
        """Date-only identity of a schedule, ignoring Feature 4 variants."""
        return tuple(sorted(schedule.assignments.items()))

    def clear(self) -> None:
        """Drop all cached navigation indexes."""
        self._date_option_cache.clear()
        self._index_nav_cache.clear()
        self._signature_pos_cache.clear()

    def rebuild(self, period_key: str | None = None) -> None:
        """Build fast navigation indexes for loaded schedules.

        Disk-backed schedule lists expose compact navigation metadata, so this
        method can rebuild the date/variant cache without unpickling every stored
        Schedule object from SQLite. Plain lists keep the original behavior.
        """
        all_schedules = self._source()
        keys = [period_key] if period_key is not None else list(all_schedules)

        for key in keys:
            schedules = all_schedules.get(key, [])
            options: list[tuple[DateSignature, list[int]]] = []
            signature_to_pos: dict[DateSignature, int] = {}
            index_nav: dict[int, tuple[int, int]] = {}

            nav_entries = getattr(schedules, "navigation_entries", None)
            if callable(nav_entries):
                entries = nav_entries()
            else:
                entries = [
                    (self.date_signature(schedule), idx)
                    for idx, schedule in enumerate(schedules)
                ]

            for signature, idx in entries:
                date_pos = signature_to_pos.get(signature)

                if date_pos is None:
                    date_pos = len(options)
                    signature_to_pos[signature] = date_pos
                    options.append((signature, []))

                variant_indices = options[date_pos][1]
                variant_pos = len(variant_indices)
                variant_indices.append(idx)
                index_nav[idx] = (date_pos, variant_pos)

            self._date_option_cache[key] = options
            self._index_nav_cache[key] = index_nav
            self._signature_pos_cache[key] = signature_to_pos

    def append_entries(self, period_key: str, start_index: int, count: int) -> None:
        """Append navigation metadata for a newly appended schedule range.

        The incremental path is valid only when the existing cache is current
        through ``start_index`` and the schedule container can expose the new
        entries as the next visible indexes. If either condition is not true,
        fall back to a full rebuild to preserve date/variant navigation exactly.
        """
        if count <= 0:
            return

        schedules = self._schedules(period_key)
        end_index = start_index + count
        if start_index < 0 or end_index > len(schedules):
            self.rebuild(period_key)
            return

        options = self._date_option_cache.get(period_key)
        index_nav = self._index_nav_cache.get(period_key)
        signature_to_pos = self._signature_pos_cache.get(period_key)
        if (
            options is None
            or index_nav is None
            or signature_to_pos is None
            or len(index_nav) != start_index
        ):
            self.rebuild(period_key)
            return

        nav_entries_range = getattr(schedules, "navigation_entries_range", None)
        if callable(nav_entries_range):
            entries = nav_entries_range(start_index, count)
            if entries is None:
                self.rebuild(period_key)
                return
        else:
            entries = [
                (self.date_signature(schedules[idx]), idx)
                for idx in range(start_index, end_index)
            ]

        if len(entries) != count:
            self.rebuild(period_key)
            return

        expected_indexes = range(start_index, end_index)
        if any(
            idx != expected_idx
            for (_signature, idx), expected_idx in zip(entries, expected_indexes)
        ):
            self.rebuild(period_key)
            return

        for signature, idx in entries:
            date_pos = signature_to_pos.get(signature)
            if date_pos is None:
                date_pos = len(options)
                signature_to_pos[signature] = date_pos
                options.append((signature, []))

            variant_indices = options[date_pos][1]
            variant_pos = len(variant_indices)
            variant_indices.append(idx)
            index_nav[idx] = (date_pos, variant_pos)

    def date_options(
        self,
        period_key: str,
    ) -> list[tuple[DateSignature, list[int]]]:
        """Return cached date options, rebuilding if the cache is missing/stale."""
        schedules_count = len(self._schedules(period_key))
        cached_indexes_count = len(self._index_nav_cache.get(period_key, {}))

        if (
            period_key not in self._date_option_cache
            or cached_indexes_count != schedules_count
        ):
            self.rebuild(period_key)

        return self._date_option_cache.get(period_key, [])

    def nav_position(self, period_key: str, idx: int) -> tuple[int, int] | None:
        """Return (date option position, variant position) for a schedule index."""
        schedules_count = len(self._schedules(period_key))
        cached_indexes_count = len(self._index_nav_cache.get(period_key, {}))

        if (
            period_key not in self._index_nav_cache
            or cached_indexes_count != schedules_count
        ):
            self.rebuild(period_key)

        return self._index_nav_cache.get(period_key, {}).get(idx)

    def index_nav(self, period_key: str) -> dict[int, tuple[int, int]]:
        """Return the raw index -> (date pos, variant pos) cache for a period."""
        return self._index_nav_cache.get(period_key, {})

    def ordered_signatures(self, period_key: str) -> list[DateSignature]:
        """Return loaded date-level schedule options in first-seen order."""
        return [signature for signature, _indices in self.date_options(period_key)]

    def indices_for_signature(
        self,
        period_key: str,
        signature: DateSignature,
    ) -> list[int]:
        """Return loaded schedule indexes that share the same exam dates."""
        for cached_signature, indices in self.date_options(period_key):
            if cached_signature == signature:
                return indices
        return []
