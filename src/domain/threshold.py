"""
Domain Utility: Threshold Criteria
-----------------------------------
Threshold criteria parsed from the THRESHOLD block of settings.txt.

THRESHOLD block line format:
    CRITERION_NAME, ON/OFF, k

Criteria (spec sections 2.1-2.5):
    MIN_DAYS_BETWEEN_MANDATORY_EXAMS  (2.1) - k >= 1
    MIN_DAYS_BETWEEN_ANY_EXAMS        (2.2) - k >= 1
    MAX_ELECTIVE_COLLISIONS           (2.3) - k >= 0  (non-negative)
    MIN_DAYS_EXAM_PERIOD_SPREAD       (2.4) - k >= 1
    MAX_EXAMS_PER_DAY                 (2.5) - k >= 1

Notes:
    - Pure data containers plus a normalization helper. No file I/O here.
    - Validation of k lives in the reader (SettingsFileReader).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple


class Criterion(Enum):
    """The five threshold criteria, named after spec sections 2.1-2.5."""

    MIN_DAYS_BETWEEN_MANDATORY_EXAMS = "MIN_DAYS_BETWEEN_MANDATORY_EXAMS"
    MIN_DAYS_BETWEEN_ANY_EXAMS = "MIN_DAYS_BETWEEN_ANY_EXAMS"
    MAX_ELECTIVE_COLLISIONS = "MAX_ELECTIVE_COLLISIONS"
    MIN_DAYS_EXAM_PERIOD_SPREAD = "MIN_DAYS_EXAM_PERIOD_SPREAD"
    MAX_EXAMS_PER_DAY = "MAX_EXAMS_PER_DAY"


# Minimum allowed k per criterion when the criterion is enabled (ON).
# Most criteria require a positive k; elective-collisions allows zero (spec 2.3).
CRITERION_MIN_K: Dict[Criterion, int] = {
    Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS: 1,
    Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS: 1,
    Criterion.MAX_ELECTIVE_COLLISIONS: 0,
    Criterion.MIN_DAYS_EXAM_PERIOD_SPREAD: 1,
    Criterion.MAX_EXAMS_PER_DAY: 1,
}

# Lowercased criterion token -> Criterion, for case-insensitive parsing.
CRITERION_ALIASES: Dict[str, Criterion] = {
    criterion.value.lower(): criterion for criterion in Criterion
}


def normalize_criterion(value: str) -> Criterion:
    """Convert a criterion token into a Criterion, case-insensitively."""
    key = value.strip().lower()

    if key not in CRITERION_ALIASES:
        raise ValueError(f"Invalid criterion: {value}")

    return CRITERION_ALIASES[key]


@dataclass(frozen=True)
class ThresholdEntry:
    """A single THRESHOLD line: a criterion, its on/off state, and its k value."""

    criterion: Criterion
    enabled: bool
    k: int


@dataclass(frozen=True)
class ThresholdSettings:
    """The parsed THRESHOLD block: an immutable collection of ThresholdEntry objects."""

    entries: Tuple[ThresholdEntry, ...] = ()

    def for_criterion(self, criterion: Criterion) -> Optional[ThresholdEntry]:
        """Return the entry for the given criterion, or None if absent."""
        for entry in self.entries:
            if entry.criterion is criterion:
                return entry
        return None
