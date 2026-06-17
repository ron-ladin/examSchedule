# Sprint 3 + Feature 4 Summary
**Project:** Syncademic — Exam Scheduler  
**Date:** June 2026

---

## Sprint 3 Goals

Sprint 3 extended the scheduling engine with two Quality-of-Life features for generated schedules:

- **Feature 3:** Threshold filtering and sorting (spec §2 and §3)
- **Feature 4:** Classroom assignment and proctor reporting (spec §4)

---

## Feature 3: Threshold Filtering & Sorting — COMPLETE

### What was built

| Story | Description | Status |
|-------|-------------|--------|
| SCRUM-258 | Core domain models (Sections 2+3) | ✅ Done |
| SCRUM-259 | Filter & Sort Engine | ✅ Done (merged PR #78) |
| SCRUM-260 | SettingsFileReader (CLI) | ✅ Done |
| SCRUM-261 | Pipeline Integration | 🔄 PR #80 under review |
| SCRUM-262 | UI: Settings Screen | ✅ Done |
| SCRUM-263 | Tests: ThresholdFilter & SortingEngine | ✅ Done |

### ThresholdFilter

Validates a generated schedule against up to 5 configurable criteria (spec §2.1–2.5):

| Criterion | Spec | Description |
|-----------|------|-------------|
| `MIN_DAYS_BETWEEN_MANDATORY_EXAMS` | §2.1 | Minimum gap between mandatory exams in the same programme/year |
| `MIN_DAYS_BETWEEN_ANY_EXAMS` | §2.2 | Minimum gap between any two exams (including electives) |
| `MAX_ELECTIVE_COLLISIONS` | §2.3 | Maximum elective-elective same-day collisions |
| `MIN_DAYS_EXAM_PERIOD_SPREAD` | §2.4 | Minimum spread (last − first mandatory exam) |
| `MAX_EXAMS_PER_DAY` | §2.5 | Maximum total exams on any single calendar day |

Each criterion can be individually enabled/disabled and configured via `settings.txt`.

### SortingEngine

Ranks valid schedules by up to 5 criteria (spec §3.1–3.5) in user-defined priority order. All criteria are descending (higher score = ranked first).

### Settings File

Users configure thresholds and sort order via `settings.txt`:
```
THRESHOLD
MIN_DAYS_BETWEEN_MANDATORY_EXAMS, ON, 2
MAX_EXAMS_PER_DAY, ON, 4

SORT
1, SORT_MIN_DAYS_MANDATORY
2, SORT_AVG_DAYS_ANY
```

### Pipeline Wiring (SCRUM-261 — PR #80, not yet merged)

> **⚠️ The wiring described below is proposed in PR #80 and not yet on develop.**
> The currently merged architecture filters post-materialisation in `controller.py`.

- ThresholdFilter is wired **lazily** in the iterator chain inside `AppController` — invalid schedules are never materialised into RAM.
- SortingEngine is applied **post-materialisation** inside `_MemoryExporter` — after the schedule list is collected.
- `resort()` method in `DesktopController` allows re-ranking cached results without re-running the CSP engine.

---

## Feature 4: Classroom Assignment — IN PROGRESS

### What was built

| Story | Description | Status |
|-------|-------------|--------|
| SCRUM-264 | Domain Extensions (Feature 4) | ✅ Done |
| SCRUM-265 | File I/O: Classroom Readers | ✅ Done |
| SCRUM-266 | Assignment Engine: ClassroomAssigner | 🔄 In Progress |
| SCRUM-267 | Pipeline Integration (Feature 4) | ⏳ Blocked by SCRUM-266 |
| SCRUM-268 | UI: Feature 4 Screens | ⏳ To Do |
| SCRUM-269 | Tests: ClassroomAssigner & Adapters | ⏳ To Do |

### Domain Models Added

- **`Classroom`** — room ID + capacity (immutable, validated)
- **`ProctorConfig`** — 1:X proctor-to-student ratio; `proctors_for(n)` = ⌈n/X⌉
- **`ClassroomAssignment`** — links one exam to one room in one time slot on one date, with student count and proctor count

### Readers Added

- **`ClassroomFileReader`** — parses `Classrooms.txt` (name + capacity per record)
- **`ProctorConfigReader`** — parses `1:X` ratio from a single-line file
- **`SlotsFileReader`** — parses comma-separated exam time slots (up to 3 per day, min 4 h apart)

### Algorithm Design (pending SCRUM-266)

`ClassroomAssigner.assign(schedule, classrooms, slots, proctor_config)`:
1. For each exam in the schedule, determine total student count from all relevant offerings.
2. Try to assign students to rooms on the exam date, splitting across multiple rooms if needed.
3. Allow cross-slot room reuse (same room, different time slot, same date).
4. Hard-reject any schedule where a single exam cannot be fully assigned.
5. Emit a pre-generation warning if total seat capacity looks insufficient.

---

## Known Limitations

1. **No cross-platform testing.** All development and CI has been on Linux. macOS rendering differences in QSS and font metrics have not been audited.

---

## Metrics

| Metric | Value | Notes |
|--------|-------|-------|
| Total tests (measured) | 456 | `python -m pytest -q` on 2026-06-17 |
| Feature 3+4 tests (measured) | 172+ | see §4 breakdown in tests_document |
| Test coverage (excl. `src/ui/`) | ≥ 85 % | enforced via `pytest --cov=src` gate |
| Pylint score (measured) | 7.63 / 10 | target 8.5; delta from E1131 false positives (pylint version) + R0904 backlog |
| Open bugs | 0 | |
| Open tech debt items | 3 (low severity) | |
