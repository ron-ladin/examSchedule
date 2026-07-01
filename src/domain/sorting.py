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

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum


class SortCriterion(Enum):
    """The five sort criteria, named after spec sections 3.1-3.5."""

    SORT_MIN_DAYS_MANDATORY = "SORT_MIN_DAYS_MANDATORY"
    SORT_AVG_DAYS_ANY = "SORT_AVG_DAYS_ANY"
    SORT_ELECTIVE_COLLISIONS = "SORT_ELECTIVE_COLLISIONS"
    SORT_EXAM_PERIOD_SPREAD = "SORT_EXAM_PERIOD_SPREAD"
    SORT_MAX_EXAMS_PER_DAY = "SORT_MAX_EXAMS_PER_DAY"


# Lowercased sort-criterion token -> SortCriterion, for case-insensitive parsing.
SORT_CRITERION_ALIASES: dict[str, SortCriterion] = {
    criterion.value.lower(): criterion for criterion in SortCriterion
}


def normalize_sort_criterion(value: str) -> SortCriterion:
    """Convert a sort-criterion token into a SortCriterion, case-insensitively."""
    key = value.strip().lower()

    if key not in SORT_CRITERION_ALIASES:
        raise ValueError(f"Invalid sort criterion: {value}")

    return SORT_CRITERION_ALIASES[key]


# Sort direction per criterion (single source of truth for every sort path).
#
# Per the SRS (stage 3, §3.1-3.5) ALL FIVE sort criteria are displayed in
# DESCENDING order of their score - including §3.3 ("בסדר יורד של מספר
# ההתנגשויות") and §3.5 ("בסדר יורד של מספר הבחינות המקסימלי"). So a higher
# score always ranks first and ASCENDING_CRITERIA is currently empty.
#
# The per-criterion direction mechanism is kept intentionally: a criterion can
# be flipped to "lowest score first" simply by adding it to this set, without
# touching SortingEngine or the SQLite ORDER BY path. It stays empty until a
# signed-off spec deviation says otherwise.
ASCENDING_CRITERIA: frozenset[SortCriterion] = frozenset()


def sorts_descending(criterion: SortCriterion) -> bool:
    """Return True if a higher score for *criterion* should rank first.

    False means lower-is-better (rank the smallest score first).
    """
    return criterion not in ASCENDING_CRITERIA


@dataclass(frozen=True)
class SortRule:
    """A single SORT line: a criterion and its priority (1 = primary)."""

    priority: int
    criterion: SortCriterion


@dataclass(frozen=True)
class SortingConfig:
    """The parsed SORT block: an immutable, ordered collection of sort rules."""

    rules: tuple[SortRule, ...] = ()

    def criteria_in_order(self) -> list[SortCriterion]:
        """Return the sort criteria from primary to least significant."""
        ordered = sorted(self.rules, key=lambda rule: rule.priority)
        return [rule.criterion for rule in ordered]

    @property
    def enabled_criteria(self) -> tuple[SortCriterion, ...]:
        """The enabled criteria as an ordered tuple (primary first).

        This is the UI-facing view of the config: a prioritized list where
        position 0 is priority 1. Mirrors ``criteria_in_order`` but returns an
        immutable tuple suitable for round-tripping through widgets.
        """
        return tuple(self.criteria_in_order())

    @classmethod
    def from_ordered_criteria(
        cls, criteria: Iterable[SortCriterion]
    ) -> "SortingConfig":
        """Build a config from an ordered list of criteria (priority 1 = first).

        Duplicate criteria are ignored after their first occurrence so the
        resulting priorities are always a clean 1..N sequence with no repeats.
        """
        seen: set[SortCriterion] = set()
        rules: list[SortRule] = []
        for criterion in criteria:
            if criterion in seen:
                continue
            seen.add(criterion)
            rules.append(SortRule(priority=len(rules) + 1, criterion=criterion))
        return cls(rules=tuple(rules))
