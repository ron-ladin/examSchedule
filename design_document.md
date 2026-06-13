# Design Document — Parts 3 & 4
**Project:** Syncademic — Exam Scheduler  
**Sprint:** 3 (Feature 3) + Feature 4  
**Date:** June 2026

---

## 1. Context

Syncademic follows **Clean Architecture (Ports & Adapters)**. The core invariant is:

```
UI / CLI → DesktopController → AppController → Interfaces ← Adapters / Domain
```

No PyQt6 inside `controller.py` or `engine/`. Domain and interface layers are frozen unless explicitly approved.

---

## 2. Feature 3: Threshold Filtering & Sorting

### 2.1 Problem

The CSP engine generates all conflict-free schedules. Not all of these are educationally desirable. Two quality requirements were added:

1. **Threshold filtering (spec §2):** Drop schedules that violate user-configured constraints (minimum gap between exams, maximum exams per day, etc.).
2. **Sorting (spec §3):** Rank remaining schedules by quality criteria so the best schedule appears first.

### 2.2 Domain Model

```
Settings
├── ThresholdSettings
│   └── entries: tuple[ThresholdEntry, ...]
│       └── ThresholdEntry(criterion: Criterion, enabled: bool, k: int)
└── SortingConfig
    └── rules: list[SortRule]
        └── SortRule(priority: int, criterion: SortCriterion)
```

Both are **immutable frozen dataclasses**, making them safe to pass across process boundaries (multiprocessing) and to compare with `==`.

### 2.3 New Interfaces

`src/domain/interfaces.py` — `IThresholdFilter`

```python
class IThresholdFilter(ABC):
    @staticmethod
    @abstractmethod
    def is_valid(schedule: Schedule, courses: List[Course], settings: ThresholdSettings) -> bool: ...
```

Lives in the domain layer so `AppController` (engine layer) can depend on it without importing adapters.

### 2.4 Wiring Decision

**Threshold filtering: lazy, in the iterator chain (before `_MemoryExporter`).**

Rationale: invalid schedules should never be materialised into RAM. The CSP generator yields schedules lazily; wrapping the iterator with a filter expression preserves O(stack depth) memory.

```python
# AppController.run() — per period
raw_iter = self._generator.generate_schedules(relevant_courses, period)
if self._threshold_filter is not None and self._threshold_settings is not None:
    schedules_by_period[period_key] = (
        s for s in raw_iter if self._threshold_filter.is_valid(s, rc, ts)
    )
```

**Sorting: post-materialisation, inside `_MemoryExporter`.**

Rationale: sorting requires a complete list. `_MemoryExporter` is the first point where the iterator is consumed into a list, making it the natural place to sort.

```python
# _MemoryExporter.export_schedules() — after list(islice(...))
collected = self._sort(collected, courses_list)
```

### 2.5 `DesktopController` additions

| Method | Description |
|--------|-------------|
| `apply_settings(settings)` | Store full `Settings` object (thresholds + sort) |
| `apply_sort(config)` | Update sort config only; does not restart generation |
| `load_settings(path)` | Load from `settings.txt` via `SettingsFileReader` |
| `resort(config)` | Re-rank cached threshold-valid results without regenerating |
| `cache_generated_results(...)` | Called by parent after subprocess generation; re-applies current sort in case it changed while generation was running |

**`_last_results` cache:** stores the threshold-valid, sorted results of the last `generate()` call so `resort()` can re-rank without re-running the CSP.

### 2.6 Settings File Format

```
THRESHOLD
MIN_DAYS_BETWEEN_MANDATORY_EXAMS, ON, 2
MIN_DAYS_BETWEEN_ANY_EXAMS, OFF, 1
MAX_ELECTIVE_COLLISIONS, ON, 0
MIN_DAYS_EXAM_PERIOD_SPREAD, ON, 5
MAX_EXAMS_PER_DAY, ON, 4

SORT
1, SORT_MIN_DAYS_MANDATORY
2, SORT_AVG_DAYS_ANY
```

Parsed by `SettingsFileReader` in `src/adapters/readers/`.

---

## 3. Feature 4: Classroom Assignment

### 3.1 Problem

Beyond scheduling exam *dates*, the university needs to assign *classrooms and time slots* for each exam and generate a proctor recommendation report.

