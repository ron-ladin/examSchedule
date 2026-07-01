"""
Merge utilities for in-memory list/dict operations.

Shared by DesktopController for replace / append / update strategies.
"""

import logging
from collections.abc import Callable

from src.domain.course import Course
from src.domain.semester import normalize_semester

logger = logging.getLogger(__name__)


def merge_by_key(
    existing: list,
    new_items: list,
    mode: str,
    key_fn: Callable,
) -> None:
    """Apply replace / append / update merge strategy to an in-memory list."""
    if mode == "replace":
        existing.clear()
        existing.extend(new_items)

    elif mode == "append":
        existing.extend(new_items)

    elif mode == "update":
        key_to_idx: dict[str, int] = {
            key_fn(item): i for i, item in enumerate(existing)
        }
        seen_new: set[str] = set()

        for item in new_items:
            key = key_fn(item)

            if key in seen_new:
                logger.warning(
                    "merge_by_key: duplicate key '%s' in new items — "
                    "last occurrence kept",
                    key,
                )

            seen_new.add(key)

            if key in key_to_idx:
                existing[key_to_idx[key]] = item
            else:
                existing.append(item)
                key_to_idx[key] = len(existing) - 1
    else:
        raise ValueError(
            f"Unknown merge mode: '{mode}'. Use replace, append, or update."
        )


def update_merge_courses(existing: list[Course], new_courses: list[Course]) -> None:
    """Update mode: merge offerings into existing courses; add unknown courses."""
    existing_by_id: dict[str, Course] = {c.id: c for c in existing}

    for new_course in new_courses:
        if new_course.id in existing_by_id:
            existing_course = existing_by_id[new_course.id]
            existing_keys = {
                (o.program_id, o.year, normalize_semester(o.semester))
                for o in existing_course.offerings
            }

            for offering in new_course.offerings:
                key = (
                    offering.program_id,
                    offering.year,
                    normalize_semester(offering.semester),
                )

                if key not in existing_keys:
                    existing_course.add_offering(offering)
                    existing_keys.add(key)
        else:
            existing.append(new_course)
            existing_by_id[new_course.id] = new_course
