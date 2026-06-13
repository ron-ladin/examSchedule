# Tests Document — Parts 3 & 4
**Project:** Syncademic — Exam Scheduler  
**Sprint:** 3 (Feature 3) + Feature 4 Scaffolding  
**Date:** June 2026

---

## 1. Test Strategy

All tests are written with `pytest` and follow the project's **unit + e2e** two-layer model:

| Layer | Location | Scope |
|-------|----------|-------|
| Unit | `tests/unit/` | Single class/module in isolation; fakes/stubs for dependencies |
| End-to-end | `tests/e2e/` | Full file-to-schedule pipeline using real readers, engine, and exporter |

**Coverage target:** 85 % (excluding `src/ui/`).  
**Test runner:** `python3.11 -m pytest tests/unit/ tests/e2e/`  
**Headless UI:** `QT_QPA_PLATFORM=offscreen python3.11 -m pytest tests/unit/ tests/e2e/`

---

## 2. Feature 3 Test Coverage

### 2.1 ThresholdFilter — `tests/unit/test_threshold_filter.py` (35 tests)

Tests five threshold criteria (spec §2.1–2.5):

| Class | Tests | What is verified |
|-------|-------|-----------------|
| `TestMinDaysBetweenMandatoryExams` | 8 | Gap exactly k passes; gap < k fails; disabled criterion always passes; electives ignored; different programs/years not compared |
| `TestMinDaysBetweenAnyExams` | 5 | Elective-to-mandatory and elective-to-elective gaps; cross-program isolation |
| `TestMaxElectiveCollisions` | 7 | Collision count = k passes; > k fails; mandatory-elective collision not counted; same-day pair counting |
| `TestMinDaysExamPeriodSpread` | 5 | Spread exactly k; single mandatory exam (spread = 0) fails k ≥ 1; electives not counted |
| `TestMaxExamsPerDay` | 5 | Day count = k passes; day count > k fails; mixed mandatory/elective counted together |
| `TestMultipleCriteriaActive` | 4 | All criteria pass; one failing criterion invalidates; empty settings always passes; unassigned courses neutral |

**Key design decisions tested:**
- Disabled criteria are transparent (pass-through).
- Cross-programme and cross-year pairs are never compared (spec §2.1–2.2).
- Elective-to-mandatory pairs are not counted as elective collisions (spec §2.3).

---

### 2.2 `IThresholdFilter` Interface — `tests/unit/test_threshold_filter_interface.py` (2 tests)

Verifies that `ThresholdFilter` satisfies the `IThresholdFilter` contract and that `is_valid` is callable as a static method.

---

### 2.3 SortingEngine — `tests/unit/test_sorting_engine.py` (18 tests)

| Class | Tests | What is verified |
|-------|-------|-----------------|
| `TestSortMinDaysMandatory` | 3 | Larger min gap ranks first; equal gaps; three-schedule ordering |
| `TestSortAvgDaysAny` | 2 | Higher average gap ranks first; electives included |
| `TestSortElectiveCollisions` | 2 | More collisions ranks first; zero collisions ranks last |
| `TestSortExamPeriodSpread` | 2 | Wider spread ranks first; electives not counted |
| `TestSortMaxExamsPerDay` | 2 | Higher day load ranks first |
| `TestMultiLevelSort` | 3 | Primary sort + tiebreaker; primary overrides secondary; all five criteria in priority order |
| `TestEdgeCases` | 4 | Empty list returns empty; single schedule unchanged; empty config preserves input order; input list not mutated |

---

### 2.4 ScheduleValidator — `tests/unit/test_schedule_validator.py` (4 tests)

Tests the engine-level `filter_schedules()` wrapper:

- Drops schedules violating an enabled threshold.
- Keeps all schedules when criterion is disabled.
- Keeps all schedules when no thresholds configured (empty `ThresholdSettings`).
- Returns a new list without mutating the input.

---

### 2.5 SettingsFileReader — `tests/unit/test_settings_file_reader.py` (18 tests)

Covers both the happy path and all validation error paths:

**Happy path:**
- Full THRESHOLD + SORT block parses correctly.
- `OFF` entry is disabled in parsed output.
- Case-insensitive criterion names; whitespace tolerance.
- SORT block is optional (no sort rules = empty `SortingConfig`).
- Sort rules ordered by priority, not by appearance.

**Validation errors (each tested to raise `ValueError`):**
- Unknown criterion name.
- Invalid toggle (not `ON`/`OFF`).
- Non-integer k.
- Wrong field count in THRESHOLD line.
- Missing THRESHOLD block header.
- Unknown sort criterion.
- Line outside any block.
- Missing file.
- Elective collisions allows k = 0 (spec §2.3).
- k = 0 for a positive-only criterion raises.
- Empty THRESHOLD block raises.
- Priority gap (e.g., 1, 3 — skipping 2) raises.
- Priority = 0 raises.
- Negative k raises.

