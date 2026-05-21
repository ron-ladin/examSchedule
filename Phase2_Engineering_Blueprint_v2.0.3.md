# examSchedule v2.0 — Phase 2 Engineering Blueprint

**Enterprise-Grade Architectural Blueprint · Jira Epic Breakdown · Team Delegation Matrix**

| Field | Value |
|---|---|
| Document status | **Master Blueprint — v2.0.3 (Senior Review Integration)** |
| Date | 2026-05-22 |
| Version | 2.0.3-reviewed |
| Authors | Alon Cohen (Team Lead & Integration Architect) |
| Methodology | Agile / Scrum · Clean Architecture · Ports & Adapters · REST/SPA |
| Previous version | 2.0.2-master |
| Change reason | Integration of senior engineering review: 3 critical issues fixed, 5 gaps addressed, 7 new Jira tasks created (SCRUM-128–134) |

---

## What Changed in This Version (Senior Review Integration)

This version incorporates a full senior engineering review conducted before Sprint 1 coding begins.
The review identified 3 critical pre-sprint blockers and 5 gaps. All are resolved below.

| Issue | Severity | Resolution | Jira |
|---|---|---|---|
| AppController materialises schedules into `list()`, destroying O(n) memory guarantee | **Critical** | Code fixed: `list()` removed, `Dict[str, Iterator[Schedule]]` passed directly | SCRUM-128 (Ron) |
| `IOutputExporter` interface used `List[Schedule]` — incompatible with `PaginatedExporter` streaming | **Critical** | Code fixed: interface updated to `Iterator[Schedule]`; all implementors updated | SCRUM-129 (Alon) |
| No generation timeout — hung runs leave session stuck in `"running"` forever | **Critical** | New task: `asyncio.wait_for` with configurable timeout + clean failure path | SCRUM-130 (Ron) |
| Race condition: double-click on Generate fires two concurrent background tasks | **Gap** | New task: atomic check-and-set guard, returns HTTP 409 on duplicate | SCRUM-131 (Alon) |
| CORS hardcoded as `localhost:5173` — breaks on any other port or machine | **Gap** | New task: pydantic-settings config module; CORS loaded from `.env` | SCRUM-132 (Lotem) |
| `build_controller()` selected_programs injection note missing from task | **Gap** | Already in SCRUM-66 description — confirmed present, no change needed | SCRUM-66 |
| `IScheduleGenerator` interface stability not explicitly confirmed | **Gap** | Interface confirmed stable (`Iterator[Schedule]` return, unchanged) | confirmed |
| Lotem's User Manual had no explicit "UI done" prerequisite | **Gap** | Already in SCRUM-113 — sequenced as post-UI, Sprint 2 only | SCRUM-113 |
| Lotem had no implementation task at sprint start | **Gap** | SCRUM-132, SCRUM-133, SCRUM-134 added: 3 concrete implementation tasks at sprint start | SCRUM-132/133/134 (Lotem) |

---

## Table of Contents

