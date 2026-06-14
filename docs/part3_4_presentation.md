# Sprint 3 + Feature 4 Presentation Outline
**Project:** Syncademic — Exam Scheduler  
**Audience:** Course instructors + peers  
**Duration:** ~15 minutes

---

## Slide 1 — Title

**Syncademic**  
*Intelligent Exam Scheduling*  
Sprint 3 Demo — Parts 3 & 4

Team members | Date

---

## Slide 2 — Recap: What We Had After Sprint 2

- PyQt6 desktop app with full file-loading UI
- CSP backtracking engine with MCV heuristic generates all conflict-free schedules
- Calendar view, Prev/Next navigation, export to file
- Up to 5 study programmes, lazy generation (no memory blowout)

**The gap:** the engine generated *all valid schedules* — potentially thousands. Users had no way to filter out low-quality ones or find the best one.

---

## Slide 3 — Feature 3: The Problem

> "We generate 10,000 schedules. Which one should the student council choose?"

Pain points:
- Two exams back-to-back on consecutive days
- Six exams crammed into one week, none spread out
- No easy way to spot the "best" schedule

---

## Slide 4 — Feature 3: Threshold Filtering (Spec §2)

**Five configurable quality thresholds — all optional, all user-controlled:**

| Criterion | Example |
|-----------|---------|
| Min days between mandatory exams | ≥ 2 days |
| Min days between any exams | ≥ 1 day |
| Max elective collisions same day | ≤ 1 |
| Min exam period spread | ≥ 5 days |
| Max exams on any single day | ≤ 4 |

Schedules that violate an *enabled* criterion are silently dropped — users only see schedules that meet their standards.

**Key design:** filtering happens *lazily* inside the generator iterator. An invalid schedule is never stored in memory.

---

## Slide 5 — Feature 3: Sorting (Spec §3)

**Five sort criteria — user picks the priority:**

| Criterion | Meaning |
|-----------|---------|
| Min days between mandatory | How well-spread are mandatory exams? |
| Avg days between any exams | Overall breathing room for students |
| Elective collisions | How many elective clashes? |
| Exam period spread | How spread is the entire exam season? |
| Max exams per day | What's the worst single day? |

The schedule ranked #1 is the one best matching the faculty's values.

---

## Slide 6 — Feature 3: Settings File

```
THRESHOLD
MIN_DAYS_BETWEEN_MANDATORY_EXAMS, ON, 2
MAX_ELECTIVE_COLLISIONS, ON, 0
MAX_EXAMS_PER_DAY, ON, 4

SORT
1, SORT_MIN_DAYS_MANDATORY
2, SORT_AVG_DAYS_ANY
```

- Loaded from `settings.txt` or configured in the Settings screen
- All criteria have sensible defaults (disabled) — no breaking changes for existing users

---

## Slide 7 — Architecture: Where the Code Lives

> **⚠️ Proposed (PR #80 — not yet merged):** The lazy `AppController` wiring shown
> below is the design from SCRUM-261. The currently merged code filters
> post-materialisation in `controller.py`. This slide reflects the target architecture.

```
AppController.run()
    └─ generator.generate_schedules()     ← CSP engine (unchanged)
        └─ _apply_filter(iter, ...)       ← LAZY ThresholdFilter (PR #80, SCRUM-261)
            └─ _MemoryExporter
                └─ list(islice(iter))     ← materialise only valid schedules
                    └─ SortingEngine.sort()   ← sort post-materialisation
                                               (new, SCRUM-261)
```

Clean Architecture maintained — no PyQt6 in engine or controller.

---

## Slide 8 — DEMO: Feature 3

*(Live demo or screenshot walkthrough)*

1. Open Settings screen → configure thresholds and sort order
2. Generate schedules
3. Show Schedule #1 — best ranked schedule
4. Disable all thresholds → count increases (more schedules shown)
5. Change sort order → instant re-ranking (no regeneration)

---

## Slide 9 — Feature 4: The Next Challenge

> "OK, we have a date for each exam. But which *room* and *time*?"

**Feature 4: Classroom Assignment (spec §4)**

When enabled:
- Assigns classrooms and time slots to every exam
- Handles large exams by splitting across multiple rooms
- Generates a Proctor Recommendation Report per schedule

---

## Slide 10 — Feature 4: New Inputs

| Input | File | What it contains |
|-------|------|-----------------|
| Classrooms | `Classrooms.txt` | Room ID + capacity |
| Exam time slots | UI / `Slots.txt` | Up to 3 time slots per day (e.g. 9:00, 13:00) |
| Proctor ratio | `proctor_config.txt` | `1:X` ratio |
| Student counts | `courses.txt` (extended) | Added per-programme student count |

Feature is optional and toggle-gated — existing workflow unchanged when off.

---

## Slide 11 — Feature 4: Algorithm Overview

`ClassroomAssigner.assign(schedule, classrooms, slots, proctor_config)`:

1. For each exam: look up total student count
2. Find the exam's date and try to fill rooms (largest first) in one slot
3. If no single room fits: split across multiple rooms, same date+slot
4. Allow a room already used in an earlier slot to be reused in a later slot
5. If any exam cannot be assigned at all: **reject the schedule entirely**
6. Generate proctor counts: `proctors_per_room = ⌈students / ratio⌉`

---

## Slide 12 — Feature 4: Progress

| Story | Status |
|-------|--------|
| Domain models (Classroom, Proctor, Assignment) | ✅ Done |
| File readers (Classrooms, Proctor, Slots) | ✅ Done |
| ClassroomAssigner algorithm | 🔄 In progress |
| Pipeline wiring | ⏳ Blocked |
| UI: Feature 4 inputs + proctor report | ⏳ Planned |
| Tests: ClassroomAssigner | ⏳ Planned |

---

## Slide 13 — Testing

- **384 tests** — all pass, 0 failures
- **≥ 85 % coverage** (excluding UI layer)
- New tests for Feature 3: threshold criteria, sorting engine, settings reader, pipeline integration
- New tests for Feature 4 scaffolding: classroom/proctor domain validation, file readers

Testing philosophy:
- Unit tests use fakes and stubs — no real files, no database
- E2E tests use real file readers and real engine
- UI tests run headless via `QT_QPA_PLATFORM=offscreen`

---

## Slide 14 — What's Next

- Complete `ClassroomAssigner` (SCRUM-266)
- Wire classroom assignment into the pipeline (SCRUM-267)
- UI: Feature 4 inputs and proctor report dialog (SCRUM-268)
- Tests for ClassroomAssigner and adapters (SCRUM-269)

---

## Slide 15 — Q&A

Questions?

*GitHub:* ron-ladin/examSchedule  
*Jira:* aloni267.atlassian.net — SCRUM board
