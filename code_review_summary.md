# Code Review Summary — Parts 3 & 4
**Project:** Syncademic — Exam Scheduler  
**Sprint:** 3 (Feature 3: Threshold Filter & Sort) + Feature 4 (Classroom Assignment)  
**Date:** June 2026  
**Reviewer:** Niv Mayost

---

## Overview

This document summarises code review findings for the features delivered in Sprint 3 and the Feature 4 scaffolding. Reviews were conducted across the domain layer, adapter layer, engine layer, and controller layer.

---

## Feature 3 — ThresholdFilter & SortingEngine

### `src/domain/threshold_filter.py`

**Strengths:**
- Clean separation of concern: one static method (`is_valid`) is the public API; all criterion checkers are internal module-level functions.
- Each checker (`_check_2_1` through `_check_2_5`) maps directly to spec sections 2.1–2.5, making the code auditable against requirements.
- Correctly excludes disabled criteria from evaluation.

**Issues found:**
- `_mandatory_dates_by_group` checks `requirement.strip().lower() != "obligatory"` but the rest of the codebase uses `"Obligatory"` (capital O) as the canonical form. Robust, but the inconsistency between the two string forms could cause silent bugs if the normalisation in readers changes.
- `_min_gap` will raise `ValueError` (from `combinations`) for an empty list. This is guarded upstream by `if len(dates) >= 2`, but the guard is duplicated in every caller instead of being inside `_min_gap`.

**Verdict:** Approved with minor notes.

---

### `src/domain/sorting_engine.py`

**Strengths:**
- Identical helper functions to `threshold_filter.py` (`_mandatory_dates_by_group`, `_all_dates_by_group`, `_elective_dates_by_group`) — shows consistency.
- Negated tuple key for `sorted()` is a clean way to get descending order without a custom comparator.

**Issues found:**
- **Code duplication:** `_mandatory_dates_by_group`, `_all_dates_by_group`, `_elective_dates_by_program`, `_min_gap`, and `_count_same_day_pairs` are duplicated verbatim between `threshold_filter.py` and `sorting_engine.py`. These should live in a shared `_schedule_metrics.py` helper. (Non-blocking for this sprint; tech debt item.)
- `_score_3_3` (elective collisions) returns a higher score for *more* collisions, meaning it ranks schedules with more collisions as "better." This is intentional per spec (higher score = ranked first, and spec says sort by this criterion), but is counter-intuitive. A comment explaining the descending-is-better convention would help future maintainers.
- `_avg_gap` divides by `len(pairs)` but `pairs` is a list of `combinations(dates, 2)` materialised twice. Could be computed in one pass.

**Verdict:** Approved with tech debt notes.

---

### `src/engine/schedule_validator.py`

**Strengths:**
- Thin adapter: a single `filter_schedules()` function that delegates all logic to `ThresholdFilter`. This is the correct pattern for wiring domain logic into the engine layer without coupling.
- Accepts an `Iterable[Schedule]` (not just `List`), making it compatible with lazy iterators.

**Issues found:** None.

**Verdict:** Approved.

---

### `src/adapters/readers/settings_file_reader.py`

**Strengths:**
- Block-based parsing with explicit state machine (THRESHOLD/SORT blocks) is easy to extend.
- Comprehensive validation: checks duplicate priorities, gaps in priority sequence, k=0 for positive-only criteria.

**Issues found:**
- Long `read()` method (approximately 100 lines). Consider extracting `_parse_threshold_line()` and `_parse_sort_line()` helper methods.
- Error messages use raw line content (good), but the line number is not reported, making debugging harder.

**Verdict:** Approved with suggestions.

---

### `src/controller.py` — SCRUM-261 Pipeline Integration

**Strengths:**
- `ThresholdFilter` is now wired lazily in the iterator chain inside `AppController`, which preserves the O(stack depth) memory guarantee — invalid schedules are never materialised.
- `SortingEngine` is applied post-materialisation inside `_MemoryExporter`, which is the correct point: sorting requires a complete list.
- `resort()` method allows re-ranking cached results without re-running the full CSP, which is important for responsiveness when the user changes sort order.

**Issues found:**
- The docstring in `controller.py` still says "Does NOT modify src/engine/app_controller.py" — now outdated since SCRUM-261 added the `threshold_filter` parameter to `AppController`.
- `_MemoryExporter._sort()` short-circuits on `not settings.sorting.rules`, but `SortingEngine.sort()` already handles an empty criteria list (returns a copy). The guard is not harmful but adds a code path to test.

**Verdict:** Approved.

---

## Feature 4 — Classroom Assignment (Scaffolding)

### Domain Models (`src/domain/`)

**`classroom.py`:** Clean immutable dataclass. Validation on both `room_id` (non-empty string) and `capacity` (positive int) is thorough.

**`proctor.py` / `ProctorConfig`:** `proctors_for(student_count)` correctly uses `ceil`. Guards against `bool` inputs (which are a subtype of `int` in Python) show attention to detail.

**`classroom_assignment.py`:** Immutable dataclass with full field validation. The `students_assigned <= room.capacity` invariant is enforced at construction time, which is the right place.

**Issues found:**
- `classroom_assignment.py` validates `students_assigned` against `room.capacity` but not against the sum of all assignments for that room across slots. The cross-slot uniqueness / reuse logic must be enforced at the `ClassroomAssigner` level (SCRUM-266).

**Verdict:** Approved.

---

### Readers (`src/adapters/readers/`)

**`classroom_file_reader.py`:** Correctly rejects duplicate room IDs, zero/negative capacity, and malformed records.

**`proctor_config_reader.py`:** Rejects all edge cases (missing colon, numerator ≠ 1, zero denominator, multiple lines).

**Issues found:** None.

**Verdict:** Approved.

---

## Open Issues / Tech Debt

| # | Severity | Description | File |
|---|----------|-------------|------|
| 1 | Low | Duplicated metric helpers between ThresholdFilter and SortingEngine | `threshold_filter.py`, `sorting_engine.py` |
| 2 | Low | Outdated docstring in controller.py after SCRUM-261 | `controller.py` |
| 3 | Low | `_min_gap` guard duplicated in every caller | `threshold_filter.py` |
| 4 | Info | `_MemoryExporter._sort()` guard is redundant | `controller.py` |
| 5 | Low | `settings_file_reader.py` does not report line numbers in error messages | `settings_file_reader.py` |

---

## Summary

All Feature 3 code is production-ready. Feature 4 domain models and readers are solid. The main remaining work is the `ClassroomAssigner` algorithm (SCRUM-266) and its pipeline wiring (SCRUM-267). Tech debt items are low severity and can be addressed in a future cleanup sprint.
