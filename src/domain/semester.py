"""
Domain Utility: Semester
-------------------------
Normalizes semester values used across the system.

Internal format:
    FALL
    SPRI
    SUMM

Accepted input examples:
    FALL, fall, Fall
    SPRI, spri, Spri
    SPRING, spring, Spring
    SUMM, summ, Summ
    SUMMER, summer, Summer

User display format:
    FALL
    SPRING
    SUMMER
"""

VALID_INTERNAL_SEMESTERS = {"FALL", "SPRI", "SUMM"}

SEMESTER_ALIASES = {
    "FALL": "FALL",
    "SPRI": "SPRI",
    "SPRING": "SPRI",
    "SUMM": "SUMM",
    "SUMMER": "SUMM",
}

SEMESTER_DISPLAY_NAMES = {
    "FALL": "FALL",
    "SPRI": "SPRING",
    "SUMM": "SUMMER",
}


def normalize_semester(value: str) -> str:
    """
    Convert semester input into the internal 4-letter format.

    Internal format is kept compatible with the assignment input format:
        FALL / SPRI / SUMM
    """
    normalized = value.strip().upper()

    if normalized not in SEMESTER_ALIASES:
        raise ValueError(f"Invalid semester: {value}")

    return SEMESTER_ALIASES[normalized]


def display_semester(value: str) -> str:
    """
    Convert internal semester format into user-facing output text.
    """
    semester = normalize_semester(value)
    return SEMESTER_DISPLAY_NAMES[semester]