---

### 2.6 Sprint 3 Integration — `tests/unit/test_controller_sprint3_integration.py` (6 tests)

End-to-end controller integration tests:

| Test | What is verified |
|------|-----------------|
| `test_generate_keeps_all_schedules_when_thresholds_off` | All schedules returned when all criteria disabled |
| `test_generate_rejects_schedules_violating_enabled_threshold` | Schedules violating MIN_DAYS_BETWEEN_MANDATORY_EXAMS are filtered |
| `test_generate_sorts_descending_by_active_config` | Schedules sorted by SORT_MIN_DAYS_MANDATORY in descending gap order |
| `test_generation_process_applies_thresholds_and_sorting_settings` | Subprocess path (`_run_generation_process`) applies settings |
| `test_resort_reorders_cached_results_without_regenerating` | `resort()` re-ranks without re-running the CSP |
| `test_resort_raises_when_no_cached_results` | `resort()` raises if called before `generate()` |

---

### 2.7 AppController Filter Wiring — `tests/unit/test_app_controller.py` (4 new tests, SCRUM-261)

| Test | What is verified |
|------|-----------------|
| `test_threshold_filter_drops_invalid_schedules_from_iterator` | Reject-all filter results in empty schedule list per period |
| `test_threshold_filter_accept_all_passes_every_schedule_through` | Accept-all filter leaves schedules unchanged |
| `test_no_threshold_filter_passes_all_schedules_unchanged` | `threshold_filter=None` is a safe no-op |
| `test_threshold_filter_only_applied_when_both_filter_and_settings_provided` | Filter is skipped when `threshold_settings=None` |

---

### 2.8 DesktopController Filter+Sort — `tests/unit/test_desktop_controller.py` (2 new tests, SCRUM-261)

| Test | What is verified |
|------|-----------------|
| `test_generate_applies_threshold_filter_and_excludes_invalid_schedules` | Strict threshold (k=5, 4-day window) excludes all 20 raw schedules |
| `test_generate_sorting_orders_schedules_by_active_sort_rule` | `SORT_MIN_DAYS_MANDATORY` produces descending gap order across 6 schedules |

---

## 3. Feature 4 Test Coverage

### 3.1 Domain Models — `tests/unit/test_feature4_domain.py` (16 tests)

| Entity | Tests |
|--------|-------|
| `Classroom` | Holds fields; rejects zero/negative/bool capacity; rejects empty/non-string room_id; immutable |
| Time slot validation | Rejects unsorted middle time slot |
| `ClassroomAssignment` | Holds fields; allows full room; rejects overfilled, negative students, negative proctor count, bool values; immutable |

### 3.2 ClassroomFileReader — `tests/unit/test_classroom_file_reader.py` (14 tests)

- Reads single and multiple rooms; free-text room names; whitespace tolerance.
- Rejects: zero/negative/non-integer capacity; missing capacity; extra line; duplicate IDs; empty file; missing file.

### 3.3 ProctorConfigReader — `tests/unit/test_proctor_config_reader.py` (16 tests)

- Reads valid ratio; `proctors_for()` rounds up; whitespace tolerance.
- Rejects: missing colon; numerator ≠ 1; non-integer denominator; empty denominator; extra parts; multiple lines; empty file; missing file; zero denominator; zero students_per_proctor; bool students_per_proctor.
- Edge cases: ratio 1:1; proctors_for(0) = 0; proctors_for(negative) raises.

---

## 4. Total Test Count

| Test file | Tests | Feature |
|-----------|-------|---------|
| `test_threshold_filter.py` | 35 | Feature 3 |
| `test_threshold_filter_interface.py` | 2 | Feature 3 |
| `test_sorting_engine.py` | 18 | Feature 3 |
| `test_schedule_validator.py` | 4 | Feature 3 |
| `test_settings_file_reader.py` | 18 | Feature 3 |
| `test_controller_sprint3_integration.py` | 6 | Feature 3 (pipeline) |
| `test_app_controller.py` (new) | 4 | SCRUM-261 |
| `test_desktop_controller.py` (new) | 2 | SCRUM-261 |
| `test_feature4_domain.py` | 16 | Feature 4 |
| `test_classroom_file_reader.py` | 14 | Feature 4 |
| `test_proctor_config_reader.py` | 16 | Feature 4 |
| **Total (parts 3+4)** | **135** | |
| **Project total** | **384+** | All features |

---

## 5. Pending Tests (SCRUM-266, SCRUM-267, SCRUM-269)

The following test modules are planned but not yet written (blocked on ClassroomAssigner implementation):

- `tests/unit/test_classroom_assigner.py` — basic assignment, splitting across rooms, cross-slot reuse, capacity boundary, hard rejection when unassignable
- `tests/unit/test_proctor_report_exporter.py` — report format, proctor count calculation, file output
- Additional `test_desktop_controller.py` cases for the feature-toggle path (SCRUM-267)