1. Executive Summary
2. Phase 2 Requirements Analysis
3. Architectural Blueprint & Technology Stack
4. API Contract & DTO Specification
5. Pagination & Memory Architecture *(includes Critical Issue #1/#2 fix)*
6. Dependency-Injection Integration Map *(includes timeout + atomic guard)*
7. UI/UX Screen Design
8. Jira Epic & Granular Story Breakdown *(updated with SCRUM-128–134)*
9. CI/CD Pipeline & Definition of Done
10. Strategic Team Delegation Matrix *(Lotem updated)*
11. Sprint Plan *(updated with new tasks)*
12. Risk Register *(updated: SRS 5.2 now ✓)*
13. Correctness Properties

---

## 1. Executive Summary

examSchedule v1.0 is a production-quality CLI scheduling engine built on a strict five-layer Clean Architecture (Domain → Interfaces → Adapters → Engine → CLI). All 84 tests pass. The engine is fully decoupled from I/O through abstract ports (`IDataProvider`, `IOutputExporter`, `IScheduleGenerator`, `IConflictStrategy`), with all concrete collaborators assembled exclusively in `main.py` via dependency injection.

Phase 2 introduces a full visual application layer via a **Client-Server Web Architecture**: a FastAPI backend wrapping the v1.0 engine, and a React + Tailwind CSS SPA as the presentation layer. The v1.0 engine, Domain, Interfaces, and all existing Adapters receive **zero modifications** (except for the interface signature fix for `IOutputExporter` — see §5).

### Kiro Architectural Review — Merge Decisions (v2.0.2)

**Adopted from Kiro:** UUID Session Management (§6.1), Async Status Polling endpoint (§4.3), Correctness Properties (§13).

**Explicitly rejected from Kiro:**
- **Kiro's `InMemoryExporter`:** Rejected. Calls `list()` on the schedule generator, destroying the O(n) memory guarantee. `PaginatedExporter` (§5) is retained.
- **Kiro's Lotem/Pydantic schemas delegation:** Rejected. Pydantic schemas are on the critical path — assigned to Ron.
- **Kiro's CI/CD omission:** Our GitHub Actions `ci.yml`, Pylint gate, coverage gate, and DoD are retained in full.
- **Kiro's v3.0 future-proofing omission:** Reserved `sort_by`/`filter_prog` params and React Query key architecture retained.

### Senior Engineering Review — Integration (v2.0.3)

All critical issues and gaps identified in the senior review have been resolved. Source code fixes have been applied to `app_controller.py` and `i_output_exporter.py`. Five new Jira tasks (SCRUM-128–132) have been created. SCRUM-59 has been updated. Full details in §5, §6, and §8.

---

## 2. Phase 2 Requirements Analysis

### 2.1 Input Screen Requirements

| Req. ID | Requirement | Client-Server Engineering Concern |
|---|---|---|
| 2.1 | User defines courses and dates file paths | React file-upload form → `POST /api/data/upload` |
| 2.1.1 | Load data from files via button | Multipart form upload; FastAPI reads file bytes; `GUIDataProvider` parses them |
| 2.1.2 | Replace stored data with new file | `PUT /api/data/courses` — full state replacement on server side |
| 2.1.3 | Additively update data from a new file | `PATCH /api/data/courses` — merge without deleting existing records |
| 2.2 | Select up to 5 study programmes from a dynamic list | `GET /api/programmes` returns list; React multi-select, max 5, validated client + server |
| 2.3.1 | Display selected programmes (ID + name) | `ProgrammeDTO` in response payload |
| 2.3.2 | Drill-down per programme: courses by year/semester | `GET /api/programmes/{id}/courses → CourseDetailDTO` |
| 2.4.1 | Calendar view of the exam period with current state | `GET /api/periods → ExamPeriodDTO`; React renders calendar from JSON |
| 2.4.2 | Toggle day exclusion/inclusion per day | `PATCH /api/periods/{key}/exclusions` |
| 2.4.3 | Adjust start/end of exam period per semester | `PATCH /api/periods/{key}/range` |
| 2.5 | Filters and sorts | Out of scope v2.0 — deferred to v3.0 |

### 2.2 Output Screen Requirements

| Req. ID | Requirement | Client-Server Engineering Concern |
|---|---|---|
| 3.1 | Calendar view of one schedule at a time | `GET /api/schedules?page=1&size=1 → React renders ScheduleDTO as calendar` |
| 3.2 | Navigation bar — next/previous | React pagination state; page query param sent to API |
| 3.3 | Show total count + current ordinal ("X of Y") | `X-Total-Count` response header on paginated endpoint |
| 3.4 | Exam slot: course ID, name, mandatory/elective, programme | `ExamSlotDTO` nested in `ScheduleDTO` |
| 3.5 | Save selected schedule to a readable file | `GET /api/schedules/{id}/export → FastAPI streams a .txt file download` |

### 2.3 Non-Functional Requirements

| Req. ID | Requirement | Target |
|---|---|---|
| 5.1 | Internal data persistence — avoid re-reading unchanged files | JSON cache keyed by file mtime; managed server-side |
| 5.2 | UI responsiveness — no stalls > 1 second | FastAPI BackgroundTasks + streaming pagination; **generation timeout via `asyncio.wait_for` (SCRUM-130)** |

---

## 3. Architectural Blueprint & Technology Stack

### 3.1 Web Architecture Rationale

The pivot from PyQt6 to FastAPI + React enforces Clean Architecture via the physical HTTP boundary — React literally cannot import Python engine code. Full rationale in the v2.0.2 document.

### 3.2 System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER — React SPA  (TypeScript + Tailwind CSS)             │
│  InputScreen.tsx  OutputScreen.tsx  Toast.tsx  ErrorBoundary.tsx         │
│  ProgrammePanel.tsx  ScheduleCalendar.tsx  ExamPeriodCalendar.tsx        │
│  NavigationBar.tsx   api/client.ts                                       │
│  State: Zustand / React Query · Build: Vite · Port: 5173                 │
└───────────────────────────┬──────────────────────────────────────────────┘
                            │  HTTP / JSON  (fetch API)
                            │  X-Total-Count header · X-Session-ID header
┌───────────────────────────▼──────────────────────────────────────────────┐
│  API LAYER — FastAPI  (Python 3)                                         │
│  src/api/                                                                │
│    config.py        ← pydantic-settings: CORS origins, timeout, port    │  ← NEW (SCRUM-132)
│    main.py          ← FastAPI app, CORS from settings, lifespan          │
│    routes/data.py · programmes.py · periods.py · schedules.py · generate │
│    schemas/         ← Pydantic DTOs (programme, period, schedule, error) │
│    dependencies.py  ← FastAPI Depends() DI wiring; atomic guard          │  ← updated (SCRUM-131)
│    session_store.py ← UUID SessionStore + SessionState                   │
│    exceptions.py    ← Global exception handler + custom exception types  │
│  Port: 8000 · Uvicorn ASGI                                               │
├──────────────────────────────────────────────────────────────────────────┤
│  ENGINE LAYER — MINIMAL CHANGES  (src/engine/)                           │
│  AppController  ← passes Iterator[Schedule], NOT list()  [SCRUM-128]    │  ← FIXED
│  ScheduleGenerator                                                       │
├──────────────────────────────────────────────────────────────────────────┤
│  INTERFACES LAYER — ONE SIGNATURE CHANGE  (src/interfaces/)              │
│  IOutputExporter  ← Dict[str, Iterator[Schedule]]  [SCRUM-129]          │  ← FIXED
│  IDataProvider · IScheduleGenerator · IConflictStrategy                 │
├──────────────────────────────────────────────────────────────────────────┤
│  ADAPTERS LAYER — Existing + NEW additions  (src/adapters/)              │
│  Existing (untouched): FileDataProvider · TextFileExporter (updated sig) │
│                        ExactConflictStrategy · all readers               │
│  NEW: SessionDataProvider · PaginatedExporter · JsonCacheAdapter         │
├──────────────────────────────────────────────────────────────────────────┤
│  DOMAIN LAYER — ZERO CHANGES  (src/domain/)                              │
│  Course · CourseOffering · ExamPeriod · Schedule · Semester              │
└──────────────────────────────────────────────────────────────────────────┘
  Dependency rule: Every arrow points inward only.
```

### 3.3 Technology Stack

| Layer | Technology | Version | Rationale |
|---|---|---|---|
| Frontend framework | React | 18.x | Component model + React Query |
| Frontend styling | Tailwind CSS | 3.x | Utility-first; responsive calendar grids |
| Frontend build | Vite | 5.x | Sub-second HMR; TypeScript first-class |
| Frontend state | Zustand + React Query | Latest | Lightweight global state + server-state caching |
| Backend framework | FastAPI | 0.115.x | Async, OpenAPI auto-docs, native Pydantic v2 |
| Backend server | Uvicorn | 0.30.x | ASGI server |
| DTO validation | Pydantic v2 | 2.7.x | Compile-time and runtime validation |
| Config management | pydantic-settings | Latest | `.env`-based config; CORS, timeout, port *(SCRUM-132)* |
| Testing | pytest + FastAPI TestClient | Latest | In-process HTTP; no display server |
| CI/CD | GitHub Actions | Latest | Zero infrastructure |
| Linting | Pylint | 3.x | Enforced at ≥ 8.5/10 in CI |

---

## 4. API Contract & DTO Specification

### 4.1 DTO Hierarchy

```
src/api/schemas/
  programme.py   → ProgrammeDTO, ProgrammeListDTO, CourseDetailDTO
  period.py      → ExamPeriodDTO, DateRangeDTO, ExclusionPatchDTO, RangePatchDTO
  schedule.py    → ScheduleDTO, ExamSlotDTO, PaginatedScheduleDTO
  data.py        → UploadResponseDTO, DataStatusDTO
  error.py       → ErrorDTO
  generate.py    → GenerationStatusDTO, GenerateResponseDTO
```

### 4.2 Core DTOs

See v2.0.2 document for full Pydantic model definitions (unchanged). Key additions:

```python
# src/api/schemas/generate.py
class GenerationStatusDTO(BaseModel):
    status:          Literal["idle", "running", "completed", "failed"]
    total_schedules: Optional[int] = None
    error:           Optional[str] = None   # populated on "failed"; safe message only

class GenerateResponseDTO(BaseModel):
    status: Literal["running"]
```

### 4.3 API Endpoint Reference

| Method | Path | Response | Notes |
|---|---|---|---|
| POST | `/api/data/courses/upload` | `UploadResponseDTO` | Replace mode |
| PATCH | `/api/data/courses/upload` | `UploadResponseDTO` | Append mode |
| POST | `/api/data/periods/upload` | `UploadResponseDTO` | Replace mode |
| PATCH | `/api/data/periods/upload` | `UploadResponseDTO` | Append mode |
| GET | `/api/data/status` | `DataStatusDTO` | Course count, period count, cache status |
| GET | `/api/programmes` | `ProgrammeListDTO` | All available programmes |
| GET | `/api/programmes/{id}/courses` | `list[CourseDetailDTO]` | Drill-down per programme |
| GET | `/api/periods` | `list[ExamPeriodDTO]` | All loaded exam periods |
| PATCH | `/api/periods/{key}/exclusions` | `ExamPeriodDTO` | Toggle one day |
| PATCH | `/api/periods/{key}/range` | `ExamPeriodDTO` | Adjust start/end |
| POST | `/api/schedules/generate` | `202 GenerateResponseDTO` | Atomic guard → 409 on duplicate *(SCRUM-131)* |
| GET | `/api/generate/status` | `GenerationStatusDTO` | Responds ≤ 200 ms always; polls every 500 ms |
| GET | `/api/schedules` | `PaginatedScheduleDTO` | Paginated; `sort_by`/`filter_prog` reserved for v3.0 |
| GET | `/api/schedules/{id}/export` | `text/plain` stream | Download .txt file |

### 4.4 v3.0 Reserved Parameters

`GET /api/schedules` accepts `sort_by` and `filter_prog` as inert query parameters in v2.0. Both appear in OpenAPI docs with `[Reserved — v3.0]` descriptions. The React Query key is structured as `['schedules', { page, filters: {} }]` — the empty `filters` object is load-bearing for zero-refactor Phase 3 activation.

---

## 5. Pagination & Memory Architecture

### 5.1 The Problem: O(n) Laziness Must Survive the API Boundary

The v1.0 `ScheduleGenerator` is a Python generator (`yield`). It produces schedules lazily, O(1) memory at a time. A naïve implementation calling `list(generator.generate_schedules(...))` silently destroys this guarantee.

### ⚠️ Critical Issue #1 — Fixed in v2.0.3

**Problem identified in senior review:** `app_controller.py` line 93-95 called `list()` on the generator before passing to the exporter, materialising the entire result set into RAM.

**Fix applied to source code:**

```python
# BEFORE (broken — v2.0.2):
schedules_by_period[period_key] = list(
    self._generator.generate_schedules(relevant_courses, period)
)

# AFTER (correct — v2.0.3):
# Pass the lazy iterator directly — do NOT call list() here.
# Converting to a list would materialise all schedules into RAM,
# destroying the O(PAGE_SIZE) memory guarantee of PaginatedExporter.
schedules_by_period[period_key] = self._generator.generate_schedules(
    relevant_courses, period
)
```

The type of `schedules_by_period` is now `Dict[str, Iterator[Schedule]]`. Jira: **SCRUM-128** (Ron — PR must include a unit test asserting the exporter receives an iterator, not a list).

### ⚠️ Critical Issue #2 — Fixed in v2.0.3

**Problem identified in senior review:** `IOutputExporter.export_schedules` was typed as `Dict[str, List[Schedule]]`, incompatible with streaming. `PaginatedExporter` and `AppController` would collide mid-sprint without this fix.

**Fix applied to source code (`src/interfaces/i_output_exporter.py`):**

```python
# BEFORE (broken — v2.0.2):
def export_schedules(
    self,
    schedules_by_period: Dict[str, List[Schedule]],
    courses_by_id: Dict[str, Course],
) -> None:

# AFTER (correct — v2.0.3):
def export_schedules(
    self,
    schedules_by_period: Dict[str, Iterator[Schedule]],  # Iterator, NOT List
    courses_by_id: Dict[str, Course],
) -> None:
```

The docstring now explicitly states: *"Implementations MUST NOT call `list()` on the iterator — the generator's O(1) laziness must be preserved through to the exporter boundary."* Jira: **SCRUM-129** (Alon — this PR must be merged **before** SCRUM-24 and SCRUM-128).

### 5.2 Solution: PaginatedExporter

```python
# src/adapters/paginated_exporter.py
PAGE_SIZE = 50

class PaginatedExporter(IOutputExporter):
    def export_schedules(self, schedules_by_period, courses_by_id) -> None:
        self.courses_by_id = courses_by_id
        for period_key, schedule_iter in schedules_by_period.items():
            pages, buffer, total = [], [], 0
            for schedule in schedule_iter:   # consumes generator lazily ✓
                buffer.append(schedule)
                total += 1
                if len(buffer) == PAGE_SIZE:
                    pages.append(buffer)
                    buffer = []              # discard reference → GC eligible
            if buffer:
                pages.append(buffer)
            self._pages[period_key] = pages
            self._totals[period_key] = total
```

### 5.3 Memory Guarantee

| Scenario | Naïve API | Paginated API (this design) |
|---|---|---|
| 10,000 valid schedules | O(10,000) in RAM ⚠️ | O(PAGE_SIZE) in RAM ✓ |
| Client requests page 3 | All 10,000 already loaded | Only page 3 read from buffer |

Memory at any point is bounded by **O(PAGE_SIZE × number_of_active_periods)** — a constant, not proportional to problem size.

---

## 6. Dependency-Injection Integration Map

### 6.1 Server-Side Session State — UUID SessionStore

Full implementation in v2.0.2 document. Summary: `SessionState` dataclass keyed by UUID in a singleton `SessionStore`. React client carries `X-Session-ID` header. `PaginatedExporter` is retained inside `SessionState` (not Kiro's `InMemoryExporter`).

```python
@dataclass
class SessionState:
    session_id:        str              = field(default_factory=lambda: str(uuid.uuid4()))
    courses:           list[Course]     = field(default_factory=list)
    exam_periods:      list[ExamPeriod] = field(default_factory=list)
    selected_programs: list[str]        = field(default_factory=list)
    exporter:          PaginatedExporter = field(default_factory=PaginatedExporter)
    active_period:     str              = ""
    generation_status: str              = "idle"   # idle | running | completed | failed
    generation_error:  Optional[str]    = None
```

### 6.2 New Adapters

- **`SessionDataProvider`** — `IDataProvider` reading from `SessionState` (not files)
- **`PaginatedExporter`** — `IOutputExporter` storing schedules in `PAGE_SIZE` pages
- **`JsonCacheAdapter`** — mtime-based JSON cache for parsed domain objects

### 6.3 FastAPI Dependency Wiring

`get_session()` resolves or creates `SessionState` by `X-Session-ID` header. `build_controller()` constructs a **fresh** `AppController` per generation call, injecting `selected_programs` from `session.selected_programs` **at the moment of construction** (snapshot at call time — not at app startup).

### ⚠️ Critical Issue #3 — Generation Timeout (New Task: SCRUM-130)

**Problem identified in senior review:** `run_generation_background` had no timeout. A hung generation leaves the session in `"running"` forever with no recovery.

**Required implementation (SCRUM-130, Ron):**

```python
async def run_generation_background(session: SessionState) -> None:
    try:
        session.generation_status = "running"
        controller = build_controller.__wrapped__(session)
        await asyncio.wait_for(
            asyncio.to_thread(controller.run),
            timeout=settings.generation_timeout_seconds,  # from SCRUM-132 config
        )
        session.generation_status = "completed"
        session.generation_error = None
    except asyncio.TimeoutError:
        session.generation_status = "failed"
        session.generation_error = (
            f"Generation timed out after {settings.generation_timeout_seconds}s. "
            "Try reducing the number of programmes or exam periods."
        )
        session.exporter = PaginatedExporter()   # clear partial results
    except Exception as exc:
        session.generation_status = "failed"
        session.generation_error = str(exc)
        session.exporter = PaginatedExporter()
```

### ⚠️ Gap 1 — Atomic Generation Guard (New Task: SCRUM-131)

**Problem identified in senior review:** Double-click on "Generate" fires two concurrent `BackgroundTasks` for the same session — no protection against this.

**Required implementation (SCRUM-131, Alon):**

```python
@router.post("/api/schedules/generate", status_code=202, response_model=GenerateResponseDTO)
async def trigger_generation(
    background_tasks: BackgroundTasks,
    session: SessionState = Depends(get_session),
):
    # Atomic guard: check + set before any await — no race window.
    # FastAPI processes each request in a single coroutine, so this is safe.
    if session.generation_status == "running":
        raise HTTPException(status_code=409, detail="Generation already in progress.")
    session.generation_status = "running"   # set before any await
    background_tasks.add_task(run_generation_background, session)
    return GenerateResponseDTO(status="running")
```

### ⚠️ Gap 4 — CORS Configuration (New Task: SCRUM-132 + updated SCRUM-59)

**Problem identified in senior review:** `localhost:5173` was hardcoded in `main.py`. Breaks silently on any other port or machine.

**Required implementation (SCRUM-132, Lotem — starting task):**

```python
# src/api/config.py  (new file)
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    cors_origins: List[str] = ["http://localhost:5173"]
    generation_timeout_seconds: int = 60
    server_port: int = 8000
    app_title: str = "examSchedule v2.0"
    class Config:
        env_file = ".env"

settings = Settings()
```

`main.py` (SCRUM-59) must use `settings.cors_origins`, not hardcode `localhost:5173`.

### 6.4 Polling Endpoint: GET /api/generate/status

React client polls every 500 ms after `POST /api/schedules/generate` returns 202. Endpoint always responds ≤ 200 ms. Returns `GenerationStatusDTO` with `status`, `total_schedules` (on completed), and `error` (on failed).

---

## 7. UI/UX Screen Design

*(Unchanged from v2.0.2 — full screen wireframes, component inventory, Tailwind token table, and Action Bar extensibility note in SCRUM-69)*

**Input Screen components:** `FileUploadPanel`, `ProgrammePanel`, `ExamPeriodCalendar`, date range pickers, status bar, Generate button with loading state.

**Output Screen components:** `ScheduleCalendar` (CSS Grid), `ExamSlotCell`, `SemesterGroupLayout`, `NavigationBar` (React Query key `['schedules', { page, filters: {} }]`), programme colour coding, Save button.

**Action Bar extensibility:** Built as a `flex items-center gap-4` row. Current elements (Prev/Next, "X of Y" counter, Save button) occupy named, independently-sized flex slots. v3.0 Filter Panel inserts as an additional flex child — no grid restructuring required.

---

## 8. Jira Epic & Granular Story Breakdown

*All v2.0 ticket IDs are sequential continuations from SCRUM-19 (last v1.0 ticket). The actual Jira board issue keys for v2.0 tasks begin at SCRUM-59 and extend through SCRUM-132.*

### Epic 1 — FastAPI Backend: Core Infrastructure

| Ticket | Title | Owner | Notes |
|---|---|---|---|
| SCRUM-59 | FastAPI app factory + CORS + SessionStore lifespan | Ron | **Updated:** CORS from `settings.cors_origins` (SCRUM-132 dependency) |
| SCRUM-60 | Pydantic DTO schemas (all) | Ron | includes `GenerationStatusDTO`, `GenerateResponseDTO` |
| SCRUM-61 | SessionStore + UUID Depends() wiring | Alon | |
| SCRUM-62 | SessionDataProvider adapter | Alon | |
| SCRUM-63 | PaginatedExporter adapter | Ron | Implements `Dict[str, Iterator[Schedule]]` interface (post SCRUM-129) |
| SCRUM-64 | JsonCacheAdapter | Ron | mtime-based; thread-safe; corrupt cache fallback |
| SCRUM-65 | Global exception handler | Ron | 4 exception types; safe ErrorDTO |
| SCRUM-66 | FastAPI composition root wiring | Alon | **Note:** fresh `AppController` per call; `selected_programs` snapshot at call time |
| **SCRUM-129** | **Update IOutputExporter: Iterator[Schedule]** | **Alon** | **NEW — Critical Issue #2. Merge first.** |
| **SCRUM-128** | **Refactor AppController streaming (no list())** | **Ron** | **NEW — Critical Issue #1. Blocked by SCRUM-129.** |
| **SCRUM-130** | **Add asyncio.wait_for generation timeout** | **Ron** | **NEW — Critical Issue #3. Blocked by SCRUM-132.** |
| **SCRUM-131** | **Atomic generation guard (409 on double-trigger)** | **Alon** | **NEW — Gap 1.** |
| **SCRUM-132** | **pydantic-settings config module + .env.example** | **Lotem** | **NEW — Gap 4. Lotem's starting task.** |

### Epic 2 — FastAPI Backend: API Routes

| Ticket | Title | Owner |
|---|---|---|
| SCRUM-67 | POST/PATCH `/api/data/courses/upload` | Ron |
| SCRUM-68 | POST/PATCH `/api/data/periods/upload` | Ron |
| SCRUM-69 | GET `/api/data/status` | Ron |
| SCRUM-70 | GET `/api/programmes` | Alon |
| SCRUM-71 | GET `/api/programmes/{id}/courses` | Alon |
| SCRUM-72 | GET `/api/periods` | Alon |
| SCRUM-73 | PATCH `/api/periods/{key}/exclusions` | Ron |
| SCRUM-74 | PATCH `/api/periods/{key}/range` | Ron |
| SCRUM-75 | POST `/api/schedules/generate` *(with atomic guard from SCRUM-131)* | Ron |
| SCRUM-76 | GET `/api/generate/status` (polling endpoint) | Ron |
| SCRUM-77 | GET `/api/schedules` (paginated + v3.0 reserved params) | Ron |
| SCRUM-78 | GET `/api/schedules/{id}/export` | Alon |

### Epic 3 — React Frontend: Input Screen

| Ticket | Title | Owner |
|---|---|---|
| SCRUM-79 | React + Vite + Tailwind scaffold | Niv |
| SCRUM-80 | `api/client.ts` typed fetch wrapper | Niv |
| SCRUM-81 | Toast notification system | Niv |
| SCRUM-82 | File upload panel — courses + dates | Niv |
| SCRUM-83 | Programme multi-select panel | Niv |
| SCRUM-84 | Course drill-down accordion | Niv |
| SCRUM-85 | `ExamPeriodCalendar` React component | Niv |
| SCRUM-86 | Date range pickers per semester | Niv |
| SCRUM-87 | Input screen layout + status bar | Niv |
| SCRUM-88 | "Generate" button + loading state | Niv |

### Epic 4 — React Frontend: Output Screen

| Ticket | Title | Owner |
|---|---|---|
| SCRUM-89 | `ScheduleCalendar` React component | Niv |
| SCRUM-90 | `ExamSlot` cell component | Niv |
| SCRUM-91 | Semester group layout | Niv |
| SCRUM-92 | Navigation bar + pagination (v3.0-ready query key) | Niv |
| SCRUM-93 | Programme colour coding | Niv |
| SCRUM-94 | Save schedule button | Niv |

### Epic 5 — QA: API Test Suite

| Ticket | Title | Owner |
|---|---|---|
| SCRUM-95 | pytest + TestClient setup | Guy |
| SCRUM-96 | Data upload endpoint tests | Guy |
| SCRUM-97 | Programme endpoint tests | Guy |
| SCRUM-98 | Period endpoint tests | Guy |
| SCRUM-99 | Schedule generation + pagination tests | Guy |
| SCRUM-100 | Export endpoint test | Guy |
| SCRUM-101 | Global exception handler tests | Guy |
| SCRUM-102 | Pagination memory boundary test | Guy |
| SCRUM-103 | Coverage gate + Pylint | Guy |

### Epic 6 — CI/CD Pipeline

| Ticket | Title | Owner |
|---|---|---|
| SCRUM-104 | `ci.yml` test runner workflow | Guy |
| SCRUM-105 | `ci.yml` Pylint linting step | Guy |
| SCRUM-106 | `ci.yml` coverage enforcement | Guy |
| SCRUM-107 | Branch protection rules | Guy |
| SCRUM-108 | Jira–Git branch name automation | Guy |

### Epic 7 — Documentation & Delivery

| Ticket | Title | Owner | Notes |
|---|---|---|---|
| SCRUM-109 | UI/UX Design Document | Alon + Niv | Action Bar extensibility note required |
| SCRUM-110 | Updated Software Design Document | Alon | |
| SCRUM-111 | Updated Test Specification | Alon + Guy | |
| SCRUM-112 | requirements.txt + package.json | Alon | Add `pydantic-settings` |
| SCRUM-113 | User Manual — Basic Operation Guide | Lotem | **Post-UI only. Blocked by SCRUM-94. Sprint 2/3.** |

---

## 9. CI/CD Pipeline & Definition of Done

### 9.1 GitHub Actions: `ci.yml`

Triggers on `pull_request` and `push` to `main`. Steps: checkout → Python 3.12 → `pip install -r requirements.txt` → `pytest --cov --cov-fail-under=85` → `pylint src/ --fail-under=8.5` → upload coverage report as artifact.

### 9.2 Branch Naming Convention

`SCRUM-{ID}/short-description` — enforced by pre-commit hook (SCRUM-108).

### 9.3 Definition of Done

A ticket is Done when: implementation complete, PR opened, `ci.yml` green, all acceptance criteria verified, Alon has approved the PR, branch merged to `main`.

---

## 10. Strategic Team Delegation Matrix

### 10.1 Assignment Table

| Owner | Tickets | Role & Rationale |
|---|---|---|
| **Alon** | SCRUM-61, 62, 66, 70–72, 78, 109–112 + **SCRUM-129, 131** | Cross-layer architectural decisions; DI graph; all DTO mappings; code review; Sprint 3 fixes |
| **Ron** | SCRUM-59, 60, 63–65, 67–69, 73–77 + **SCRUM-128, 130** | Most algorithmically and architecturally demanding backend work: session wiring, all Pydantic schemas, async generation pipeline, PAGE_SIZE-bounded exporter, mtime cache, exception handler, all stateful mutation routes, timeout |
| **Niv** | SCRUM-79–94 (entire React + Tailwind frontend) | Full ownership of both screens; never imports Python; develops against MSW mocks before backend is ready |
| **Guy** | SCRUM-95–108 (entire QA suite + CI/CD pipeline) | Sole owner of all quality assurance: 9 API test files, CI, Pylint, coverage, branch protection |
| **Lotem** | **SCRUM-132, SCRUM-133, SCRUM-134** (starting tasks) + **SCRUM-113** (end task) | See §10.2 |

### 10.2 Lotem — Task Assignment (Updated v2.0.3)

Lotem has **4 total tasks**: 3 implementation tasks in Sprint 1 (Days 1–4) and 1 documentation task at the end of Sprint 2/3. All are fully isolated and non-blocking.

**Sprint 1 starting tasks (Days 1–4):**

**SCRUM-132 — pydantic-settings config module** *(Days 1–3, Backend epic SCRUM-54)*
Creates `src/api/config.py` with pydantic-settings (CORS origins, timeout, port) and `.env.example`. Fixes the senior review's Gap 4 (hardcoded CORS). Must merge early — unblocks SCRUM-59 and SCRUM-130.
- Isolated: no dependency on any other in-progress task
- Non-blocking: others import from it, but it has no inward dependencies
- Self-contained: one new file + one `.env.example` + one `requirements.txt` line

**SCRUM-133 — Tailwind CSS design tokens** *(Days 1–3, React UI epic SCRUM-55)*
Creates `frontend/tailwind.config.js` with the full `theme.extend` block (brand, surface, exam colour palette) and `frontend/src/tokens.ts` exporting `PROGRAMME_COLOURS`. Pure frontend configuration — zero dependency on the backend or any other task.

**SCRUM-134 — ErrorBoundary + LoadingSpinner components** *(Days 2–4, React UI epic SCRUM-55)*
Creates `frontend/src/components/ErrorBoundary.tsx` (React class component, catches rendering errors) and `frontend/src/components/LoadingSpinner.tsx` (functional component with Tailwind animation). No props required, no API calls. Depends only on SCRUM-133 tokens.

**End task (Sprint 2/3): SCRUM-113 — User Manual**

A standalone Word document for non-technical end users. Has a **hard dependency on UI completion** — explicitly blocked by SCRUM-94 (Save button, the final frontend task). Sequenced in Sprint 2/3 only.

**Formal non-blocking proof** (SCRUM-113 and all Lotem tasks): No Lotem task appears on any critical path node. Ron, Niv, Guy, and Alon all have fully independent backlogs. Pipeline delivers completely regardless of Lotem's availability at any given time.

### 10.3 Ron — High-Complexity Backend Detail

SCRUM-63 (`PaginatedExporter`): Must consume `Iterator[Schedule]` per the updated interface (SCRUM-129). Must consume the generator in PAGE_SIZE-bounded chunks without ever triggering full materialisation. Requires careful generator protocol handling and GC-eligible page buffer management.

SCRUM-64 (`JsonCacheAdapter`): `datetime.date` and `Set[date]` serialisation; atomic mtime comparison; silent fallback on corrupt cache.

SCRUM-65 (Global Exception Handler): Intercepts exceptions from `AppController.run()` deep in a thread pool; full traceback logged internally; safe message only in `ErrorDTO` to client.

SCRUM-75 (POST `/api/schedules/generate`): Must include the atomic guard from SCRUM-131 and integrate with `run_generation_background` from SCRUM-130.

SCRUM-128 (`AppController` streaming): `list()` removed; `Iterator[Schedule]` passed directly; blocked by SCRUM-129.

SCRUM-130 (timeout): `asyncio.wait_for` wrapping `asyncio.to_thread(controller.run)`; timeout from `settings.generation_timeout_seconds`; blocked by SCRUM-132.

### 10.4 Alon — Sprint 1 Bottleneck Warning

The senior review flagged: **SCRUM-66 (composition root wiring) blocks both SCRUM-63 (Ron's PaginatedExporter endpoint) and SCRUM-88 (Niv's Generate button)**. SCRUM-66 must be Sprint 1's highest-priority Alon task.

SCRUM-129 (`IOutputExporter` interface update) must be merged before any other interface-dependent PR. It is the first PR that should go to `main`.

---

## 11. Sprint Plan

### Sprint 1 (Days 1–7) — Backend Foundation

Goal: FastAPI app running, all DTOs defined, DI wiring complete, existing tests still green, CI pipeline live, config module delivered.

| Ticket | Owner | Days | Notes |
|---|---|---|---|
| **SCRUM-132** | **Lotem** | **1–3** | **Config module — must merge early for SCRUM-59 and SCRUM-130** |
| **SCRUM-133** | **Lotem** | **1–3** | **Tailwind design tokens — unblocks Niv immediately** |
| **SCRUM-134** | **Lotem** | **2–4** | **ErrorBoundary + LoadingSpinner — after SCRUM-133** |
| **SCRUM-129** | **Alon** | **1–2** | **Interface fix — merge first before any other PR** |
| SCRUM-59 | Ron | 2–3 | After SCRUM-132 merged |
| SCRUM-60 | Ron | 1–3 | |
| SCRUM-61 | Alon | 2–4 | |
| SCRUM-62 | Alon | 4–5 | |
| SCRUM-63 | Ron | 3–5 | After SCRUM-129 merged |
| **SCRUM-128** | **Ron** | **4–6** | **After SCRUM-129 and SCRUM-63** |
| SCRUM-64 | Ron | 5–7 | |
| SCRUM-65 | Ron | 4–5 | |
| SCRUM-66 | Alon | 5–6 | **Priority: unblocks Ron (SCRUM-63) and Niv (SCRUM-88)** |
| **SCRUM-131** | **Alon** | **5–6** | **Atomic guard — alongside SCRUM-66** |
| SCRUM-79 | Niv | 1–2 | |
| SCRUM-80 | Niv | 2–3 | |
| SCRUM-81 | Niv | 3–4 | |
| SCRUM-95 | Guy | 1–2 | |
| SCRUM-104–106 | Guy | 2–4 | |
| SCRUM-108 | Guy | 5 | |

Sprint 1 exit criteria: `GET /health → 200`; all 84 existing tests pass in CI; React dev server renders; `ci.yml` green on `main`; `IOutputExporter` interface fix merged.

### Sprint 2 (Days 8–16) — API Routes + Both Screens

Goal: All API endpoints implemented. Input and Output screens fully functional.

| Ticket | Owner | Days |
|---|---|---|
| SCRUM-67–69 | Ron | 8–10 |
| SCRUM-70–72 | Alon | 8–10 |
| SCRUM-73–74 | Ron | 10–11 |
| SCRUM-75, 76, 77 | Ron | 11–14 | *(includes SCRUM-130 timeout + SCRUM-131 guard)* |
| **SCRUM-130** | **Ron** | **12–13** | **Timeout — after SCRUM-75** |
| SCRUM-78 | Alon | 14–15 |
| SCRUM-82–88 | Niv | 8–14 |
| SCRUM-89–94 | Niv | 12–16 |
| SCRUM-96–98 | Guy | 8–12 |
| SCRUM-99–101 | Guy | 12–16 |
| SCRUM-109 | Alon + Niv | 8–11 |
| SCRUM-113 | Lotem | 14–16 | *(after SCRUM-94 merged)* |

Sprint 2 exit criteria: Full end-to-end user flow works in browser; all API tests pass; > 80% coverage.

### Sprint 3 (Days 17–21) — Integration, QA & Delivery

Goal: Memory test, coverage gate ≥ 85%, all documentation, release candidate.

| Ticket | Owner | Days |
|---|---|---|
| SCRUM-102 | Guy | 17–18 |
| SCRUM-103 | Guy | 18–19 |
| SCRUM-107 | Guy | 19 |
| SCRUM-110 | Alon | 17–19 |
| SCRUM-111 | Alon + Guy | 19–20 |
| SCRUM-112 | Alon | 20 |
| Bug fixes, PR approvals | Alon | 17–21 |

Sprint 3 exit criteria: All 89+ tests green in CI; coverage ≥ 85%; Pylint ≥ 8.5; all docs merged; demo rehearsal passes end-to-end.

---

## 12. Risk Register (Updated v2.0.3)

| Risk | Prob. | Impact | Owner | Mitigation |
|---|---|---|---|---|
| `BackgroundTasks` thread-safety: race condition on `generation_status` | Medium | High | Ron | Single-writer pattern + atomic guard (SCRUM-131) + concurrent-request unit test |
| Double-click "Generate" fires two background tasks | **Low** *(mitigated)* | High | Alon | **SCRUM-131: check-and-set guard returns HTTP 409 before any `await`** |
| Generation hangs indefinitely — session stuck in "running" | **Low** *(mitigated)* | High | Ron | **SCRUM-130: `asyncio.wait_for` with configurable timeout; clean failure path** |
| Backtracking generates > 10,000 schedules; RAM spikes | Medium | Medium | Ron | Configurable `MAX_SCHEDULES` hard cap (default 2,000) in `AppController` |
| React Query serves stale schedule data after re-generation | Medium | Medium | Niv | Invalidate `schedules` cache key on `POST /api/schedules/generate` success |
| CI takes > 5 minutes | Low | Medium | Guy | `pytest -x` (stop on first failure); target < 90-second CI wall time |
| Pylint false positives | Low | Low | Guy | `# pylint: disable=...` annotations with PR comment + Alon approval |
| Niv blocked waiting for unimplemented API route | Medium | Medium | Niv | MSW mock handlers for all endpoints from day 1 |
| Lotem unavailable for entire sprint | High | None | — | SCRUM-132/133/134 (starting tasks) and SCRUM-113 (end task) are all zero-dependency; pipeline unaffected |
| CORS misconfiguration on demo machine | **Low** *(mitigated)* | Medium | Lotem | **SCRUM-132: `.env`-based CORS config; no source code change needed** |
| FastAPI not permitted in grading environment | Low | High | Alon | Pinned `requirements.txt`; `pip install fastapi uvicorn pydantic pydantic-settings` in README; test in clean venv |

### Updated SRS Coverage Check

| SRS Requirement | JIRA Coverage | Status |
|---|---|---|
| 2.1.1 File upload via button | POST `/api/data/courses/upload` | ✓ |
| 2.1.2 Replace mode | SCRUM-67 | ✓ |
| 2.1.3 Append/update mode | SCRUM-67 | ✓ |
| 2.2 Programme multi-select (up to 5) | SCRUM-70, 83 | ✓ |
| 2.3.2 Course drill-down by year/semester | SCRUM-71, 84 | ✓ |
| 2.4.2 Toggle individual exam dates | SCRUM-73, 85 | ✓ |
| 2.4.3 Shift semester start/end | SCRUM-74, 86 | ✓ |
| 2.5 Filter/sort (v3.0) | Declared as inert query params | ✓ |
| 3.1 Output as year calendar | SCRUM-89 | ✓ |
| 3.2 Navigate between schedules | SCRUM-92 | ✓ |
| 3.3 Show X of Y count | SCRUM-92 + X-Total-Count header | ✓ |
| 3.5 Save schedule to file | SCRUM-78, 94 | ✓ |
| 5.1 Internal caching (no re-read if unchanged) | SCRUM-64 `JsonCacheAdapter` | ✓ |
| **5.2 No freeze > 1 second** | **SCRUM-130 timeout + BackgroundTasks** | **✓ (was ⚠️)** |

---

## 13. Correctness Properties

*(Adopted from Kiro review, adapted to paginated architecture. All `InMemoryExporter` references replaced with `PaginatedExporter`. Properties 20–22 are original additions.)*

| Property | Statement | Test Ticket |
|---|---|---|
| 1 | Pydantic DTO round-trip fidelity — no data loss | SCRUM-96, 99 |
| 2 | `SessionDataProvider` returns exact objects from `SessionState` | SCRUM-95 |
| 3 | `PaginatedExporter` completeness (sum of totals = generator output) AND boundedness (no page > PAGE_SIZE) | SCRUM-102 |
| 4 | File upload replace mode exactness | SCRUM-96 |
| 5 | File upload append mode preservation | SCRUM-96 |
| 6 | Malformed upload returns 422; `SessionState` unchanged | SCRUM-96 |
| 7 | Programme list derived from distinct `CourseOffering.programme_id` values | SCRUM-97 |
| 8 | Programme selection validation gate (max 5, known IDs) | SCRUM-97 |
| 9 | Day exclusion toggle symmetry (toggle twice → original state) | SCRUM-98 |
| 10 | Date range ordering invariant (`start ≤ end`; 400 otherwise) | SCRUM-98 |
| 11 | Generation precondition enforcement (422 if any of courses/periods/programs empty) | SCRUM-99 |
| 12 | Generation failure leaves no partial state (`exporter` reset, `status = "failed"`) | SCRUM-101 |
| **12a** | **Generation timeout leaves no partial state (same as Property 12, triggered by `asyncio.TimeoutError`)** | **SCRUM-130** |
| 13 | Paginated endpoint slice correctness; `X-Total-Count = T` | SCRUM-99 |
| 14 | Navigation button state invariant (Prev disabled ↔ P==1; Next disabled ↔ P==T) | SCRUM-92 |
| 15 | Calendar cell placement correctness (slot appears in date-matching cell) | SCRUM-89, 90 |
| 16 | Period sort order: FALL < SPRI < SUMM; Aleph < Bet < Gimel | SCRUM-91 |
| 17 | Run button enabled ↔ courseCount > 0 AND periodCount > 0 AND programmeCount > 0 | SCRUM-88 |
| 18 | Status summary accuracy within 5 seconds of any data action | SCRUM-87 |
| 19 | Save endpoint output byte-for-byte identical to `TextFileExporter` | SCRUM-100 |
| 20 | UUID session isolation — mutations to session A have no effect on session B | SCRUM-95 |
| 21 | Status polling responds ≤ 200 ms always, even during active generation | SCRUM-99 |
| 22 | v3.0 reserved params are inert — response identical with and without `sort_by`/`filter_prog` | SCRUM-99 |

---

## Appendix A — New Jira Tasks Summary (v2.0.3)

| Ticket | Title | Owner | Priority | Sprint |
|---|---|---|---|---|
| SCRUM-128 | Refactor AppController to stream iterators into IOutputExporter | Ron | **Critical** | 1 |
| SCRUM-129 | Update IOutputExporter interface: `Dict[str, Iterator[Schedule]]` | Alon | **Critical — merge first** | 1 |
| SCRUM-130 | Add `asyncio.wait_for` generation timeout | Ron | **Critical** | 2 |
| SCRUM-131 | Atomic generation guard — HTTP 409 on double-trigger | Alon | **High** | 1 |
| SCRUM-132 | pydantic-settings config module + `.env.example` | Lotem | **High** | 1 |
| SCRUM-133 | Tailwind CSS design tokens (`tailwind.config.js` + `tokens.ts`) | Lotem | **High** | 1 |
| SCRUM-134 | React utility components: `ErrorBoundary.tsx` + `LoadingSpinner.tsx` | Lotem | **Medium** | 1 |

## Appendix B — Updated Jira Tasks Summary (v2.0.3)

| Ticket | Title | Change |
|---|---|---|
| SCRUM-59 | FastAPI app factory + CORS | CORS now reads from `settings.cors_origins`; depends on SCRUM-132 |
| SCRUM-66 | FastAPI composition root wiring | `selected_programs` injection note confirmed present (Gap 2 already addressed) |
| SCRUM-113 | User Manual | Sequencing confirmed: explicitly post-UI, Sprint 2/3, blocked by SCRUM-94 |

---

*Document prepared for direct import into the team Jira board, GitHub repository, and course submission package.*
*All merges to `main` require: passing `ci.yml` + Alon's explicit PR approval.*
*Branch naming: `SCRUM-{ID}/short-description` — enforced by pre-commit hook (SCRUM-108).*
