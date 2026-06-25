"""Canonical ordering helpers for exam periods."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

from src.domain.exam_period import ExamPeriod

STANDARD_PERIOD_ORDER: tuple[tuple[str, str], ...] = (
    ("FALL", "Aleph"),
    ("FALL", "Bet"),
    ("FALL", "Gimel"),
    ("SPRI", "Aleph"),
    ("SPRI", "Bet"),
    ("SPRI", "Gimel"),
    ("SUMM", "Aleph"),
    ("SUMM", "Bet"),
    ("SUMM", "Gimel"),
)

_STANDARD_PERIOD_INDEX = {
    f"{semester} - {moed}": index
    for index, (semester, moed) in enumerate(STANDARD_PERIOD_ORDER)
}

_T = TypeVar("_T")


def canonical_period_key(period_key: str) -> tuple[int, str]:
    """Return a stable sort key for standard periods first, then extras."""
    return (
        _STANDARD_PERIOD_INDEX.get(period_key, len(_STANDARD_PERIOD_INDEX)),
        period_key,
    )


def sort_periods_canonically(periods: list[ExamPeriod]) -> list[ExamPeriod]:
    """Return exam periods in the shared canonical display/generation order."""
    return sorted(periods, key=lambda period: canonical_period_key(period.get_key()))


def sort_period_mapping_canonically(mapping: Mapping[str, _T]) -> dict[str, _T]:
    """Return a dict inserted in canonical period order."""
    return {
        key: mapping[key]
        for key in sorted(mapping, key=canonical_period_key)
    }
