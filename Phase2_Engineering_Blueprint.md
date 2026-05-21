# examSchedule v2.0 — Phase 2 Engineering Blueprint
### Enterprise-Grade Architectural Blueprint · Jira Epic Breakdown · Team Delegation Matrix

> **Document status:** Master Blueprint — Enterprise + Kiro Merge + Technical Review Patch  
> **Date:** 2026-05-21  
> **Version:** 2.0.3  
> **Authors:** Alon Cohen (Team Lead & Integration Architect)  
> **Methodology:** Agile / Scrum · Clean Architecture · Ports & Adapters · REST/SPA  
> **Merge note:** Incorporates selected elements from the Kiro architectural review (UUID session management, async status polling, correctness properties). Explicit rejections documented in §1 and §10.  
> **v2.0.3 patch:** Applies 3 critical fixes and 5 gap remediations identified in the v2.0.2 Technical Review. Adds SCRUM-121 through SCRUM-127. Lotem delegation revised: Sprint 1 = SCRUM-126 (Pydantic schemas in `src/schemas/`); Sprint 2 = SCRUM-113 (User Manual, post-UI).

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Phase 2 Requirements Analysis](#2-phase-2-requirements-analysis)
3. [Architectural Blueprint & Technology Stack](#3-architectural-blueprint--technology-stack)
4. [API Contract & DTO Specification](#4-api-contract--dto-specification)
5. [Pagination & Memory Architecture](#5-pagination--memory-architecture)
6. [Dependency-Injection Integration Map](#6-dependency-injection-integration-map)
7. [UI/UX Screen Design](#7-uiux-screen-design)
8. [Jira Epic & Granular Story Breakdown](#8-jira-epic--granular-story-breakdown)
9. [CI/CD Pipeline & Definition of Done](#9-cicd-pipeline--definition-of-done)
10. [Strategic Team Delegation Matrix](#10-strategic-team-delegation-matrix)
11. [Sprint Plan](#11-sprint-plan)
12. [Risk Register](#12-risk-register)
13. [Correctness Properties](#13-correctness-properties)

---

## 1. Executive Summary

examSchedule v1.0 is a production-quality CLI scheduling engine built on a strict five-layer
**Clean Architecture** (Domain → Interfaces → Adapters → Engine → CLI). All 84 tests pass.
The engine is fully decoupled from I/O through abstract ports (`IDataProvider`,
`IOutputExporter`, `IScheduleGenerator`, `IConflictStrategy`), with all concrete collaborators
assembled exclusively in `main.py` via dependency injection.

Phase 2 introduces a full visual application layer. This revision makes a **strategic pivot**
from a desktop GUI to a **Client-Server Web Architecture**: a **FastAPI** backend wrapping
the v1.0 engine, and a **React + Tailwind CSS** Single-Page Application (SPA) as the
presentation layer. This is not merely a technology preference — it is an architectural
decision that yields seven compounding engineering benefits, each detailed in Section 3.

The v1.0 engine, Domain, Interfaces, and all existing Adapters receive **zero modifications**.
The physical network boundary between React and FastAPI enforces the inward dependency
rule more rigorously than any in-process GUI framework can: the frontend cannot call engine
code directly, cannot import domain objects, and cannot bypass the adapter layer — the HTTP
protocol is the only permitted communication channel.

### Kiro Architectural Review — Merge Decisions

This document (v2.0.2-master) incorporates a selective merge from a secondary architectural
review ("Kiro model"). The following decisions govern exactly what was adopted and what
was explicitly rejected.

**Adopted from Kiro:**

- **UUID Session Management (§6.1, §6.3):** `AppSession` (single global) is replaced by a
  `SessionState` + `SessionStore` pattern. Each client carries an `X-Session-ID` UUID header.
  The server resolves or creates a session per request, making the API strictly stateless and
  safe for concurrent or multi-tab clients.

- **Async Status Polling endpoint (§4.3, §6.3, SCRUM-36B):** `GET /api/generate/status`
  formally added. The React client polls this endpoint every 500 ms after `POST /api/schedules/generate`
  returns `202`. The endpoint reads `SessionState.generation_status` (a string set by the
  background thread) and responds within 200 ms at all times.

- **Correctness Properties (§13):** A formal properties section maps every functional
  requirement to a machine-verifiable statement. Adapted from Kiro's format to align with
  our paginated architecture and v3.0 reserved parameters.

**Explicitly rejected from Kiro (with rationale):**

- **Kiro's `InMemoryExporter`:** Rejected. Kiro's exporter calls `list()` on the schedule
  generator, destroying the O(n) memory guarantee. Our `PaginatedExporter` (§5) is retained.
  It is the only architectural choice that prevents memory leaks for large result sets.

- **Kiro's Lotem delegation for API schemas:** Originally rejected in v2.0.2. Kiro assigned
  `src/api/schemas/` (the FastAPI DTO schemas imported by every route) to Lotem. This was
  correctly rejected because API schemas are on the critical path. Ron retains ownership of
  `src/api/schemas/` (SCRUM-21).

  **v2.0.3 revision:** A separate, genuinely isolated schema module — `src/schemas/` — has
  been created for domain-level Pydantic models (`CourseOfferingSchema`, `CourseSchema`,
  `ExamPeriodSchema`, `ScheduleSchema`, `ScheduleDetailSchema`). These models have zero
  imports from `src/presentation/`, `src/api/`, or FastAPI. This module is assigned to
  **Lotem as SCRUM-126** (Sprint 1). It is fully off the critical path. The API DTO schemas
  in `src/api/schemas/` remain with **Ron** (SCRUM-21). Formal non-blocking proof for
  Lotem's revised assignment is in §10.2.

- **Kiro's CI/CD omission:** Kiro has no CI/CD definition. Our GitHub Actions `ci.yml`,
  Pylint gate, coverage gate, Definition of Done (§9), and branch naming convention are
  all retained in full.

- **Kiro's v3.0 future-proofing omission:** Kiro has no reserved query parameters. Our
  `sort_by` / `filter_prog` reserved params (§4.4, SCRUM-37) and React Query key
  architecture (SCRUM-52) are retained in full.

---

## 2. Phase 2 Requirements Analysis

Structured extraction from *מסמך דרישות תוכנה – שלב 2*, mapped to engineering concerns
in the Client-Server model.

### 2.1 Input Screen Requirements

| Req. ID | Requirement | Client-Server Engineering Concern |
|---------|-------------|-----------------------------------|
| 2.1 | User defines courses and dates file paths | React file-upload form → `POST /api/data/upload` |
| 2.1.1 | Load data from files via button | Multipart form upload; FastAPI reads file bytes; `GUIDataProvider` parses them |
| 2.1.2 | Replace stored data with new file | `PUT /api/data/courses` — full state replacement on server side |
| 2.1.3 | Additively update data from a new file | `PATCH /api/data/courses` — merge without deleting existing records |
| 2.2 | Select up to 5 study programmes from a dynamic list | `GET /api/programmes` returns list; React multi-select, max 5, validated client + server |
| 2.3 | Display selected programmes (ID + name) | State held in React; data from `GET /api/programmes` response |
| 2.3.1 | Show programme ID + name per selected entry | `ProgrammeDTO` in response payload |
| 2.3.2 | Drill-down per programme: courses by year/semester, mandatory/elective, eval type | `GET /api/programmes/{id}/courses` → `CourseDetailDTO` |
| 2.4 | Calendar view of the exam period with current state | `GET /api/periods` → `ExamPeriodDTO`; React renders calendar from JSON |
| 2.4.1 | Calendar format showing current exam period summary | React calendar component consumes `ExamPeriodDTO.date_ranges` |
| 2.4.2 | Toggle day exclusion/inclusion per day | `PATCH /api/periods/{key}/exclusions` — body: `{ "date": "YYYY-MM-DD", "excluded": bool }` |
| 2.4.3 | Adjust start/end of exam period per semester | `PATCH /api/periods/{key}/range` — body: `{ "start": "...", "end": "..." }` |
| 2.5 | Filters and sorts | **Out of scope v2.0** — deferred to v3.0 (§2.5 of spec) |

### 2.2 Output Screen Requirements

| Req. ID | Requirement | Client-Server Engineering Concern |
|---------|-------------|-----------------------------------|
| 3.1 | Calendar view of one schedule at a time | `GET /api/schedules?page=1&size=1` → React renders `ScheduleDTO` as calendar |
| 3.2 | Navigation bar — next / previous | React pagination state; `page` query param sent to API |
| 3.3 | Show total count + current ordinal ("X of Y") | `X-Total-Count` response header on paginated endpoint |
| 3.4 | Exam slot: course ID, name, mandatory/elective, programme | `ExamSlotDTO` nested in `ScheduleDTO` |
| 3.5 | Save selected schedule to a readable file | `GET /api/schedules/{id}/export` → FastAPI streams a `.txt` file download |

### 2.3 Non-Functional Requirements

| Req. ID | Requirement | Target |
|---------|-------------|--------|
| 5.1 | Internal data persistence — avoid re-reading unchanged files | JSON cache keyed by file mtime; managed server-side |
| 5.2 | UI responsiveness — no stalls > 1 second | FastAPI `BackgroundTasks` + streaming pagination; React shows loading states |
| 4.1 | Language: Python | Python 3 + FastAPI backend; TypeScript React frontend |
| 4.2 | OOP design | Maintained via Clean Architecture in backend |
| 4.3 | Designed for future extension (v3.0 filters) | Paginated API supports future `?filter=` query params with no breaking changes |
| 7.1 | Git per-member + Jira project management | Branch naming enforced: `SCRUM-{ID}/description` |
| 7.3 | AGILE: UI/UX doc, test spec, code review | All artefacts produced; PRs mandatory |

---

## 3. Architectural Blueprint & Technology Stack

### 3.1 The Web Architecture Pivot — Rationale

**Decision: FastAPI (Backend) + React + Tailwind CSS (Frontend)**

Moving from a PyQt6 desktop GUI to a Client-Server web architecture is a strategic
architectural decision, not a cosmetic technology swap. The following table shows how each
of the seven mandated optimizations is either enabled or dramatically simplified by this pivot.

| Optimization | PyQt6 Approach | FastAPI + React Approach |
|---|---|---|
| Clean Architecture enforcement | Convention-only; imports can leak | **Physical HTTP boundary** — React literally cannot import Python engine code |
| Memory leak prevention | Custom generator consumption logic in-process | **HTTP Pagination** — server streams one page at a time; client never holds all schedules |
| Strict DTO enforcement | Pydantic DTOs at in-process boundary | **Pydantic required** by FastAPI at every endpoint; enforced by HTTP serialisation |
| Testing | `pytest-qt` — flaky, slow, GUI-dependent | **`TestClient`** — in-process HTTP, deterministic, runs in CI without a display server |
| CI/CD | Complex Xvfb setup for headless Qt | **GitHub Actions** — zero display dependency; standard Python test runner |
| Error handling | Qt signal propagation; custom crash handlers | **FastAPI `@app.exception_handler`** — single handler produces clean JSON; React renders Toast |
| Future scalability | Monolithic desktop binary | **Decoupled services** — backend and frontend deployable and upgradeable independently |

### 3.2 How the HTTP Boundary Enforces Clean Architecture

The single most important architectural property of Clean Architecture is the **inward
dependency rule**: outer layers may depend on inner layers, never the reverse, and no layer
may be bypassed. A PyQt6 application enforces this by convention only — a developer could
always add a rogue `from src.engine import ...` import in a widget file.

The FastAPI + React boundary makes this violation **physically impossible**:

```
React SPA (TypeScript)          FastAPI Backend (Python)
─────────────────────           ─────────────────────────────────────────
fetch('/api/schedules')   HTTP  src/api/routes/schedules.py
                         ────►  src/api/dependencies.py  (DI wiring)
                                src/adapters/gui_data_provider.py
                                src/engine/app_controller.py
                                src/domain/ · src/interfaces/
```

The React application has no knowledge of Python, no access to domain objects, and no
way to call the engine directly. The only communication channel is HTTP + JSON — and
every JSON payload is validated against a Pydantic DTO schema before it enters or exits
the Python process. This is Clean Architecture enforced by the network stack, not by
human discipline.

### 3.3 Complete System Architecture Diagram

```
┌───────────────────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER — React SPA  (TypeScript + Tailwind CSS)              │
│                                                                           │
│  InputScreen.tsx        OutputScreen.tsx        Toast.tsx                 │
│  ProgrammePanel.tsx     ScheduleCalendar.tsx     ErrorBoundary.tsx        │
│  ExamPeriodCalendar.tsx NavigationBar.tsx         api/client.ts           │
│                                                                           │
│  State: Zustand / React Query · Build: Vite · Port: 5173                  │
└───────────────────────────┬───────────────────────────────────────────────┘
                            │  HTTP / JSON  (fetch API)
                            │  Content-Type: application/json
                            │  X-Total-Count header (pagination)
┌───────────────────────────▼───────────────────────────────────────────────┐
│  API LAYER — FastAPI  (Python 3)                                          │
│                                                                           │
│  src/api/                                                                 │
│    main.py          ← FastAPI app, CORS, lifespan, global exception handler│
│    routes/                                                                │
│      data.py        ← POST/PUT/PATCH /api/data/*                          │
│      programmes.py  ← GET /api/programmes, /api/programmes/{id}/courses   │
│      periods.py     ← GET/PATCH /api/periods/*                            │
│      schedules.py   ← GET /api/schedules (paginated), /export             │
│    schemas/         ← Pydantic DTOs (request + response models)           │
│      programme.py · course.py · period.py · schedule.py · error.py       │
│    dependencies.py  ← FastAPI Depends() DI wiring                        │
│    session.py       ← Server-side session state (AppSession dataclass)    │
│    exceptions.py    ← Global exception handler + custom exception types   │
│                                                                           │
│  Port: 8000 · Uvicorn ASGI                                                │
├───────────────────────────────────────────────────────────────────────────┤
│  ENGINE LAYER — ZERO CHANGES  (src/engine/)                               │
│  AppController · ScheduleGenerator                                        │
├───────────────────────────────────────────────────────────────────────────┤
│  INTERFACES LAYER — ZERO CHANGES  (src/interfaces/)                       │
│  IDataProvider · IOutputExporter · IScheduleGenerator · IConflictStrategy│
├───────────────────────────────────────────────────────────────────────────┤
│  ADAPTERS LAYER — Existing unchanged + NEW additions  (src/adapters/)     │
│                                                                           │
│  Existing (untouched):                                                    │
│    FileDataProvider · TextFileExporter · ExactConflictStrategy            │
│    CourseFileReader · ExamPeriodFileReader · ProgramSelectorReader        │
│  NEW:                                                                     │
│    SessionDataProvider  ← IDataProvider reading from AppSession           │
│    PaginatedExporter    ← IOutputExporter storing paginated schedule list │
│    JsonCacheAdapter     ← mtime-based JSON cache for parsed domain objects│
├───────────────────────────────────────────────────────────────────────────┤
│  DOMAIN LAYER — ZERO CHANGES  (src/domain/)                               │
│  Course · CourseOffering · ExamPeriod · Schedule · Semester               │
└───────────────────────────────────────────────────────────────────────────┘

  Dependency rule: Every arrow points inward only.
  The HTTP boundary between React and FastAPI makes lateral leakage physically impossible.
```

### 3.4 Technology Stack Summary

| Layer | Technology | Version | Rationale |
|-------|------------|---------|-----------|
| Frontend framework | React | 18.x | Component model + React Query for server state |
| Frontend styling | Tailwind CSS | 3.x | Utility-first; responsive calendar grids without custom CSS |
| Frontend build | Vite | 5.x | Sub-second HMR; TypeScript first-class |
| Frontend state | Zustand + React Query | Latest | Lightweight global state + server-state caching |
| Backend framework | FastAPI | 0.115.x | Async, OpenAPI auto-docs, native Pydantic v2 integration |
| Backend server | Uvicorn | 0.30.x | ASGI server; production-grade with `--reload` for dev |
| DTO validation | Pydantic v2 | 2.7.x | Compile-time and runtime validation; ~10x faster than v1 |
| Testing | pytest + FastAPI TestClient | Latest | In-process HTTP testing; no display server needed |
| CI/CD | GitHub Actions | Latest | Zero infrastructure; free for academic repos |
| Linting | Pylint | 3.x | Enforced at ≥ 8.5/10 score in CI |

---

## 4. API Contract & DTO Specification

All API payloads are governed by Pydantic v2 models. The React client communicates
**exclusively** through these DTOs — it has no knowledge of Python domain objects.
This is the formal Pydantic DTO specification for every API endpoint.

### 4.1 DTO Hierarchy

```
src/api/schemas/
  programme.py   → ProgrammeDTO, ProgrammeListDTO, CourseDetailDTO
  period.py      → ExamPeriodDTO, DateRangeDTO, ExclusionPatchDTO, RangePatchDTO
  schedule.py    → ScheduleDTO, ExamSlotDTO, PaginatedScheduleDTO
  data.py        → UploadResponseDTO, DataStatusDTO
  error.py       → ErrorDTO
```

### 4.2 Core DTOs

```python
# src/api/schemas/programme.py
from pydantic import BaseModel, Field

class CourseDetailDTO(BaseModel):
    course_id:    str
    course_name:  str
    year:         int
    semester:     str                   # "FALL" | "SPRI" | "SUMM"
    requirement:  str                   # "mandatory" | "elective"
    eval_type:    str                   # "Exam" | "Project" | "Participation"

class ProgrammeDTO(BaseModel):
    programme_id:   str = Field(pattern=r"^\d{5}$")
    programme_name: str
    courses:        list[CourseDetailDTO] = []

class ProgrammeListDTO(BaseModel):
    programmes: list[ProgrammeDTO]
    total:      int
```

```python
# src/api/schemas/period.py
from pydantic import BaseModel
from datetime import date

class DateRangeDTO(BaseModel):
    start: date
    end:   date

class ExamPeriodDTO(BaseModel):
    key:          str          # e.g. "FALL_Aleph"
    semester:     str
    moed:         str
    date_ranges:  list[DateRangeDTO]
    excluded:     list[date]   # explicitly excluded dates
    valid_dates:  list[date]   # pre-computed: in-range, not excluded, not weekend

class ExclusionPatchDTO(BaseModel):
    date:     date
    excluded: bool

class RangePatchDTO(BaseModel):
    start: date
    end:   date
```

```python
# src/api/schemas/schedule.py
from pydantic import BaseModel
from datetime import date

class ExamSlotDTO(BaseModel):
    course_id:     str
    course_name:   str
    requirement:   str      # "mandatory" | "elective"
    programmes:    list[str]  # affected programme IDs
    exam_date:     date

class ScheduleDTO(BaseModel):
    schedule_id:   int      # ordinal within this generation run
    period_key:    str
    slots:         list[ExamSlotDTO]

class PaginatedScheduleDTO(BaseModel):
    schedules:    list[ScheduleDTO]
    page:         int
    page_size:    int
    total:        int       # also echoed in X-Total-Count header
```

```python
# src/api/schemas/error.py
from pydantic import BaseModel

class ErrorDTO(BaseModel):
    code:    str    # e.g. "INVALID_FILE", "ENGINE_ERROR", "PROGRAMME_NOT_FOUND"
    message: str    # human-readable, safe to display in UI Toast
    detail:  str | None = None   # optional technical detail for logging
```

```python
# src/api/schemas/generate.py
from pydantic import BaseModel
from typing import Literal, Optional

class GenerationStatusDTO(BaseModel):
    status:          Literal["idle", "running", "completed", "failed"]
    total_schedules: Optional[int] = None   # populated when status == "completed"
    error:           Optional[str] = None   # populated when status == "failed"; safe message only

class GenerateResponseDTO(BaseModel):
    status: Literal["running"]   # always "running" on 202 Accepted
```

### 4.3 API Endpoint Reference

| Method | Path | Request | Response | Notes |
|--------|------|---------|----------|-------|
| `POST` | `/api/data/courses/upload` | Multipart file | `UploadResponseDTO` | Replace mode |
| `PATCH` | `/api/data/courses/upload` | Multipart file | `UploadResponseDTO` | Append mode |
| `POST` | `/api/data/periods/upload` | Multipart file | `UploadResponseDTO` | Replace mode |
| `PATCH` | `/api/data/periods/upload` | Multipart file | `UploadResponseDTO` | Append mode |
| `GET` | `/api/data/status` | — | `DataStatusDTO` | Course count, period count, cache status |
| `GET` | `/api/programmes` | — | `ProgrammeListDTO` | All available programmes |
| `GET` | `/api/programmes/{id}/courses` | — | `list[CourseDetailDTO]` | Drill-down per programme |
| `GET` | `/api/periods` | — | `list[ExamPeriodDTO]` | All loaded exam periods |
| `PATCH` | `/api/periods/{key}/exclusions` | `ExclusionPatchDTO` | `ExamPeriodDTO` | Toggle one day |
| `PATCH` | `/api/periods/{key}/range` | `RangePatchDTO` | `ExamPeriodDTO` | Adjust start/end |
| `POST` | `/api/schedules/generate` | `GenerateRequestDTO` | `202 { "status": "running" }` | Fires `asyncio.to_thread` background generation; returns immediately |
| `GET` | `/api/generate/status` | `X-Session-ID` header | `GenerationStatusDTO` | Polls generation state; responds ≤ 200 ms even during computation; React client polls every 500 ms |
| `GET` | `/api/schedules` | `?page=N&size=M&sort_by=&filter_prog=` | `PaginatedScheduleDTO` | Paginated; `X-Total-Count` header; `sort_by` + `filter_prog` reserved for v3.0 — accepted, documented, safely ignored in v2.0 |
| `GET` | `/api/schedules/{id}/export` | — | `text/plain` stream | Download `.txt` file |

### 4.4 v3.0 Extensibility: Reserved Query Parameters on `GET /api/schedules`

The `GET /api/schedules` route is designed to accept two optional query parameters that are
**inert in v2.0** but structurally wired so that Phase 3 activates them with zero breaking
changes to the API contract, the DTO schema, or the React Query state machine.

```python
# src/api/routes/schedules.py  (v2.0 implementation)

from fastapi import APIRouter, Depends, Query, Response
from typing import Optional
from src.api.schemas.schedule import PaginatedScheduleDTO
from src.api.session import AppSession
from src.api.dependencies import get_session

router = APIRouter()

@router.get("/api/schedules", response_model=PaginatedScheduleDTO)
async def list_schedules(
    page: int          = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int          = Query(1, ge=1, le=50, description="Schedules per page"),

    # ── v3.0 reserved parameters ──────────────────────────────────────────
    sort_by:     Optional[str] = Query(
        None,
        description="[Reserved — v3.0] Sort field: 'date_asc' | 'date_desc' | 'conflict_density'. "
                    "Accepted in v2.0 but ignored in execution logic.",
    ),
    filter_prog: Optional[str] = Query(
        None,
        description="[Reserved — v3.0] Filter by programme ID (5-digit string). "
                    "Accepted in v2.0 but ignored in execution logic.",
    ),
    # ──────────────────────────────────────────────────────────────────────

    session:  AppSession = Depends(get_session),
    response: Response   = None,
):
    """
    Returns one page of generated schedules.

    v2.0 behaviour: `sort_by` and `filter_prog` are parsed and validated by
    FastAPI/Pydantic but are NOT passed to the PaginatedExporter. They appear
    in the OpenAPI/Swagger docs as documented, reserved parameters.

    v3.0 upgrade path: pass `sort_by` and `filter_prog` into a new
    `FilteredPaginatedExporter` adapter — no changes to this route signature,
    no changes to the DTO schema, no changes to the React client.
    """
    # v2.0: sort_by and filter_prog intentionally unused — see docstring above
    exporter = session.exporter
    schedules = exporter.get_page(period_key=session.active_period, page=page - 1)
    total     = exporter.get_total(session.active_period)

    response.headers["X-Total-Count"] = str(total)

    return PaginatedScheduleDTO(
        schedules=[_to_dto(s, exporter.courses_by_id) for s in schedules],
        page=page,
        page_size=size,
        total=total,
    )
```

**Why this is strictly better than a disabled UI button:**
The extensibility lives entirely in the API contract and the frontend query key — both
invisible to the user. No placeholder UI element is rendered, no conditional `disabled`
logic is shipped, and no dead code paths exist in the engine. When Phase 3 activates
`sort_by` and `filter_prog`, the only changes required are: (a) implementing a
`FilteredPaginatedExporter` adapter, and (b) populating the `filters` object in the
React Query key. The route handler signature, the DTO, and the client `apiFetch` call
are all forward-compatible today.

---

## 5. Pagination & Memory Architecture

### 5.1 The Problem: O(n) Laziness Must Survive the API Boundary

The v1.0 `ScheduleGenerator` is a Python **generator** (`yield`). It produces schedules
lazily, one at a time, consuming O(n) memory regardless of how many valid schedules exist.
This is a core performance guarantee of the engine.

A naïve API implementation — one that calls `list(generator.generate_schedules(...))` before
building a JSON response — would silently destroy this guarantee, potentially loading tens of
thousands of schedules into RAM for a complex input set. This is the memory leak risk that
must be addressed architecturally.

> **v2.0.3 Critical Fix (SCRUM-122 → SCRUM-121):** The v2.0.2 `IOutputExporter.export_schedules()`
> interface used `Dict[str, List[Schedule]]` as the `schedules_by_period` parameter type.
> A `List[Schedule]` is not an iterator — passing it required the caller (`AppController`) to
> first materialise the generator via `list(generator)`, silently destroying the O(n) guarantee.
> **Fix:** The interface signature is changed to `Dict[str, Iterator[Schedule]]`. The
> `PaginatedExporter` already consumed the iterator lazily (correct). `TextFileExporter` wraps
> with `list()` internally (its use case is single-schedule export where full materialisation
> is acceptable). `AppController` now passes the raw generator directly. SCRUM-122 (Alon)
> must be merged before SCRUM-121 (Ron) starts — this is an enforced merge-order dependency.

### 5.2 Solution: Server-Side Pagination with `PaginatedExporter`

The solution is a two-phase design:

**Phase 1 — Generation with bounded buffering (background task):**

```python
# src/adapters/paginated_exporter.py

from src.interfaces.i_output_exporter import IOutputExporter   # inward dep ✓
from src.domain.schedule import Schedule
from src.domain.course import Course

PAGE_SIZE = 50   # configurable; controls max RAM per generation run

class PaginatedExporter(IOutputExporter):
    """
    Stores schedules in pages of PAGE_SIZE rather than one flat list.
    The API layer reads one page at a time; pages not yet requested
    are never materialised beyond the generator's lazy production.

    Memory cost: O(PAGE_SIZE) per period, not O(total_schedules).
    """
    def __init__(self) -> None:
        # pages[period_key] = [[Schedule, ...], [Schedule, ...], ...]
        self._pages: dict[str, list[list[Schedule]]] = {}
        self._totals: dict[str, int] = {}
        self.courses_by_id: dict[str, Course] = {}

    def export_schedules(self, schedules_by_period, courses_by_id) -> None:
        self.courses_by_id = courses_by_id
        for period_key, schedule_iter in schedules_by_period.items():
            pages = []
            buffer = []
            total = 0
            for schedule in schedule_iter:   # consumes generator lazily
                buffer.append(schedule)
                total += 1
                if len(buffer) == PAGE_SIZE:
                    pages.append(buffer)
                    buffer = []              # discard reference → GC eligible
            if buffer:
                pages.append(buffer)
            self._pages[period_key] = pages
            self._totals[period_key] = total

    def get_page(self, period_key: str, page: int) -> list[Schedule]:
        """Returns one page (0-indexed). Raises IndexError if out of range."""
        return self._pages.get(period_key, [[]])[page]

    def get_total(self, period_key: str) -> int:
        return self._totals.get(period_key, 0)
```

**Phase 2 — API endpoint serves one page per request:**

```python
# src/api/routes/schedules.py  (excerpt)

@router.get("/api/schedules", response_model=PaginatedScheduleDTO)
async def list_schedules(
    page: int = Query(1, ge=1),
    size: int = Query(1, ge=1, le=50),
    session: AppSession = Depends(get_session),
    response: Response = None,
):
    exporter: PaginatedExporter = session.exporter
    # Only the requested page is ever sent to the client.
    # All other pages remain server-side until explicitly requested.
    schedules = exporter.get_page(period_key=session.active_period, page=page - 1)
    total = exporter.get_total(session.active_period)

    response.headers["X-Total-Count"] = str(total)

    return PaginatedScheduleDTO(
        schedules=[_to_dto(s, exporter.courses_by_id) for s in schedules],
        page=page,
        page_size=size,
        total=total,
    )
```

### 5.3 Memory Guarantee

| Scenario | v1.0 CLI | Naïve API | Paginated API (this design) |
|----------|----------|-----------|----------------------------|
| 10 valid schedules | O(1) yielded | O(10) in RAM | O(PAGE_SIZE) in RAM |
| 10,000 valid schedules | O(1) yielded | O(10,000) in RAM ⚠️ | O(PAGE_SIZE) in RAM ✓ |
| Client requests page 3 | N/A | All 10,000 already loaded | Only page 3 read from buffer |
| Generator exhausted | Immediately | After full materialisation | After full materialisation, but in PAGE_SIZE steps |

The `PaginatedExporter` preserves the generator's laziness **within each page boundary**.
The generator is consumed incrementally as pages are filled. Memory at any point is bounded
by `O(PAGE_SIZE × number_of_active_periods)` — a constant determined by configuration,
not by problem size.

---

## 6. Dependency-Injection Integration Map

### 6.1 Server-Side Session State — UUID `SessionStore`

*(Adopted from Kiro architectural review — see §1 merge rationale.)*

All mutable state (loaded courses, exam periods, generated schedules) is held in a
`SessionState` dataclass, keyed by a UUID inside a singleton `SessionStore`. The React
client receives its UUID in the first response and sends it back on every subsequent
request via the `X-Session-ID` header. This makes the API **strictly stateless** —
the server holds no ambient global session — and supports concurrent clients or
multiple browser tabs without interference.

The `PaginatedExporter` is retained inside `SessionState` (not replaced by Kiro's
flat `InMemoryExporter`) to preserve the O(PAGE_SIZE) memory guarantee (§5).

```python
# src/api/session_store.py
from dataclasses import dataclass, field
from typing import Dict, Optional
import uuid

from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.adapters.paginated_exporter import PaginatedExporter   # ← retained; NOT InMemoryExporter


@dataclass
class SessionState:
    """Server-side state for a single client session, keyed by UUID."""
    session_id:        str              = field(default_factory=lambda: str(uuid.uuid4()))
    courses:           list[Course]     = field(default_factory=list)
    exam_periods:      list[ExamPeriod] = field(default_factory=list)
    selected_programs: list[str]        = field(default_factory=list)
    # PaginatedExporter — preserves O(PAGE_SIZE) memory guarantee
    exporter:          PaginatedExporter = field(default_factory=PaginatedExporter)
    active_period:     str              = ""
    # Generation lifecycle — written by background thread, read by polling endpoint
    generation_status: str              = "idle"   # idle | running | completed | failed
    generation_error:  Optional[str]    = None
    # v2.0.3 (SCRUM-124): atomic lock prevents double-trigger race condition
    generation_lock:   asyncio.Lock     = field(default_factory=asyncio.Lock)


class SessionStore:
    """
    In-memory store mapping UUID session IDs to SessionState objects.
    Thread-safe for single-process deployment (one writer per session at a time).
    For multi-process deployment, replace with a Redis-backed store.
    """
    def __init__(self) -> None:
        self._sessions: Dict[str, SessionState] = {}

    def get_or_create(self, session_id: Optional[str] = None) -> SessionState:
        """Return existing session by ID, or create a fresh one."""
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        state = SessionState()
        self._sessions[state.session_id] = state
        return state

    def get(self, session_id: str) -> Optional[SessionState]:
        """Return session by ID, or None if not found."""
        return self._sessions.get(session_id)
```

### 6.2 New Adapter: `SessionDataProvider`

```python
# src/adapters/session_data_provider.py

from src.interfaces.i_data_provider import IDataProvider      # inward dep ✓
from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.api.session_store import SessionState                 # API layer → adapters is allowed
                                                               # (API is outermost; adapters is inner)

class SessionDataProvider(IDataProvider):
    """
    IDataProvider that reads from the server-side SessionState (UUID-keyed).
    Replaces FileDataProvider in the web context — AppController is unchanged.
    """
    def __init__(self, session: SessionState) -> None:
        self._session = session

    def get_courses(self) -> list[Course]:
        return self._session.courses

    def get_exam_periods(self) -> list[ExamPeriod]:
        return self._session.exam_periods

    def get_selected_programs(self) -> list[str]:
        return self._session.selected_programs
```

### 6.3 FastAPI Dependency Wiring — UUID Session Resolution

*(X-Session-ID header pattern adopted from Kiro architectural review — see §1.)*

```python
# src/api/dependencies.py

import asyncio
from typing import Optional
from fastapi import Depends, Header, HTTPException, Request, Response
from src.api.session_store import SessionState, SessionStore
from src.adapters.session_data_provider import SessionDataProvider
from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.engine.app_controller import AppController
from src.engine.schedule_generator import ScheduleGenerator


def get_session_store(request: Request) -> SessionStore:
    """Retrieves the singleton SessionStore initialised at app startup."""
    return request.app.state.session_store


def get_session(
    response:     Response,
    store:        SessionStore = Depends(get_session_store),
    x_session_id: Optional[str] = Header(None),
) -> SessionState:
    """
    Resolves or creates a SessionState for this request.

    - If X-Session-ID header is present and valid → return existing session.
    - If X-Session-ID is absent or unknown → create a new session.
    - The resolved/new session ID is always written back to the response
      X-Session-ID header so the client can persist it.

    This makes every route handler stateless: it receives a fully-populated
    SessionState object and never touches a global variable.
    """
    if x_session_id:
        session = store.get(x_session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found. "
                                "Start a new session by omitting the X-Session-ID header.")
    else:
        session = store.get_or_create()

    # Echo session ID back so client stores it on the first request
    response.headers["X-Session-ID"] = session.session_id
    return session


def build_controller(session: SessionState) -> AppController:
    """
    Pure DI wiring — no business logic.
    MUST be called once per generation trigger, inside run_generation_background(),
    after the generation_lock is acquired and AFTER confirming status is not "running".
    This ensures selected_programs is snapshotted at call time (SCRUM-66 fix).
    NOT called at startup. NOT called as a FastAPI Depends() directly.
    """
    # Snapshot selected_programs at call time — prevents stale binding if the client
    # updates the selection while generation is in progress (v2.0.3 SCRUM-66 fix).
    selected_programs = list(session.selected_programs)
    data_provider = SessionDataProvider(session)
    strategy  = ExactConflictStrategy(selected_programs=selected_programs)
    generator = ScheduleGenerator(conflict_strategy=strategy)
    return AppController(
        data_provider=data_provider,
        exporter=session.exporter,      # PaginatedExporter — O(PAGE_SIZE) memory guarantee
        generator=generator,
        selected_programs=selected_programs,
    )


GENERATION_TIMEOUT_SECONDS: int = int(os.getenv("GENERATION_TIMEOUT_SECONDS", "120"))


async def run_generation_background(session: SessionState) -> None:
    """
    Background coroutine: runs AppController.run() in a thread pool so the
    FastAPI event loop is never blocked.  Writes generation_status back to
    SessionState so the polling endpoint can read it.

    v2.0.3 changes (SCRUM-123, SCRUM-124, SCRUM-66):
    - Enforces GENERATION_TIMEOUT_SECONDS (default 120 s) via asyncio.wait_for.
      On timeout, status is set to "error" and exporter is reset — no stuck sessions.
    - build_controller() is called once per generation trigger AFTER lock is acquired,
      snapshotting selected_programs at that moment (stale-binding fix).
    """
    try:
        # build_controller called per-generation, inside the lock-guarded section,
        # with a fresh snapshot of selected_programs (SCRUM-66 fix).
        controller = build_controller(session)
        await asyncio.wait_for(
            asyncio.to_thread(controller.run),
            timeout=GENERATION_TIMEOUT_SECONDS,
        )
        session.generation_status = "completed"
        session.generation_error  = None
    except asyncio.TimeoutError:
        session.generation_status = "error"
        session.generation_error  = (
            f"Generation exceeded the {GENERATION_TIMEOUT_SECONDS}s time limit. "
            "Try reducing the number of selected programmes."
        )
        from src.adapters.paginated_exporter import PaginatedExporter
        session.exporter = PaginatedExporter()
    except Exception as exc:
        session.generation_status = "failed"
        session.generation_error  = str(exc)
        # PaginatedExporter is reset so no partial results are accessible
        from src.adapters.paginated_exporter import PaginatedExporter
        session.exporter = PaginatedExporter()
```

### 6.3a Polling Endpoint: `GET /api/generate/status`

```python
# src/api/routes/generate.py  (excerpt)

from fastapi import APIRouter, Depends, BackgroundTasks
from src.api.dependencies import get_session, run_generation_background
from src.api.schemas.generate import GenerationStatusDTO, GenerateResponseDTO
from src.api.session_store import SessionState

router = APIRouter()

@router.post("/api/schedules/generate", status_code=202,
             response_model=GenerateResponseDTO)
async def trigger_generation(
    background_tasks: BackgroundTasks,
    session: SessionState = Depends(get_session),
):
    """
    Fires generation in a background thread; returns 202 immediately.

    v2.0.3 (SCRUM-124): Atomic double-trigger guard via session.generation_lock.
    A second POST while generation is running returns HTTP 409 Conflict + ErrorDTO.
    The lock is acquired before the status check-and-set to eliminate the race condition
    where two concurrent POSTs both read status="idle" and both launch a background task.
    """
    if not session.courses or not session.exam_periods or not session.selected_programs:
        raise HTTPException(status_code=422, detail="Preconditions not met: "
                            "load courses, dates, and select programmes first.")

    # Atomic guard: acquire lock before status check (SCRUM-124)
    if session.generation_lock.locked():
        raise HTTPException(
            status_code=409,
            detail=ErrorDTO(
                code="GENERATION_IN_PROGRESS",
                message="A generation run is already in progress. "
                        "Wait for completion before starting a new one.",
            ).model_dump(),
        )

    async with session.generation_lock:
        # Double-check inside lock (handles the race between lock check and acquire)
        if session.generation_status == "running":
            raise HTTPException(
                status_code=409,
                detail=ErrorDTO(
                    code="GENERATION_IN_PROGRESS",
                    message="A generation run is already in progress.",
                ).model_dump(),
            )
        session.generation_status = "running"
        background_tasks.add_task(run_generation_background, session)

    return GenerateResponseDTO(status="running")


@router.get("/api/generate/status", response_model=GenerationStatusDTO)
async def generation_status(session: SessionState = Depends(get_session)):
    """
    Polling endpoint.  React client calls this every 500 ms after POST /generate.

    Always responds within 200 ms — guaranteed because AppController.run()
    runs in a thread pool, not on the event loop, so this handler is never
    blocked behind the computation.

    Response transitions: idle → running → completed | failed
    """
    total: int | None = None
    if session.generation_status == "completed":
        # Sum totals across all periods from the PaginatedExporter
        total = sum(
            session.exporter.get_total(key)
            for key in session.exporter._totals          # noqa: SLF001
        )
    return GenerationStatusDTO(
        status=session.generation_status,
        total_schedules=total,
        error=session.generation_error,
    )
```

### 6.4 AppController — Zero Modifications

`AppController.__init__` is **unchanged**:
```python
AppController(data_provider, exporter, generator, selected_programs)
```
`SessionDataProvider` replaces `FileDataProvider` and `PaginatedExporter` replaces
`TextFileExporter` — the engine cannot distinguish them from their file-based counterparts.

### 6.5 Global Exception Handler

```python
# src/api/exceptions.py

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from src.api.schemas.error import ErrorDTO

class EngineError(Exception):
    """Raised by adapters for recoverable engine-level failures."""
    def __init__(self, code: str, message: str, detail: str = None):
        self.code = code
        self.message = message
        self.detail = detail

def register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(EngineError)
    async def engine_error_handler(request: Request, exc: EngineError):
        return JSONResponse(
            status_code=422,
            content=ErrorDTO(
                code=exc.code,
                message=exc.message,
                detail=exc.detail,
            ).model_dump(),
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=400,
            content=ErrorDTO(
                code="VALIDATION_ERROR",
                message=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(FileNotFoundError)
    async def file_error_handler(request: Request, exc: FileNotFoundError):
        return JSONResponse(
            status_code=404,
            content=ErrorDTO(
                code="FILE_NOT_FOUND",
                message="The specified data file could not be read on the server.",
                detail=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        # Log full traceback internally; return safe message to client
        import logging, traceback
        logging.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content=ErrorDTO(
                code="INTERNAL_ERROR",
                message="An unexpected error occurred. Please check your input files.",
            ).model_dump(),
        )
```

Every Python exception thrown anywhere in the engine — malformed files, invalid programme
IDs, duplicate exam periods — is caught here, converted to an `ErrorDTO`, and returned as
a clean JSON `422/400/500`. The React frontend receives a structured error object and
renders it as a **Toast notification** (see Section 7.2), preventing any unhandled crash.

### 6.6 CORS Configuration — Environment Variable (v2.0.3, SCRUM-125)

CORS origins are no longer hardcoded to `http://localhost:5173`. They are read from an
environment variable so the app works on any host/port without source changes:

```python
# src/api/main.py  (updated)
import os
from fastapi.middleware.cors import CORSMiddleware

CORS_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

A `.env.example` file is added to the repository root:
```
# .env.example
CORS_ORIGINS=http://localhost:5173
GENERATION_TIMEOUT_SECONDS=120
```

For demos on a non-default host/port, set `CORS_ORIGINS=http://192.168.1.42:3000` in `.env`
without touching source code. See SCRUM-125 for acceptance criteria.

---

## 7. UI/UX Screen Design

### 7.1 Input Screen — React + Tailwind Layout

```
┌────────────────────────────────────────────────────────────────────────────┐
│  examSchedule                                         [▶ Generate]        │
│  ─────────────────────────────────────────────────────────────────────    │
├───────────────────────┬────────────────────────────────────────────────────┤
│  DATA SOURCES         │  EXAM PERIOD CALENDAR                              │
│  ┌─────────────────┐  │  ┌──────────────────────────────────────────────┐  │
│  │ courses.txt     │  │  │  FALL — Moed Aleph        [◀ Prev] [Next ▶]  │  │
│  │ [Browse…]       │  │  │  ─────────────────────────────────────────   │  │
│  │ [↺ Replace]     │  │  │  Sun  Mon  Tue  Wed  Thu  Fri  Sat           │  │
│  │ [+ Append]      │  │  │   ░    ✓    ✓    ✓    ✓    ✓    ░           │  │
│  ├─────────────────┤  │  │   ✓    ✓   [✗]   ✓    ✓    ✓    ░  ← excl. │  │
│  │ dates.txt       │  │  │   ✓    ✓    ✓    ✓    ✓    ✓    ░           │  │
│  │ [Browse…]       │  │  │                                              │  │
│  │ [↺ Replace]     │  │  │  Start: [2026-02-01 ▾]  End: [2026-02-28 ▾] │  │
│  │ [+ Append]      │  │  └──────────────────────────────────────────────┘  │
│  └─────────────────┘  │                                                    │
│                       │  STATUS                                            │
│  PROGRAMMES (max 5)   │  ● Courses: 42   ● Periods: 3   ● Progs: 2       │
│  ┌─────────────────┐  │  ● Cache: FRESH  ● Last run: 14:32               │
│  │ [+ Add ▾]       │  │                                                    │
│  │                 │  │                                                    │
│  │ ▼ 10111 CS      │  │                                                    │
│  │   Y1/FALL Calc  │  │                                                    │
│  │   Y1/FALL Phys  │  │                                                    │
│  │ ▶ 10211 EE      │  │                                                    │
│  └─────────────────┘  │                                                    │
└───────────────────────┴────────────────────────────────────────────────────┘
  ┌────────────────────────────────────────────────────────────────────────┐
  │  ✕  Error: Programme 99999 not found in courses file   [Dismiss]      │  ← Toast
  └────────────────────────────────────────────────────────────────────────┘
```

**Tailwind layout notes:**
- Container: `flex h-screen` — full viewport height
- Sidebar: `w-80 flex-shrink-0 border-r border-gray-200 p-4 overflow-y-auto`
- Main panel: `flex-1 p-6`
- Calendar grid: CSS Grid `grid-cols-7`; excluded cells: `bg-gray-100 line-through text-gray-400 cursor-pointer`
- "Generate" button: `fixed top-4 right-4 bg-blue-600 text-white px-6 py-2 rounded-lg shadow`
- Toast: `fixed bottom-4 left-1/2 -translate-x-1/2 bg-red-50 border border-red-200 rounded-lg px-4 py-3 flex items-center gap-3`
- Colour system: neutral grays for shell; blue-600 primary; red-500 error; green-500 success; amber-500 warning

### 7.2 Toast Notification — Error Handling Flow

When FastAPI returns a non-2xx response, the React API client intercepts the JSON body,
reads the `ErrorDTO`, and dispatches a Toast. The user never sees a raw error or a blank screen.

```typescript
// frontend/src/api/client.ts

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);
  if (!res.ok) {
    const err = await res.json();   // ErrorDTO from FastAPI global handler
    throw new ApiError(err.code, err.message);   // caught by React Query's onError
  }
  return res.json();
}

// React Query usage:
useQuery({
  queryFn: () => apiFetch('/api/schedules?page=1'),
  onError: (err: ApiError) => toast.error(err.message),  // renders Toast component
});
```

### 7.3 Output Screen — React + Tailwind Layout

```
┌────────────────────────────────────────────────────────────────────────────┐
│  examSchedule › Schedule Viewer          [◀ Prev]  3 / 47  [Next ▶]  [💾] │
│  ─────────────────────────────────────────────────────────────────────    │
│  [ FALL Semester — Moed Aleph ]                                            │
│  ┌──────┬──────────────────┬──────────────────┬──────────────────┬──────┐  │
│  │ Week │ Sunday           │ Monday           │ Tuesday          │ ...  │  │
│  ├──────┼──────────────────┼──────────────────┼──────────────────┼──────┤  │
│  │  1   │                  │ 10111 Calculus 1 │                  │      │  │
│  │      │                  │ ◆ Mandatory      │                  │      │  │
│  │      │                  │ CS · EE          │                  │      │  │
│  ├──────┼──────────────────┼──────────────────┼──────────────────┼──────┤  │
│  │  2   │ 20211 Physics 1  │                  │ 30111 Linear Alg │      │  │
│  │      │ ◇ Elective · EE  │                  │ ◆ Mandatory · CS │      │  │
│  └──────┴──────────────────┴──────────────────┴──────────────────┴──────┘  │
│  [ SPRING Semester — Moed Aleph ]  ...                                      │
└────────────────────────────────────────────────────────────────────────────┘
```

**Tailwind layout notes:**
- Nav bar: `flex items-center justify-between px-6 py-3 border-b border-gray-200 sticky top-0 bg-white z-10`
- Calendar: `overflow-x-auto` wrapper; inner `table` with `table-fixed w-full`
- Exam slot cells: `bg-{programme-colour}-50 border border-{programme-colour}-200 rounded p-1 text-xs`
- Programme colour map (Tailwind palette, WCAG AA contrast): `blue`, `emerald`, `violet`, `amber`, `rose`
- Semester group: `mt-8 mb-2 text-sm font-semibold text-gray-500 uppercase tracking-wide`

---

## 8. Jira Epic & Granular Story Breakdown

*All ticket IDs continue from SCRUM-19 (last v1.0 ticket).*
*Branch naming convention enforced: `SCRUM-{ID}/short-description` (see §9.2).*

---

### Epic 1 — FastAPI Backend: Core Infrastructure
*Foundation epic. All other server-side epics depend on this being merged.*

| Ticket | Title | Owner | Acceptance Criteria |
|--------|-------|-------|---------------------|
| **SCRUM-20** | FastAPI app factory + CORS + `SessionStore` lifespan | Ron | `uvicorn src.api.main:create_app --factory` starts on port 8000; `SessionStore` initialised in `@asynccontextmanager lifespan` and stored at `app.state.session_store`; CORS allows `localhost:5173`; `GET /health` returns `{"status":"ok"}` |
| **SCRUM-21** | Pydantic DTO schemas (all) | **Ron** | All schemas in `src/api/schemas/`: `programme`, `period`, `schedule`, `data`, `error`, `generate` modules; includes `GenerationStatusDTO` and `GenerateResponseDTO`; Pydantic v2 validation; `mypy --strict` passes |
| **SCRUM-22** | `SessionStore` + UUID `Depends()` wiring | Alon | `get_session()` reads `X-Session-ID` header; creates new session when absent; echoes session ID in response `X-Session-ID` header; `get(unknown_id)` → 404 + `ErrorDTO`; unit-testable by injecting a mock `SessionStore` |
| **SCRUM-23** | `SessionDataProvider` adapter | Alon | Implements `IDataProvider`; reads from `SessionState` (not `AppSession`); all 3 interface methods return correct domain objects |
| **SCRUM-24** | `PaginatedExporter` adapter | Ron | Implements `IOutputExporter`; stores in `PAGE_SIZE=50` pages; `get_page()` returns correct slice; memory bounded per §5.3 |
| **SCRUM-25** | `JsonCacheAdapter` | Ron | Serialises `list[Course]` + `list[ExamPeriod]` to `data/.cache.json`; mtime-based invalidation; thread-safe; corrupt cache falls back to file-read |
| **SCRUM-26** | Global exception handler | Ron | All 4 exception types registered; each returns correct HTTP status + `ErrorDTO` JSON; unhandled exceptions log full traceback but return safe message |
| **SCRUM-27** | FastAPI composition root wiring | Alon | `build_controller()` injects `SessionDataProvider` + `PaginatedExporter` + `ScheduleGenerator` into `AppController` without modifying engine code |

---

### Epic 2 — FastAPI Backend: API Routes
*Implements all API endpoints from §4.3.*

| Ticket | Title | Owner | Acceptance Criteria |
|--------|-------|-------|---------------------|
| **SCRUM-28** | `POST/PATCH /api/data/courses/upload` | Ron | Multipart file accepted; replace mode clears session courses; append mode merges; returns `UploadResponseDTO` with count |
| **SCRUM-29** | `POST/PATCH /api/data/periods/upload` | Ron | Same pattern as SCRUM-28 for `exam_periods`; returns period count |
| **SCRUM-30** | `GET /api/data/status` | Ron | Returns `DataStatusDTO`: course count, period count, cache freshness, last-run timestamp |
| **SCRUM-31** | `GET /api/programmes` | Alon | Returns `ProgrammeListDTO` derived from session courses; sorted by programme ID |
| **SCRUM-32** | `GET /api/programmes/{id}/courses` | Alon | Returns `list[CourseDetailDTO]`; filtered by programme ID; raises `404 + ErrorDTO` if ID unknown |
| **SCRUM-33** | `GET /api/periods` | Alon | Returns `list[ExamPeriodDTO]` with precomputed `valid_dates` |
| **SCRUM-34** | `PATCH /api/periods/{key}/exclusions` | Ron | Toggles `ExamPeriod.excluded`; re-computes `valid_dates`; returns updated `ExamPeriodDTO` |
| **SCRUM-35** | `PATCH /api/periods/{key}/range` | Ron | Adjusts date range; validates `start < end`; raises `400 + ErrorDTO` on invalid range |
| **SCRUM-36** | `POST /api/schedules/generate` | Ron | Validates preconditions (courses, periods, programmes non-empty); sets `session.generation_status = "running"`; adds `run_generation_background(session)` to `BackgroundTasks`; returns `202 GenerateResponseDTO(status="running")` immediately; background task sets status to `"completed"` or `"failed"` and resets `PaginatedExporter` on failure |
| **SCRUM-36B** | `GET /api/generate/status` (polling endpoint) | Ron | Returns `GenerationStatusDTO` with `status`, `total_schedules` (sum across all periods when completed), and `error` (safe message only); must respond ≤ 200 ms at all times including during active generation; React client polls every 500 ms and navigates to Output Screen on `status == "completed"` |
| **SCRUM-37** | `GET /api/schedules` (paginated + v3.0 reserved params) | Ron | Returns `PaginatedScheduleDTO`; `X-Total-Count` header set; `page`/`size` validated; `sort_by: Optional[str] = None` and `filter_prog: Optional[str] = None` declared as Query params with `[Reserved — v3.0]` OpenAPI descriptions; both params parsed by FastAPI but explicitly unused in v2.0 execution logic (confirmed by code comment in route body); returns `404` if generation not complete; confirmed via `GET /api/schedules?sort_by=date_asc&filter_prog=10111` → same response as without those params |
| **SCRUM-38** | `GET /api/schedules/{id}/export` | Alon | Streams `.txt` file using `TextFileExporter` for single schedule; `Content-Disposition: attachment` header |

---

### Epic 3 — React Frontend: Input Screen
*Implements requirements §2.1–2.4. All API calls use the typed `apiFetch` client.*

| Ticket | Title | Owner | Acceptance Criteria |
|--------|-------|-------|---------------------|
| **SCRUM-39** | React + Vite + Tailwind scaffold | Niv | `npm run dev` serves on port 5173; TypeScript strict mode; ESLint configured; proxy to `localhost:8000` |
| **SCRUM-40** | `api/client.ts` — typed fetch wrapper | Niv | `apiFetch` intercepts non-2xx; throws `ApiError(code, message)`; all DTOs typed with TypeScript interfaces |
| **SCRUM-41** | Toast notification system | Niv | `<Toast>` component; `useToast()` hook; auto-dismisses after 5 s; error/success/warning variants; triggered by `ApiError` in React Query `onError` |
| **SCRUM-42** | File upload panel — courses + dates | Niv | Browse button → `POST /api/data/courses/upload`; Replace/Append mode selection; shows file name after upload; error rendered as Toast |
| **SCRUM-43** | Programme multi-select panel | Niv | Fetches `GET /api/programmes`; checkbox list; max 5 enforced client-side + validated server-side; drill-down expands inline accordion |
| **SCRUM-44** | Course drill-down accordion | Niv | Calls `GET /api/programmes/{id}/courses` on expand; groups by year + semester; mandatory bold, elective italic |
| **SCRUM-45** | `ExamPeriodCalendar` React component | Niv | Renders `ExamPeriodDTO.valid_dates`; excluded dates greyed with strikethrough; click toggles exclusion via `PATCH /api/periods/{key}/exclusions` |
| **SCRUM-46** | Date range pickers per semester | Niv | `<input type="date">` for start/end; calls `PATCH /api/periods/{key}/range`; calendar re-renders from response |
| **SCRUM-47** | Input screen layout + status bar | Niv | 30/70 flex layout; status bar shows `DataStatusDTO` data; polling `GET /api/data/status` every 5 s |
| **SCRUM-48** | "Generate" button + loading state | Niv | Calls `POST /api/schedules/generate`; button disabled during generation; spinner shown; navigates to Output Screen on `generation_done: true` |

---

### Epic 4 — React Frontend: Output Screen
*Implements requirements §3.1–3.5.*

| Ticket | Title | Owner | Acceptance Criteria |
|--------|-------|-------|---------------------|
| **SCRUM-49** | `ScheduleCalendar` React component | Niv | Renders `ScheduleDTO.slots` as a CSS Grid calendar; correct date-to-cell mapping; empty days blank |
| **SCRUM-50** | `ExamSlot` cell component | Niv | Displays course ID, name, `◆/◇` indicator, programme badges; truncates to fit cell; full info on hover tooltip |
| **SCRUM-51** | Semester group layout | Niv | Groups slots by `period_key`; renders separate calendar section per semester/moed; ordered by semester + moed |
| **SCRUM-52** | Navigation bar + pagination (v3.0-ready query key) | Niv | Prev/Next buttons call `GET /api/schedules?page=N`; `X-Total-Count` header read for "X of Y" counter; Prev disabled at page 1, Next at last page; React Query key **must** be structured as `['schedules', { page: currentPage, filters: {} }]` — the empty `filters` object is intentional and load-bearing: when Phase 3 populates it (e.g. `{ page: 1, filters: { sort_by: 'date_asc', filter_prog: '10111' } }`), React Query will automatically detect the key change and trigger a re-fetch with zero state-machine refactoring; confirmed by test: mutating `filters` from `{}` to `{ sort_by: 'date_asc' }` in Storybook/MSW causes the query to re-execute |
| **SCRUM-53** | Programme colour coding | Niv | Maps up to 5 programme IDs to Tailwind colour classes; legend below nav bar; consistent across page navigation |
| **SCRUM-54** | Save schedule button | Niv | Calls `GET /api/schedules/{id}/export`; triggers browser file download; success Toast on completion |

---

### Epic 5 — QA: API Test Suite (FastAPI TestClient)
*Owned by Guy. All tests run in-process — no display server, no browser, no Qt dependency.*

| Ticket | Title | Owner | Acceptance Criteria |
|--------|-------|-------|---------------------|
| **SCRUM-55** | `pytest` + `TestClient` setup | Guy | `conftest.py` with `test_client` fixture using `FastAPI TestClient`; `pytest.ini` configured; all 84 existing tests still pass |
| **SCRUM-56** | Data upload endpoint tests | Guy | Tests for: valid file upload (replace), valid file upload (append), invalid file format, empty file, oversized file; each asserts correct HTTP status + `UploadResponseDTO` shape |
| **SCRUM-57** | Programme endpoint tests | Guy | `GET /api/programmes`: correct list, empty (no courses loaded); `GET /api/programmes/{id}/courses`: known ID, unknown ID (→ 404 + `ErrorDTO`) |
| **SCRUM-58** | Period endpoint tests | Guy | `GET /api/periods`; `PATCH exclusions`: toggle on, toggle off, invalid date; `PATCH range`: valid, end-before-start (→ 400) |
| **SCRUM-59** | Schedule generation + pagination tests | Guy | `POST /api/schedules/generate` with loaded session data; `GET /api/schedules?page=1&size=1` returns correct shape + `X-Total-Count`; `?page=999` returns 404; verifies paginated output matches engine output for known small input |
| **SCRUM-60** | Export endpoint test | Guy | `GET /api/schedules/{id}/export` returns `text/plain`; `Content-Disposition: attachment`; content matches `TextFileExporter` format |
| **SCRUM-61** | Global exception handler tests | Guy | Inject each of the 4 exception types into a route; assert correct HTTP status code + `ErrorDTO.code` field for each |
| **SCRUM-62** | Pagination memory boundary test | Guy | Generate schedules for a dataset producing > 100 results; assert `PaginatedExporter` never holds more than `PAGE_SIZE × N_periods` schedules in a single page buffer |
| **SCRUM-63** | Coverage gate + Pylint | Guy | `pytest-cov` configured; CI fails below 85% overall; `pylint src/` configured; CI fails below 8.5/10 score |

---

### Epic 6 — CI/CD Pipeline (GitHub Actions)
*Owned by Guy. Implements automated quality gates on every Pull Request.*

| Ticket | Title | Owner | Acceptance Criteria |
|--------|-------|-------|---------------------|
| **SCRUM-64** | `ci.yml` — test runner workflow | Guy | Triggers on `pull_request` to `main`; installs deps; runs `pytest --cov`; fails PR merge if any test fails |
| **SCRUM-65** | `ci.yml` — Pylint linting step | Guy | Runs `pylint src/` in CI; fails PR if score < 8.5/10; score printed in workflow output |
| **SCRUM-66** | `ci.yml` — coverage enforcement | Guy | `pytest-cov` generates `coverage.xml`; CI step fails if overall coverage < 85%; uploads report as workflow artefact |
| **SCRUM-67** | Branch protection rules | Guy | Document required GitHub repo settings: `main` branch requires passing `ci.yml` + at least 1 PR approval (Alon) before merge is permitted |
| **SCRUM-68** | Jira–Git branch name automation | Guy | Document and enforce naming convention `SCRUM-{ID}/short-description` via a pre-commit hook (`pre-commit` config file + `branch-name-check.sh`); hook installed in `README` setup instructions |

---

### Epic 7 — Documentation & Delivery

| Ticket | Title | Owner | Acceptance Criteria |
|--------|-------|-------|---------------------|
| **SCRUM-69** | UI/UX Design Document (with v3.0 layout extensibility note) | Alon + Niv | Covers: screen wireframes, component inventory, Tailwind token table (colours/spacing/typography), interaction flows, responsive breakpoints; **must include an explicit architectural note** specifying that the Output Screen top Action Bar is built as a modular `flex` row (`flex items-center gap-4`) where the current elements — Prev/Next navigation, "X of Y" counter, and Save button — each occupy named, independently-sized slots; the document must specify that a future Filter Panel (v3.0) inserts as an additional `flex` child between the counter and the Save button without requiring grid restructuring; the note must confirm: no fixed pixel widths on Action Bar children, no absolute positioning of nav elements, and the calendar grid below uses `flex-1 min-h-0 overflow-auto` so it reflows correctly when the Action Bar grows vertically to accommodate a filter row |
| **SCRUM-70** | Updated Software Design Document | Alon | Extends existing SDD: new API layer diagram, DTO class diagram, updated sequence diagram showing HTTP flow, pagination design |
| **SCRUM-71** | Updated Test Specification | Alon + Guy | Maps SCRUM-55–63 to formal test cases; each entry has: input, expected HTTP status, expected response body shape, pass/fail criteria |
| **SCRUM-72** | `requirements.txt` + `package.json` | Alon | Pinned Python deps (`fastapi`, `uvicorn`, `pydantic`, `pytest`, `pytest-cov`, `pylint`); pinned npm deps; `README.md` setup instructions updated |
| **SCRUM-113** | User Manual — Basic Operation Guide *(post-UI, Sprint 2)* | **Lotem** | Step-by-step end-user guide: launch app, upload files, select programmes, configure calendar, generate, navigate, save; non-technical language; annotated screenshots. **Dependency:** All SCRUM-79 to SCRUM-94 (Epic 2: React UI) must be merged before Lotem begins; screenshots provided by any team member after UI is stable. *Deferred from Sprint 1 in v2.0.3 — Lotem now implements SCRUM-126 in Sprint 1.* |

---

### Epic 8 — v2.0.3 Technical Review: Critical Fixes & Gap Remediations
*Added in v2.0.3 following the post-design technical review. All tasks target Sprint 1 (SCRUM-121 to SCRUM-126) or Sprint 1/2 boundary (SCRUM-127). Merge order constraint: SCRUM-122 must be merged before SCRUM-121 starts.*

| Ticket | Title | Owner | Acceptance Criteria |
|--------|-------|-------|---------------------|
| **SCRUM-121** | AppController streaming refactor — pass raw `Iterator[Schedule]` | **Ron** | `AppController.run()` does NOT call `list()` on the schedule generator; the raw iterator is passed directly to `export_schedules()`; existing 84 engine tests still pass; `PaginatedExporter` memory guarantee preserved. **Blocked on SCRUM-122 merge.** |
| **SCRUM-122** | `IOutputExporter.export_schedules()` interface fix — `Iterator[Schedule]` | **Alon** | Interface signature changed from `Dict[str, List[Schedule]]` to `Dict[str, Iterator[Schedule]]`; `PaginatedExporter.export_schedules()` updated to match; `TextFileExporter.export_schedules()` wraps with `list()` internally; `mypy --strict` passes on all three; existing tests updated. **Must be merged before SCRUM-121.** |
| **SCRUM-123** | Generation timeout — `asyncio.wait_for` + `GENERATION_TIMEOUT_SECONDS` env var | **Ron** | `run_generation_background()` wraps `asyncio.to_thread(controller.run)` in `asyncio.wait_for(timeout=GENERATION_TIMEOUT_SECONDS)`; on `asyncio.TimeoutError` sets `generation_status = "error"` and resets `PaginatedExporter`; `GENERATION_TIMEOUT_SECONDS` env var defaults to 120; `.env.example` updated |
| **SCRUM-124** | Atomic generation guard — `asyncio.Lock` + HTTP 409 on double-trigger | **Alon** | `SessionState` gains `generation_lock: asyncio.Lock`; `POST /api/schedules/generate` acquires lock before check-and-set; simultaneous second POST returns `HTTP 409 Conflict` + `ErrorDTO(code="GENERATION_IN_PROGRESS")`; integration test verifies 409 on concurrent requests |
| **SCRUM-125** | CORS env config — `CORS_ORIGINS` env var, `.env.example` | **Alon** | `CORS_ORIGINS` read from env (comma-separated), default `http://localhost:5173`; `CORSMiddleware` uses the parsed list; `.env.example` documents both `CORS_ORIGINS` and `GENERATION_TIMEOUT_SECONDS`; demo works on non-default host/port without source changes |
| **SCRUM-126** | `src/schemas/` — domain Pydantic models (Lotem's Sprint 1 implementation task) | **Lotem** | Creates `src/schemas/` module with `CourseOfferingSchema`, `CourseSchema`, `ExamPeriodSchema`, `ScheduleSchema`, `ScheduleDetailSchema`; all Pydantic v2 `BaseModel`; **zero imports from `src/presentation/`, `src/api/`, or FastAPI**; standalone unit tests pass; `mypy --strict` passes; fully isolated from API route pipeline |
| **SCRUM-127** | QA — tests for timeout, double-trigger 409, `build_controller` snapshot | **Guy** | Three new test cases: (1) simulate slow `controller.run()` to trigger timeout, assert `status == "error"` and exporter reset; (2) fire two concurrent POSTs, assert second returns 409 + `ErrorDTO`; (3) mutate `session.selected_programs` after `build_controller()` is called, assert controller uses original snapshot |

> **Jira hygiene note (v2.0.3):** SCRUM-61 (SessionStore + UUID `Depends()` wiring) was
> found parented to Epic 2 (React UI) in error. Parent corrected to Epic 1 (Backend API).
> This was a Jira metadata issue only; the task definition and assignee are unchanged.

---

## 9. CI/CD Pipeline & Definition of Done

### 9.1 GitHub Actions Workflow: `ci.yml`

```yaml
# .github/workflows/ci.yml

name: CI — Test, Lint & Coverage

on:
  pull_request:
    branches: [ main ]
  push:
    branches: [ main ]

jobs:
  test:
    name: Python Tests + Coverage + Lint
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run Pytest with coverage
        run: |
          pytest --cov=src --cov-report=xml --cov-report=term-missing \
                 --cov-fail-under=85 -v
        # --cov-fail-under=85 causes a non-zero exit if coverage < 85%
        # This automatically fails the GitHub Actions job and blocks the PR merge

      - name: Upload coverage report
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: coverage.xml

      - name: Run Pylint
        run: |
          pylint src/ --fail-under=8.5
        # --fail-under=8.5 causes a non-zero exit if score < 8.5/10
```

### 9.2 Git–Jira Branch Naming Convention

All branches **must** follow the pattern `SCRUM-{ID}/short-description`.
A `pre-commit` hook enforces this on every developer's machine.

```bash
# .git/hooks/commit-msg  (or via pre-commit framework)
# Also enforced as a documented team rule in README.md

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ ! "$BRANCH" =~ ^SCRUM-[0-9]+/ && "$BRANCH" != "main" ]]; then
  echo "ERROR: Branch name must match 'SCRUM-{ID}/description'. Got: $BRANCH"
  exit 1
fi
```

Examples of valid branch names:
- `SCRUM-28/file-upload-endpoint`
- `SCRUM-49/schedule-calendar-component`
- `SCRUM-64/github-actions-ci`

### 9.3 Definition of Done (DoD)

A ticket is **only** considered Done when **all** of the following criteria are met.
No exceptions. No partial Done.

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| 1 | All code committed on a branch named `SCRUM-{ID}/description` | Branch name pre-commit hook |
| 2 | All existing tests still pass (`pytest` green) | GitHub Actions `ci.yml` |
| 3 | New code is covered by at least one new test | `pytest-cov` diff coverage |
| 4 | Overall coverage remains ≥ 85% | `--cov-fail-under=85` in CI |
| 5 | `pylint src/` score ≥ 8.5/10 | `pylint --fail-under=8.5` in CI |
| 6 | PR opened and linked to Jira ticket (ticket ID in PR title) | Manual check by Alon |
| 7 | **Alon's PR approval obtained** | GitHub branch protection: 1 required reviewer |
| 8 | No secrets, credentials, or `.env` files committed | `git-secrets` pre-commit hook |
| 9 | Acceptance criteria in ticket description all checked off | Jira ticket review |
| 10 | Merged to `main` only after `ci.yml` passes | GitHub branch protection: CI required |

---

## 10. Strategic Team Delegation Matrix

### 10.1 Assignment Table

| Ticket(s) | Owner | Role & Rationale |
|-----------|-------|------------------|
| SCRUM-31–33, 38 (Programme + Period GET routes, Export route) | **Alon** | Read-only routes mapping domain objects to DTOs; requires domain model knowledge; Alon reviews every DTO mapping for correctness |
| SCRUM-20, **21 (API DTO schemas — `src/api/schemas/`)**, 24–26, 28–30, 34–37, **36B (status polling)**, **SCRUM-121 (streaming refactor)**, **SCRUM-123 (generation timeout)** (FastAPI infra, API Pydantic DTOs, Pagination, Cache, Generation, Write routes, UUID session management, critical fixes) | **Ron** | The most algorithmically and architecturally demanding backend work: `SessionStore` + UUID wiring, all API Pydantic DTO schemas (`src/api/schemas/`), async generation pipeline via `asyncio.to_thread` + `asyncio.wait_for`, `PAGE_SIZE`-bounded exporter, mtime-keyed JSON cache, global exception handler, status polling endpoint, all stateful mutation routes, and the streaming refactor. **Note:** Ron owns `src/api/schemas/` (on critical path). Lotem owns the separate `src/schemas/` domain models (SCRUM-126, off critical path). |
| SCRUM-22, 23, 27, 31–33, 38, **SCRUM-122 (interface fix)**, **SCRUM-124 (atomic guard)**, **SCRUM-125 (CORS env)** (Session + DI wiring, domain-facing routes, critical fixes) | **Alon** | Cross-layer architectural decisions: composition root, DI graph, interface contracts, CORS configuration. SCRUM-122 establishes the `Iterator[Schedule]` interface fix and must be merged first (before SCRUM-121). SCRUM-124 adds the atomic generation lock. SCRUM-125 externalises CORS to env vars. |
| SCRUM-39–54 (Entire React + Tailwind frontend) | **Niv** | Full ownership of both screens; Niv's work is bounded entirely to the `frontend/` directory; Niv never imports Python code; all data arrives via `apiFetch()` typed wrappers |
| SCRUM-55–68 (Entire QA suite + CI/CD pipeline) | **Guy** | Sole owner of all quality assurance: TestClient setup, 9 API test files, GitHub Actions `ci.yml`, Pylint configuration, coverage enforcement, branch protection documentation, Jira–Git naming hook |
| SCRUM-69–72 (Design doc, SDD, Test spec, requirements) | **Alon** | System-wide documentation requires Integration Architect perspective; Niv contributes wireframe assets to SCRUM-69 |
| **SCRUM-126 (Sprint 1: `src/schemas/` domain Pydantic models)** | **Lotem** | Isolated implementation task — see §10.2 |
| **SCRUM-113 (Sprint 2: User Manual, post-UI)** | **Lotem** | Deferred to Sprint 2; blocked on all Epic 2 React UI tasks being merged — see §10.2 |
| **SCRUM-127 (QA for timeout + 409 + build_controller snapshot)** | **Guy** | Extends QA coverage for v2.0.3 critical fix tests — see §10.5 |

### 10.2 Lotem — Revised Dual Assignment (v2.0.3): Formal Proof of Non-Blocking

**Sprint 1 task:** SCRUM-126 — `src/schemas/` domain Pydantic models  
**Sprint 2 task:** SCRUM-113 — User Manual: Basic Operation Guide (post-UI)

> **v2.0.3 revision note:** In v2.0.2, Lotem was assigned only SCRUM-73 (User Manual).
> The Kiro assignment of `src/api/schemas/` (FastAPI API schemas) to Lotem was rejected
> because those schemas are imported by every route and are on the critical path.
> In v2.0.3, a genuinely isolated schema module — `src/schemas/` — has been identified.
> These are domain-level Pydantic models with zero dependencies on `src/api/`, FastAPI,
> or any route. SCRUM-126 assigns this module to Lotem in Sprint 1. The User Manual
> (SCRUM-113) is deferred to Sprint 2 where it logically belongs (requires a working UI
> for screenshots). Both tasks satisfy the non-blocking requirement.

#### SCRUM-126 — `src/schemas/` domain Pydantic models

**Nature of task:** Create `src/schemas/__init__.py` and five schema files:
`course_offering.py`, `course.py`, `exam_period.py`, `schedule.py`, `schedule_detail.py`.
Each defines a Pydantic v2 `BaseModel`. Zero imports from `src/presentation/`, `src/api/`,
or FastAPI. Standalone unit tests. `mypy --strict` passes.

**Formal dependency proof (SCRUM-126):**

| Dependency Check | Result | Evidence |
|------------------|--------|----------|
| Does SCRUM-126 import from any API route or FastAPI? | **No** | `src/schemas/` has only `pydantic` and `src/domain/` as dependencies |
| Does any route ticket list SCRUM-126 as a blocker? | **No** | Routes use `src/api/schemas/` (Ron's SCRUM-21) — separate module |
| Would SCRUM-126 being absent prevent the demo? | **No** | Demo critical path is SCRUM-20→22→23→27→36→37→49→52 |
| Does Lotem's delay block any other team member? | **No** | Ron, Niv, Guy, Alon all have fully independent backlogs |
| Is SCRUM-126 on the critical path? | **No** | `src/schemas/` is consumed only in future v3.0 integration |

#### SCRUM-113 — User Manual (Sprint 2)

**Nature of task:** Step-by-step end-user guide in non-technical language: launch app,
upload files, select programmes, configure calendar, generate, navigate, save.
Annotated screenshots supplied by any team member after Epic 2 UI is stable.

**Dependency:** All SCRUM-79 to SCRUM-94 (Epic 2: React UI components) must be merged
before Lotem begins. This is an explicit sequencing constraint — not a blocker for Sprint 1.

**Formal dependency proof (SCRUM-113 in Sprint 2):**

| Dependency Check | Result | Evidence |
|------------------|--------|----------|
| Is SCRUM-113 listed as a `blockedBy` for any other ticket? | **No** | No ticket is gated on the User Manual |
| Would SCRUM-113 being absent prevent the Sprint 1 demo? | **No** | Sprint 1 demo requires backend foundation only |
| Does any Sprint 1 team member depend on Lotem's Sprint 2 output? | **No** | All Sprint 1 backlogs are fully independent |

**Conclusion:** The v2.0 pipeline delivers completely regardless of Lotem's availability.
Both SCRUM-126 and SCRUM-113 are off the critical path. SCRUM-126 provides a meaningful,
isolated Sprint 1 contribution with a clear delivery window.

### 10.3 Ron — High-Complexity Backend Task Detail

Ron's assignments represent the highest-risk, highest-complexity items in the entire sprint:

**SCRUM-24 (`PaginatedExporter`):** Must consume the engine's lazy `Iterator[Schedule]` in
PAGE_SIZE-bounded chunks without ever triggering full materialisation. Requires careful
generator protocol handling and reference management to ensure discarded pages are eligible
for garbage collection.

**SCRUM-25 (`JsonCacheAdapter`):** Must serialise `datetime.date` objects and `Set[date]`
excluded sets to JSON (neither is JSON-serialisable by default). mtime comparison must be
atomic to avoid TOCTOU race conditions. Corrupt or schema-changed cache files must fail
silently with a fallback to file-read — never crash the application.

**SCRUM-26 (Global Exception Handler):** Must correctly intercept exceptions raised deep
inside `AppController.run()` and its collaborators, convert them to `ErrorDTO` instances
with appropriate HTTP status codes, and ensure the full traceback is logged internally
without any sensitive detail leaking to the client response body.

**SCRUM-36 (`POST /api/schedules/generate`):** FastAPI's `BackgroundTasks` runs the
`AppController.run()` call in a thread pool. Ron must correctly manage the session state
flag (`generation_done`) across the async boundary, handle the case where the client polls
`GET /api/schedules` before generation is complete (return `202` with a clear message),
and ensure thread-safety when the exporter writes to the session's `PaginatedExporter`.

### 10.4 Niv — Frontend Implementation Contracts

Niv's implementation is bounded entirely to `frontend/src/`. The contracts Niv depends on:

- **Reads via:** `apiFetch()` typed wrappers returning TypeScript interfaces matching the Pydantic DTOs
- **Error handling via:** `onError: (err: ApiError) => toast.error(err.message)` — Niv never writes try/catch blocks around API calls; the client wrapper handles this uniformly
- **Never imports:** any Python file, any domain class, any adapter or engine module
- **Unblocked when:** SCRUM-20 (FastAPI health endpoint) is merged — Niv can develop against the running backend immediately thereafter. For any endpoint not yet implemented, Niv uses **MSW (Mock Service Worker)** to mock the JSON response during development.

### 10.5 Guy — QA Coverage Targets

| Test Category | Tickets | Target Coverage |
|---------------|---------|-----------------|
| Existing engine unit tests (v1.0) | (unchanged) | 100% pass |
| Data upload API tests | SCRUM-56 | All 5 edge cases covered |
| Programme + Period API tests | SCRUM-57, 58 | All endpoints + all error branches |
| Generation + Pagination API tests | SCRUM-59 | Correct page slicing + header values |
| Export API test | SCRUM-60 | File content correctness |
| Exception handler tests | SCRUM-61 | All 4 exception types |
| Memory boundary test | SCRUM-62 | `PaginatedExporter` buffer size assertion |
| Overall `src/` coverage | SCRUM-63 | ≥ 85% (enforced in CI) |
| Pylint score | SCRUM-63 | ≥ 8.5/10 (enforced in CI) |
| Generation timeout test | **SCRUM-127** | Slow controller triggers `asyncio.TimeoutError`; status = "error"; exporter reset |
| Double-trigger 409 test | **SCRUM-127** | Concurrent POSTs; second returns 409 + `ErrorDTO(code="GENERATION_IN_PROGRESS")` |
| `build_controller` snapshot test | **SCRUM-127** | Mutate `session.selected_programs` after build; assert controller uses original snapshot |

---

## 11. Sprint Plan

### Sprint 1 (Days 1–7) — Backend Foundation + Critical Fixes

**Goal:** FastAPI app running, all DTOs defined, DI wiring complete, critical fixes merged,
existing tests still green. Niv begins frontend scaffold. CI pipeline live. Lotem begins
isolated `src/schemas/` module.

| Ticket | Owner | Days |
|--------|-------|------|
| SCRUM-20 FastAPI scaffold + CORS env config | Ron | 1–2 |
| SCRUM-21 Pydantic API DTO schemas (`src/api/schemas/`) | Ron | 1–3 |
| SCRUM-22 `SessionStore` + UUID `Depends()` wiring | Alon | 2–4 |
| SCRUM-23 `SessionDataProvider` | Alon | 4–5 |
| SCRUM-24 `PaginatedExporter` | Ron | 3–5 |
| SCRUM-25 `JsonCacheAdapter` | Ron | 5–7 |
| SCRUM-26 Global exception handler | Ron | 4–5 |
| SCRUM-27 Composition root wiring | Alon | 5–6 |
| **SCRUM-122** IOutputExporter interface fix (`Iterator[Schedule]`) | Alon | 2–3 *(merge before SCRUM-121)* |
| **SCRUM-121** AppController streaming refactor | Ron | 4–5 *(after SCRUM-122 merged)* |
| **SCRUM-123** Generation timeout (`asyncio.wait_for`) | Ron | 5–6 |
| **SCRUM-124** Atomic generation guard (`asyncio.Lock` + 409) | Alon | 3–4 |
| **SCRUM-125** CORS env config (`.env.example`) | Alon | 2 |
| **SCRUM-126** `src/schemas/` domain Pydantic models | **Lotem** | 1–7 *(async, fully isolated)* |
| SCRUM-39 React + Vite + Tailwind scaffold | Niv | 1–2 |
| SCRUM-40 `api/client.ts` typed wrapper | Niv | 2–3 |
| SCRUM-41 Toast notification system | Niv | 3–4 |
| SCRUM-55 `pytest` + `TestClient` setup | Guy | 1–2 |
| SCRUM-64 `ci.yml` test runner | Guy | 2–3 |
| SCRUM-65 Pylint CI step | Guy | 3 |
| SCRUM-66 Coverage enforcement CI | Guy | 4 |
| SCRUM-68 Branch naming pre-commit hook | Guy | 5 |
| **SCRUM-127** QA for timeout + 409 + snapshot tests | Guy | 6–7 |

> **Merge order constraint:** SCRUM-122 (Alon) must be merged and green in CI before
> Ron opens a PR for SCRUM-121. Alon targets Day 3 completion for SCRUM-122.

**Sprint 1 exit criteria:** `GET /health` → 200; all 84 existing tests pass in CI; SCRUM-121/122/123/124/125 all merged; React dev server renders; `ci.yml` green on `main`.

---

### Sprint 2 (Days 8–16) — API Routes + Both Screens

**Goal:** All API endpoints implemented. Input and Output screens fully functional.
Lotem begins User Manual once Epic 2 UI components are stable.

| Ticket | Owner | Days |
|--------|-------|------|
| SCRUM-28–30 Upload routes (courses + dates) | Ron | 8–10 |
| SCRUM-31–33 Programme + Period GET routes | Alon | 8–10 |
| SCRUM-34–35 Period PATCH routes | Ron | 10–11 |
| SCRUM-36, 36B Generate + status polling + paginated GET | Ron | 11–14 |
| SCRUM-38 Export route | Alon | 14–15 |
| SCRUM-42–48 Input screen components | Niv | 8–14 |
| SCRUM-49–54 Output screen components | Niv | 12–16 |
| SCRUM-56–58 Upload + Programme + Period tests | Guy | 8–12 |
| SCRUM-59–61 Generation + Export + Exception tests | Guy | 12–16 |
| SCRUM-69 UI/UX design doc | Alon + Niv | 8–11 |
| **SCRUM-113** User Manual (post-UI) | **Lotem** | 14–16 *(after Epic 2 tasks merged)* |

**Sprint 2 exit criteria:** Full end-to-end user flow works in browser; all API tests pass; > 80% coverage.

---

### Sprint 3 (Days 17–21) — Integration, QA & Delivery

**Goal:** Memory test, coverage gate ≥ 85%, all documentation, release candidate.

| Ticket | Owner | Days |
|--------|-------|------|
| SCRUM-62 Pagination memory boundary test | Guy | 17–18 |
| SCRUM-63 Coverage gate + Pylint gate | Guy | 18–19 |
| SCRUM-67 Branch protection documentation | Guy | 19 |
| SCRUM-70 Updated SDD | Alon | 17–19 |
| SCRUM-71 Updated Test Specification | Alon + Guy | 19–20 |
| SCRUM-72 `requirements.txt` + `package.json` | Alon | 20 |
| Bug fixes, code review, PR approvals | Alon | 17–21 |

**Sprint 3 exit criteria:** All 89+ tests green in CI; coverage ≥ 85%; Pylint ≥ 8.5; all docs merged; demo rehearsal passes end-to-end.

---

## 12. Risk Register

| Risk | Prob. | Impact | Owner | Mitigation |
|------|-------|--------|-------|------------|
| **[RESOLVED v2.0.3]** `AppController.run()` calls `list()` on generator — destroys O(n) memory guarantee | — | — | Alon/Ron | Fixed: SCRUM-122 changes `IOutputExporter` interface to `Iterator[Schedule]`; SCRUM-121 refactors `AppController` to pass raw iterator. Merge order enforced: SCRUM-122 before SCRUM-121. |
| **[RESOLVED v2.0.3]** Double-trigger of `POST /api/schedules/generate` fires two concurrent background tasks | — | — | Alon | Fixed: SCRUM-124 adds `asyncio.Lock` on `SessionState`; returns HTTP 409 + `ErrorDTO` on second trigger. |
| **[RESOLVED v2.0.3]** No timeout on `run_generation_background()` — sessions can get permanently stuck in "running" state | — | — | Ron | Fixed: SCRUM-123 wraps `asyncio.to_thread(controller.run)` in `asyncio.wait_for(timeout=GENERATION_TIMEOUT_SECONDS)`; on timeout sets status to "error" and resets exporter. |
| **[RESOLVED v2.0.3]** CORS hardcoded to `localhost:5173` — demo breaks on any other host/port | — | — | Alon | Fixed: SCRUM-125 reads `CORS_ORIGINS` from env var; `.env.example` documents the variable. |
| **[RESOLVED v2.0.3]** `selected_programs` stale binding — `AppController` built with programs snapshot from startup, not from generation-trigger time | — | — | Alon | Fixed: SCRUM-66 updated to call `build_controller(session)` once per generation trigger inside `run_generation_background()`, snapshotting `list(session.selected_programs)` at that instant. |
| **MERGE ORDER RISK:** SCRUM-121 starts before SCRUM-122 is merged | Medium | High | Alon | Enforced via branch protection: SCRUM-121 PR description must reference SCRUM-122 merge SHA; Alon's PR review blocks SCRUM-121 merge if SCRUM-122 is not already green in `main`. |
| `BackgroundTasks` thread-safety bug causes race condition on `SessionState.generation_status` | Low | Medium | Ron | **Mitigated by SCRUM-124** (asyncio.Lock). Remaining single-writer pattern for status field (only `run_generation_background` mutates it post-lock) eliminates residual risk. |
| Backtracking generates > 10,000 schedules; `PaginatedExporter` RAM still spikes during full consumption | Medium | Medium | Ron | Add configurable `MAX_SCHEDULES` hard cap (default 2,000) in `AppController`; document as known limitation |
| React Query cache serves stale schedule data after re-generation | Medium | Medium | Niv | Invalidate React Query `schedules` cache key on `POST /api/schedules/generate` success |
| CI takes > 5 minutes; developers skip PR process | Low | Medium | Guy | Add `pytest -x` (stop on first failure) in CI; target < 90-second CI wall time |
| Pylint fails on valid code (false positives) | Low | Low | Guy | Add `# pylint: disable=...` annotations only with PR comment explaining the suppression; Alon approves |
| Niv blocked waiting for an unimplemented API route | Medium | Medium | Niv | Niv uses MSW mock handlers during development; unblocked from day 1 |
| Lotem unavailable for entire sprint (miluim extension) | High | **None** | — | SCRUM-126 and SCRUM-113 both have zero blocking dependencies on the critical path; pipeline unaffected; see §10.2 |
| FastAPI not permitted in course grading environment | Low | High | Alon | Document `pip install fastapi uvicorn pydantic` in `README`; provide pinned `requirements.txt`; test in clean venv before submission |

---

---

## 13. Correctness Properties

*(Section adopted from Kiro architectural review and adapted to the examSchedule v2.0
paginated architecture. All property references to `InMemoryExporter` have been replaced
with `PaginatedExporter`. Properties 20–22 are original additions covering the UUID
session model, async polling contract, and v3.0 reserved parameter pass-through.)*

A **correctness property** is a formal, machine-verifiable statement about system behaviour
that must hold true across all valid executions. Properties serve as the bridge between
human-readable requirements and executable test assertions. Every property below maps
directly to one or more requirements from *מסמך דרישות תוכנה – שלב 2* and to one or more
test tickets in Epic 5 (QA).

---

### Property 1 — Pydantic Schema Round-Trip Fidelity

*For any* valid domain object (`Course`, `CourseOffering`, `ExamPeriod`, or `Schedule`),
converting it to its corresponding Pydantic DTO and back to a domain object SHALL produce
an object with field values identical to the original — no data loss, no type coercion.

**Validates:** Requirement §2.1, §3.4 (API field completeness)  
**Test ticket:** SCRUM-56 (upload round-trip), SCRUM-59 (schedule DTO field verification)

---

### Property 2 — `SessionDataProvider` Faithfulness

*For any* `SessionState` containing courses, exam periods, and selected programmes,
calling `SessionDataProvider.get_courses()`, `.get_exam_periods()`, and
`.get_selected_programs()` SHALL return exactly those objects without modification,
copy, or filtering.

**Validates:** Requirement §1 (IDataProvider contract)  
**Test ticket:** SCRUM-46 (`GUIDataProvider` / `SessionDataProvider` unit tests)

---

### Property 3 — `PaginatedExporter` Completeness and Boundedness

*For any* `schedules_by_period` dict passed to `PaginatedExporter.export_schedules()`,
two sub-properties SHALL hold simultaneously:

- **Completeness:** The sum of `get_total(key)` across all period keys SHALL equal the
  total number of `Schedule` objects produced by the generator.
- **Boundedness:** At no point during `export_schedules()` execution SHALL any single
  page buffer hold more than `PAGE_SIZE` schedules simultaneously.

**Validates:** Requirement §3.1 (schedule count display), §5.2 (< 1 s responsiveness via memory control)  
**Test ticket:** SCRUM-62 (pagination memory boundary test)

> **Rejection note:** Kiro's Property 3 refers to `InMemoryExporter.export_schedules()`
> capturing all schedules as a flat list. This property is explicitly replaced because the
> flat-list design destroys the O(n) memory guarantee. `PaginatedExporter` is the correct
> implementation.

---

### Property 4 — File Upload Replace Mode Exactness

*For any* valid courses file content, uploading in "replace" mode SHALL result in
`SessionState.courses` containing exactly the courses parsed by `CourseFileReader` from
that file, with the response count equal to `len(session.courses)`. No previously loaded
courses SHALL remain.

**Validates:** Requirement §2.1.2  
**Test ticket:** SCRUM-56 (data upload endpoint tests — replace branch)

---

### Property 5 — File Upload Append Mode Preservation

*For any* `SessionState` containing N courses and any valid courses file producing M
additional courses, uploading in "append" mode SHALL result in `SessionState.courses`
containing exactly N + M courses — all original courses preserved, all new courses added,
no duplicates introduced.

**Validates:** Requirement §2.1.3  
**Test ticket:** SCRUM-56 (data upload endpoint tests — append branch)

---

### Property 6 — Malformed Upload Returns 422

*For any* file content that causes `CourseFileReader.read()` or
`ExamPeriodFileReader.read()` to raise a `ValueError`, the upload endpoint SHALL return
HTTP 422 with an `ErrorDTO` whose `message` field contains a human-readable description
identifying the offending line or field. `SessionState` SHALL be unchanged.

**Validates:** Requirement §2.1 (error handling)  
**Test ticket:** SCRUM-56 (malformed file edge case)

---

### Property 7 — Programme List Derivation Completeness

*For any* set of courses in `SessionState`, `GET /api/programmes` SHALL return exactly
the distinct set of `programme_id` values found across all `CourseOffering` objects in
those courses — no omissions, no phantom entries.

**Validates:** Requirement §2.2  
**Test ticket:** SCRUM-57 (programme endpoint tests)

---

### Property 8 — Programme Selection Validation Gate

*For any* list of programme IDs submitted to the selection endpoint, the endpoint SHALL
accept the request if and only if all IDs exist in `SessionState.courses` offerings AND
`len(ids) ≤ 5`. Any other combination SHALL return HTTP 422 identifying the specific
violation (unknown ID or excess count).

**Validates:** Requirements §2.2 (max 5), §2.2 (ID validation)  
**Test ticket:** SCRUM-57 (programme endpoint tests — boundary cases)

---

### Property 9 — Day Exclusion Toggle Symmetry

*For any* `ExamPeriod` and any valid date within its date ranges, toggling the exclusion
status twice SHALL return the period to its original state — the date is back in (or out of)
`excluded` exactly as it was before the first toggle.

**Validates:** Requirement §2.4.2  
**Test ticket:** SCRUM-58 (period endpoint tests — toggle symmetry)

---

### Property 10 — Date Range Ordering Invariant

*For any* pair of dates `(start, end)` submitted to the period range endpoint, the
endpoint SHALL accept the update if and only if `start ≤ end`. When `start > end`,
it SHALL return HTTP 400 + `ErrorDTO(code="VALIDATION_ERROR")` without mutating
`SessionState`.

**Validates:** Requirement §2.4.3  
**Test ticket:** SCRUM-58 (period endpoint tests — invalid range)

---

### Property 11 — Generation Precondition Enforcement

*For any* `SessionState`, `POST /api/schedules/generate` SHALL return HTTP 422 listing
all unmet preconditions if any of `courses`, `exam_periods`, or `selected_programs` is
empty. It SHALL proceed and return `202` only when all three are non-empty.

**Validates:** Requirement §2 (run preconditions)  
**Test ticket:** SCRUM-59 (schedule generation tests — precondition branches)

---

### Property 12 — Generation Failure Leaves No Partial State

*For any* input that causes `AppController.run()` to raise an exception inside the
background thread, the following SHALL hold simultaneously:

- `SessionState.generation_status == "failed"`
- `SessionState.generation_error` contains a safe, non-empty string
- `SessionState.exporter` is a freshly-initialised `PaginatedExporter` with no pages
- `GET /api/schedules?page=1` returns 404 (generation not complete)

**Validates:** Requirement §5 (error handling, no partial results)  
**Test ticket:** SCRUM-61 (global exception handler tests)

---

### Property 13 — Paginated Endpoint Slice Correctness

*For any* completed generation run with total T schedules for a given period, and for
any valid page number P and page size S (where `P × S ≤ T`), `GET /api/schedules?page=P&size=S`
SHALL return exactly the schedules at ordinal positions `[(P-1)×S, P×S)` in the
`PaginatedExporter` buffer for that period, and the `X-Total-Count` response header
SHALL equal T.

**Validates:** Requirement §3.1–3.3 (schedule browsing, X of Y counter)  
**Test ticket:** SCRUM-59 (pagination correctness and header value)

---

### Property 14 — Navigation Button State Invariant

*For any* current page P and total page count T, the React "Previous" button SHALL be
disabled if and only if `P == 1`, and the "Next" button SHALL be disabled if and only
if `P == T`. Both conditions are derived from the `X-Total-Count` header value.

**Validates:** Requirement §3.2 (navigation controls)  
**Test ticket:** SCRUM-52 acceptance criteria (Niv), SCRUM-59 (Guy — header value verified)

---

### Property 15 — Calendar Cell Placement Correctness

*For any* `ScheduleDTO` and any `ExamSlotDTO` within it, the React calendar SHALL render
that slot in the grid cell whose date column matches `slot.exam_date`. No slot SHALL
appear in a cell whose date differs from its `exam_date`.

**Validates:** Requirement §3.1 (calendar view accuracy)  
**Test ticket:** SCRUM-49 acceptance criteria (Niv), SCRUM-50 (MSW integration)

---

### Property 16 — Period Sort Order Consistency

*For any* set of exam periods returned by `GET /api/periods` or embedded in schedule
results, the ordering SHALL match `AppController._sort_exam_periods` — FALL < SPRI < SUMM,
Aleph < Bet < Gimel — both in the API response array and in the React calendar section
rendering order.

**Validates:** Requirement §3.1 (calendar chronological order)  
**Test ticket:** SCRUM-51 acceptance criteria (Niv)

---

### Property 17 — Run Button Precondition Gate (Frontend)

*For any* combination of data-loading state (courses loaded / not, periods loaded / not,
programmes selected / not), the React "Generate" button SHALL be enabled if and only if
all three conditions are satisfied simultaneously: `courseCount > 0 AND periodCount > 0
AND programmeCount > 0`.

**Validates:** Requirement §2 (run preconditions reflected in UI)  
**Test ticket:** SCRUM-48 acceptance criteria

---

### Property 18 — Status Summary Accuracy

*For any* `SessionState`, the React status bar SHALL display counts that exactly match
`len(session.courses)`, `len(session.exam_periods)`, and `len(session.selected_programs)`
as returned by `GET /api/data/status`. The display SHALL update within 5 seconds of any
data-loading or selection action (polling interval).

**Validates:** Requirement §2 (status display)  
**Test ticket:** SCRUM-47 acceptance criteria

---

### Property 19 — Save Endpoint Output Format Invariance

*For any* valid schedule index, the file written by `GET /api/schedules/{id}/export`
SHALL be byte-for-byte identical to the output that `TextFileExporter.export_schedules()`
would produce when called with the same single-schedule `schedules_by_period` dict and
`courses_by_id` map.

**Validates:** Requirement §3.5 (human-readable file format)  
**Test ticket:** SCRUM-60 (export endpoint content test)

---

### Property 20 — UUID Session Isolation (New — not in Kiro)

*For any* two concurrent clients with distinct `X-Session-ID` values, mutations to one
client's `SessionState` (file uploads, programme selection, generation) SHALL have no
observable effect on the other client's `SessionState`. This property is verified by
issuing interleaved requests from two distinct session IDs and asserting independent state.

**Validates:** §6.1 (multi-client safety), Requirement §11 (reliability)  
**Test ticket:** SCRUM-55 integration test — session isolation scenario

---

### Property 21 — Status Polling Response Time Guarantee (New — not in Kiro)

*For any* `SessionState.generation_status` value (`idle`, `running`, `completed`, `failed`),
`GET /api/generate/status` SHALL return a valid `GenerationStatusDTO` with HTTP 200 within
200 milliseconds, measured from request receipt to response first-byte, even while
`AppController.run()` is executing concurrently in a thread pool.

**Validates:** Requirement §5.2 (responsiveness during generation), §6.1 (non-blocking async)  
**Test ticket:** SCRUM-51 (performance / responsiveness test) — extended to cover polling

---

### Property 22 — v3.0 Reserved Parameters Are Inert in v2.0 (New — not in Kiro)

*For any* request to `GET /api/schedules` that includes `sort_by` and/or `filter_prog`
query parameters with any non-empty string values, the response body and `X-Total-Count`
header SHALL be identical to the response from the same request without those parameters.
The parameters SHALL appear in the OpenAPI schema with `[Reserved — v3.0]` descriptions.

**Validates:** §4.4 (v3.0 future-proofing, no breaking changes)  
**Test ticket:** SCRUM-59 — extended assertion: parameterised vs. unparameterised response equality

---

*Document prepared for direct import into the team Jira board, GitHub repository, and course submission package.*  
*All ticket IDs are sequential continuations from the last v1.0 ticket (SCRUM-19), with SCRUM-36B inserted between SCRUM-36 and SCRUM-37.*  
*v2.0.3 adds SCRUM-121 through SCRUM-127 following the post-design technical review. Jira Epics are SCRUM-54 to SCRUM-58; tasks SCRUM-59 to SCRUM-120 correspond to the original 61 planned stories; tasks SCRUM-121 to SCRUM-127 are the critical-fix additions.*  
*All merges to `main` require: passing `ci.yml` + Alon's explicit PR approval.*  
*Branch naming convention: `SCRUM-{ID}/short-description` — enforced by pre-commit hook (SCRUM-68).*  
*Critical merge order: SCRUM-122 must be merged and CI-green before SCRUM-121 PR is opened.*
