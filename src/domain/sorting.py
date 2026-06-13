"""
Domain Utility: Sorting Criteria
---------------------------------
Sorting rules parsed from the SORT block of settings.txt.

SORT block line format:
    priority, CRITERION_NAME

Criteria (spec sections 3.1-3.5, all applied in descending order):
    SORT_MIN_DAYS_MANDATORY   (3.1)
    SORT_AVG_DAYS_ANY         (3.2)
    SORT_ELECTIVE_COLLISIONS  (3.3)
    SORT_EXAM_PERIOD_SPREAD   (3.4)
    SORT_MAX_EXAMS_PER_DAY    (3.5)

Notes:
    - Pure data containers plus a normalization helper. No file I/O here.
    - Validation of priorities lives in the reader (SettingsFileReader).
    - Sorting may change at runtime; threshold requirements do not.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple


class SortCriterion(Enum):
    """The five sort criteria, named after spec sections 3.1-3.5."""

    SORT_MIN_DAYS_MANDATORY = "SORT_MIN_DAYS_MANDATORY"
    SORT_AVG_DAYS_ANY = "SORT_AVG_DAYS_ANY"
    SORT_ELECTIVE_COLLISIONS = "SORT_ELECTIVE_COLLISIONS"
    SORT_EXAM_PERIOD_SPREAD = "SORT_EXAM_PERIOD_SPREAD"
    SORT_MAX_EXAMS_PER_DAY = "SORT_MAX_EXAMS_PER_DAY"


# Lowercased sort-criterion token -> SortCriterion, for case-insensitive parsing.
SORT_CRITERION_ALIASES: Dict[str, SortCriterion] = {
    criterion.value.lower(): criterion for criterion in SortCriterion
}


def normalize_sort_criterion(value: str) -> SortCriterion:
    """Convert a sort-criterion token into a SortCriterion, case-insensitively."""
    key = value.strip().lower()

    if key not in SORT_CRITERION_ALIASES:
        raise ValueError(f"Invalid sort criterion: {value}")

    return SORT_CRITERION_ALIASES[key]


@dataclass(frozen=True)
class SortRule:
    """A single SORT line: a criterion and its priority (1 = primary)."""

    priority: int
    criterion: SortCriterion


@dataclass(frozen=True)
class SortingConfig:
    """The parsed SORT block: an immutable, ordered collection of sort rules."""

    rules: tuple[SortRule, ...] = ()

    def criteria_in_order(self) -> List[SortCriterion]:
        """Return the sort criteria from primary to least significant."""
        ordered = sorted(self.rules, key=lambda rule: rule.priority)
        return [rule.criterion for rule in ordered]