### 3.2 Domain Model Additions

```
Classroom(room_id: str, capacity: int)
ProctorConfig(students_per_proctor: int)
    └── proctors_for(student_count: int) -> int  [= ceil(count / ratio)]
ClassroomAssignment(
    exam: CourseOffering,
    room: Classroom,
    slot: TimeSlot,
    date: date,
    students_assigned: int,
    proctor_count: int,
)
```

All are immutable frozen dataclasses with field-level validation.

### 3.3 Algorithm Design (SCRUM-266 — in progress)

`ClassroomAssigner` takes a `Schedule` (date assignments) and produces a mapping of `exam → list[ClassroomAssignment]`. The algorithm must handle:

1. **Splitting:** A single exam may be split across multiple rooms on the same date+slot if no single room has sufficient capacity.
2. **Cross-slot reuse:** If two exams share a date but are scheduled in different time slots, the same room may be used for both.
3. **Pre-check warning:** Before generation, warn if total available seat-hours across all rooms and slots for a day are unlikely to accommodate all exams. (Soft check — does not block generation.)
4. **Hard rejection:** If any single exam cannot be assigned (not enough total capacity across all rooms on its date), the entire `Schedule` is rejected (not included in results).

### 3.4 Wiring Plan (SCRUM-267)

```
generate() → _EngineController.run() → _MemoryExporter (materialises + sorts)
                                              ↓
                                    ClassroomAssigner.assign()
                                              ↓
                                    Reject schedules with unassignable exams
                                              ↓
                                    Augmented results returned to UI
```

Feature is **toggle-gated**: a `classroom_assignment_enabled: bool` flag in `DesktopController` must be `True` and all required inputs (classrooms file, time slots, proctor ratio) must be loaded before the assigner is called.

**Load More compatibility:** When `start_load_more_for_period()` is called for additional schedules, each new schedule also passes through `ClassroomAssigner` before being added to the display list.

### 3.5 ProctorReportExporter

Produces a text file per schedule, one section per exam day, showing:
- Exam name, room, slot, student count, proctor count
- Total proctors needed that day

Format to be defined in SCRUM-266.

### 3.6 Input Files

| File | Reader | Format |
|------|--------|--------|
| `Classrooms.txt` | `ClassroomFileReader` | `$$$$` delimited; room name + capacity |
| `proctor_config.txt` | `ProctorConfigReader` | `1:X` ratio on a single line |
| Time slots | UI entry / `SlotsFileReader` | comma-separated HH:MM, up to 3 per day |
| `courses.txt` (extended) | `CourseFileReader` (extended) | Extra `StudentCount` field per offering line |

---

## 4. Architecture Decisions

### AD-1: ThresholdFilter in domain, not engine

**Decision:** `ThresholdFilter` lives in `src/domain/`, not `src/engine/`.  
**Rationale:** The filter contains pure business logic (gap calculations, collision counts). Placing it in the domain layer keeps the engine independent of any concrete filtering strategy.

### AD-2: Lazy filtering via IThresholdFilter in AppController

**Decision:** `AppController` wraps generator iterators with a filter expression rather than materialising to filter.  
**Rationale:** Preserves the O(stack depth) memory guarantee of the lazy generator. A schedule that fails a threshold is never held in RAM beyond the stack frame where it is produced.

### AD-3: Sorting post-materialisation in _MemoryExporter

**Decision:** `SortingEngine.sort()` is called inside `_MemoryExporter.export_schedules()` after each period's schedules are collected into a list.  
**Rationale:** Sorting requires random access to the full list. The exporter is the first layer that holds a complete list, making it the minimal and correct location for sorting.

### AD-4: Feature 4 is toggle-gated

**Decision:** Classroom assignment is only active when explicitly enabled and all required inputs are present.  
**Rationale:** The base scheduling feature must remain fully functional without Feature 4 inputs. Toggle-gating also allows the UI to disable the Generate button when Feature 4 is on but inputs are incomplete.

### AD-5: `resort()` operates on cached results

**Decision:** Re-sorting does not re-run the CSP engine.  
**Rationale:** Re-running the engine for a sort change would be prohibitively expensive for large faculties. The threshold-valid schedules are cached in `_last_results` and can be re-ranked in O(n log n) without touching the engine.
