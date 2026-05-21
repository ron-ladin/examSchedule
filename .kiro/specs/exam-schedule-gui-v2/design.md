# Design Document - examSchedule GUI v2.0

## Introduction

This document describes the technical design for upgrading examSchedule from a CLI application (v1.0) to a web-based GUI (v2.0) using FastAPI as the backend and React (TypeScript) as the frontend. The core principle is that **no existing source file is modified** - FastAPI replaces the CLI as the composition root, injecting new adapter implementations into the unchanged engine layer.

---

## Architectural Blueprint

### Layer Diagram (v2.0)

The existing five-layer Clean Architecture is preserved. A new **Presentation Layer** is added as the outermost shell:

```
Frontend (React/TS SPA)
    |  HTTP/JSON
    v
Presentation Layer (NEW - src/presentation/)
    FastAPI App (composition root)
    APIDataProvider (implements IDataProvider)
    InMemoryExporter (implements IOutputExporter)
    |
    v
Engine Layer (UNCHANGED - src/engine/)
    AppController, ScheduleGenerator
    |
    v
Interfaces Layer (UNCHANGED - src/interfaces/)
    IDataProvider, IOutputExporter, IScheduleGenerator, IConflictStrategy
    |
    v
Adapters Layer (UNCHANGED - src/adapters/)
    FileDataProvider, TextFileExporter, ExactConflictStrategy, Readers
    |
    v
Domain Layer (UNCHANGED - src/domain/)
    Course, CourseOffering, ExamPeriod, Schedule, semester.py
```

### Key Architectural Decisions

1. **FastAPI as Composition Root**: FastAPI replaces `main.py` (argparse CLI) as the outermost layer that wires dependencies together. The `AppController` constructor signature remains unchanged.
2. **New Adapters, Not Modified Ones**: Two new adapter classes (`APIDataProvider`, `InMemoryExporter`) implement existing interfaces. The existing `FileDataProvider` and `TextFileExporter` remain untouched.
3. **Existing Readers Reused**: `CourseFileReader` and `ExamPeriodFileReader` are instantiated by the upload endpoints to parse uploaded files. They are not modified.
4. **Session State**: Server-side in-memory storage (Python dict keyed by session ID) holds parsed data between requests.
5. **Non-blocking Generation**: `AppController.run()` is CPU-bound; it runs via `asyncio.to_thread()` to avoid blocking the event loop.

---

## New File Structure

```
src/
  schemas/                    # Lotem (isolated)
    __init__.py
    course_schema.py          # CourseSchema, CourseOfferingSchema
    exam_period_schema.py     # ExamPeriodSchema
    schedule_schema.py        # ScheduleSchema, ScheduleDetailSchema
  presentation/               # Alon + Ron
    __init__.py
    app.py                    # FastAPI app factory, CORS, lifespan
    dependencies.py           # Depends() providers (get_session, etc.)
    session_store.py          # SessionState dataclass + in-memory store
    adapters/
      __init__.py
      api_data_provider.py    # APIDataProvider (IDataProvider)
      in_memory_exporter.py   # InMemoryExporter (IOutputExporter)
    routers/
      __init__.py
      upload.py               # POST /api/upload/courses, /api/upload/dates
      programs.py             # GET /api/programs, POST /api/programs/select
      periods.py              # GET /api/periods, PATCH /api/periods/{id}
      generate.py             # POST /api/generate, GET /api/generate/status
      schedules.py            # GET /api/schedules/{index}, POST /api/schedules/save
      health.py               # GET /health
frontend/                      # Niv
  src/
    App.tsx
    pages/
      InputScreen.tsx
      OutputScreen.tsx
    components/
      FileUploader.tsx
      ProgramSelector.tsx
      ProgramDrillDown.tsx
      ExamPeriodCalendar.tsx
      StatusSummary.tsx
      ScheduleCalendar.tsx
      ScheduleNavigation.tsx
      ExamSlot.tsx
    api/
      client.ts               # Axios/fetch wrapper
      types.ts                # TypeScript interfaces mirroring Pydantic schemas
    hooks/
      useSession.ts
      useGeneration.ts
      useScheduleBrowser.ts
```

---

## Team Delegation

| Member | Role | Scope |
|--------|------|-------|
| **Alon** (Team Lead) | Architecture scaffolding | `src/presentation/app.py`, `APIDataProvider`, `InMemoryExporter`, FastAPI setup, integration, PR reviews |
| **Niv** (Frontend) | React SPA | `frontend/` - Input Screen, Output Screen, calendar component, navigation |
| **Guy** (Testing) | Quality assurance | API integration tests, frontend E2E tests, performance/reactivity tests |
| **Ron** (Backend) | Endpoint implementation | File upload endpoints, session state management, schedule generation endpoint, save endpoint, complex data mutations |
| **Lotem** (Miluim - isolated) | Pydantic schemas | `src/schemas/` - zero dependencies on other work, can be merged independently |

---

## Components and Interfaces

### Session State Model

```python
# src/presentation/session_store.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from datetime import date
import uuid

from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule


@dataclass
class SessionState:
    """Server-side state for a single user session."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    courses: List[Course] = field(default_factory=list)
    exam_periods: List[ExamPeriod] = field(default_factory=list)
    selected_programs: List[str] = field(default_factory=list)
    # Generation results
    schedules_by_period: Optional[Dict[str, List[Schedule]]] = None
    courses_by_id: Optional[Dict[str, Course]] = None
    generation_status: str = "idle"  # idle | running | completed | failed
    generation_error: Optional[str] = None


class SessionStore:
    """In-memory session store. Thread-safe for single-process deployment."""

    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}

    def get_or_create(self, session_id: Optional[str] = None) -> SessionState:
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        state = SessionState()
        self._sessions[state.session_id] = state
        return state

    def get(self, session_id: str) -> Optional[SessionState]:
        return self._sessions.get(session_id)
```

### APIDataProvider

```python
# src/presentation/adapters/api_data_provider.py
from typing import List

from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.interfaces.i_data_provider import IDataProvider


class APIDataProvider(IDataProvider):
    """
    Implements IDataProvider by reading from server-side session state.
    Injected into AppController at generation time.
    """

    def __init__(
        self,
        courses: List[Course],
        exam_periods: List[ExamPeriod],
        selected_programs: List[str],
    ):
        self._courses = courses
        self._exam_periods = exam_periods
        self._selected_programs = selected_programs

    def get_courses(self) -> List[Course]:
        return self._courses

    def get_exam_periods(self) -> List[ExamPeriod]:
        return self._exam_periods

    def get_selected_programs(self) -> List[str]:
        return self._selected_programs
```

### InMemoryExporter

```python
# src/presentation/adapters/in_memory_exporter.py
from typing import Dict, List, Optional

from src.domain.course import Course
from src.domain.schedule import Schedule
from src.interfaces.i_output_exporter import IOutputExporter


class InMemoryExporter(IOutputExporter):
    """
    Implements IOutputExporter by storing schedules in memory.
    Results are retrieved after AppController.run() completes.
    """

    def __init__(self):
        self.schedules_by_period: Optional[Dict[str, List[Schedule]]] = None
        self.courses_by_id: Optional[Dict[str, Course]] = None

    def export_schedules(
        self,
        schedules_by_period: Dict[str, List[Schedule]],
        courses_by_id: Dict[str, Course],
    ) -> None:
        self.schedules_by_period = schedules_by_period
        self.courses_by_id = courses_by_id
```

### Pydantic Schemas (Lotem - Isolated)

```python
# src/schemas/course_schema.py
from pydantic import BaseModel
from typing import List


class CourseOfferingSchema(BaseModel):
    program_id: str
    year: int
    semester: str
    requirement: str

    model_config = {"from_attributes": True}


class CourseSchema(BaseModel):
    id: str
    name: str
    instructor: str
    evaluation_type: str
    offerings: List[CourseOfferingSchema]

    model_config = {"from_attributes": True}
```

```python
# src/schemas/exam_period_schema.py
from pydantic import BaseModel
from typing import List, Set, Tuple
from datetime import date


class ExamPeriodSchema(BaseModel):
    semester: str
    moed: str
    date_ranges: List[Tuple[date, date]]
    excluded_dates: Set[date]

    model_config = {"from_attributes": True}
```

```python
# src/schemas/schedule_schema.py
from pydantic import BaseModel
from typing import Dict
from datetime import date

from src.schemas.exam_period_schema import ExamPeriodSchema
from src.schemas.course_schema import CourseSchema


class ScheduleSchema(BaseModel):
    period: ExamPeriodSchema
    assignments: Dict[str, date]  # course_id -> exam date (ISO 8601)

    model_config = {"from_attributes": True}


class ExamAssignmentDetailSchema(BaseModel):
    course: CourseSchema
    assigned_date: date
    affected_program_ids: List[str]
    obligation_type: str


class ScheduleDetailSchema(BaseModel):
    period: ExamPeriodSchema
    assignments: Dict[str, date]
    details: List[ExamAssignmentDetailSchema]

    model_config = {"from_attributes": True}
```

**Conversion helpers** (in each schema module):

```python
# Example: src/schemas/course_schema.py (additional)
from src.domain.course import Course
from src.domain.course_offering import CourseOffering


def course_to_schema(course: Course) -> CourseSchema:
    return CourseSchema.model_validate(course, from_attributes=True)


def schema_to_course(schema: CourseSchema) -> Course:
    course = Course(
        id=schema.id,
        name=schema.name,
        instructor=schema.instructor,
        evaluation_type=schema.evaluation_type,
    )
    for offering in schema.offerings:
        course.add_offering(CourseOffering(
            program_id=offering.program_id,
            year=offering.year,
            semester=offering.semester,
            requirement=offering.requirement,
        ))
    return course
```

---

## REST API Endpoint Design

### Base URL: `/api`

All endpoints accept/return JSON. Session is identified by `X-Session-ID` header (UUID). If absent, a new session is created and the ID returned in the response header.

| Method | Path | Description | Owner |
|--------|------|-------------|-------|
| GET | `/health` | Health check (always 200) | Alon |
| POST | `/api/upload/courses` | Upload courses file | Ron |
| POST | `/api/upload/dates` | Upload dates file | Ron |
| GET | `/api/programs` | List available programs | Ron |
| POST | `/api/programs/select` | Select programs (max 5) | Ron |
| GET | `/api/programs/courses` | Get courses for selected programs | Ron |
| GET | `/api/periods` | Get all exam periods | Ron |
| PATCH | `/api/periods/{index}` | Update exam period dates/exclusions | Ron |
| POST | `/api/generate` | Trigger schedule generation | Ron |
| GET | `/api/generate/status` | Poll generation status | Ron |
| GET | `/api/schedules/{index}` | Get schedule by index | Ron |
| GET | `/api/schedules/count` | Get total schedule count | Ron |
| POST | `/api/schedules/save` | Save schedule to file | Ron |

### Endpoint Details

#### POST /api/upload/courses

**Request**: `multipart/form-data` with field `file` (the courses text file) and query param `mode=replace|append`

**Response 200**:
```json
{"count": 42, "session_id": "uuid-here"}
```

**Response 422**: Parse error with line/field identification.

**Logic**:
1. Save uploaded file to a temp path
2. Instantiate `CourseFileReader(temp_path)` and call `.read()`
3. If mode is "replace", set `session.courses = parsed_courses`
4. If mode is "append", extend `session.courses += parsed_courses`
5. Return count of newly parsed courses

#### POST /api/upload/dates

**Request**: `multipart/form-data` with field `file` and query param `mode=replace|append`

**Response 200**:
```json
{"count": 6, "session_id": "uuid-here"}
```

**Response 422**: Parse error.

**Logic**: Same pattern as courses upload using `ExamPeriodFileReader`.

#### GET /api/programs

**Response 200**:
```json
{"programs": [{"id": "83101", "name": "Computer Science"}, ...]}
```

**Logic**: Extract distinct `program_id` values from all `CourseOffering` objects in session courses. Program name is derived from the program ID (lookup or label from data).

#### POST /api/programs/select

**Request**:
```json
{"program_ids": ["83101", "83102"]}
```

**Response 200**:
```json
{"selected": ["83101", "83102"]}
```

**Response 422**: If any ID not found in loaded courses, or if count > 5.

**Logic**:
1. Validate len(program_ids) <= 5
2. Validate each ID exists in session courses offerings
3. Store in `session.selected_programs`

#### GET /api/programs/courses

**Response 200**:
```json
{
  "programs": {
    "83101": {
      "years": {
        "1": {
          "FALL": [{"id": "12345", "name": "Intro CS", "obligation": "Obligatory", "evaluation": "Exam"}],
          "SPRI": [...]
        }
      }
    }
  }
}
```

**Logic**: For each selected program, filter courses that have an offering for that program, group by year and semester.

#### GET /api/periods

**Response 200**: List of `ExamPeriodSchema` objects.

#### PATCH /api/periods/{index}

**Request**:
```json
{"action": "toggle_exclusion", "date": "2025-02-15"}
```
or:
```json
{"action": "update_range", "range_index": 0, "start": "2025-02-01", "end": "2025-02-28"}
```

**Response 200**: Updated `ExamPeriodSchema`.

**Response 422**: Invalid date range (start > end).

#### POST /api/generate

**Request**: Empty body (uses session state).

**Response 202** (Accepted):
```json
{"status": "running"}
```

**Response 422**: Preconditions not met (lists which are missing).

**Logic**:
1. Validate preconditions: courses loaded, periods loaded, programs selected
2. Set `session.generation_status = "running"`
3. Launch `asyncio.to_thread(self._run_generation, session)` as background task
4. Return 202 immediately

**Background task** (`_run_generation`):
```python
async def _run_generation(session: SessionState) -> None:
    try:
        data_provider = APIDataProvider(
            courses=session.courses,
            exam_periods=session.exam_periods,
            selected_programs=session.selected_programs,
        )
        exporter = InMemoryExporter()
        generator = ScheduleGenerator(ExactConflictStrategy())
        controller = AppController(
            data_provider=data_provider,
            exporter=exporter,
            generator=generator,
            selected_programs=session.selected_programs,
        )
        await asyncio.to_thread(controller.run)
        session.schedules_by_period = exporter.schedules_by_period
        session.courses_by_id = exporter.courses_by_id
        session.generation_status = "completed"
    except Exception as e:
        session.generation_status = "failed"
        session.generation_error = str(e)
```

#### GET /api/generate/status

**Response 200**:
```json
{"status": "running" | "completed" | "failed" | "idle", "total_schedules": 120, "error": null}
```

**Performance**: Must respond within 200ms even during generation (guaranteed because generation runs in a thread, not on the event loop).

#### GET /api/schedules/{index}

**Response 200**: `ScheduleDetailSchema` for the schedule at the given cross-product index.

**Response 404**: Index out of range.

**Logic**: The total schedule count is the Cartesian product of per-period schedule lists. Index `i` maps to a specific combination using modular arithmetic across period lists.

#### GET /api/schedules/count

**Response 200**:
```json
{"total": 120, "per_period": {"FALL - Aleph": 10, "SPRI - Aleph": 12}}
```

#### POST /api/schedules/save

**Request**:
```json
{"index": 5}
```

**Response 200**:
```json
{"file_path": "/absolute/path/to/output/schedule_5.txt"}
```

**Response 500**: File write error.

**Logic**:
1. Resolve the schedule combination at the given index
2. Construct a single-combination `schedules_by_period` dict
3. Instantiate `TextFileExporter(output_path)` and call `.export_schedules()`
4. Return the absolute file path

---

## Frontend Component Architecture

### Technology Stack

- **React 18** with TypeScript
- **React Router** for Input/Output screen navigation
- **Axios** for HTTP client
- **Vite** as build tool
- CSS Modules or Tailwind CSS for styling

### Component Tree

```
App
 +-- Router
      +-- InputScreen
      |    +-- Sidebar
      |    |    +-- FileUploader (courses)
      |    |    +-- FileUploader (dates)
      |    |    +-- ProgramSelector (dropdown, max 5)
      |    |    +-- ProgramDrillDown (courses by year/semester)
      |    |    +-- RunButton (disabled until preconditions met)
      |    +-- MainPanel
      |         +-- ExamPeriodCalendar (interactive date toggling)
      |         +-- StatusSummary (courses count, periods count, programs count)
      +-- OutputScreen
           +-- ScheduleNavigation (Prev/Next, counter label, Save)
           +-- ScheduleCalendar
                +-- PeriodSection (one per semester+moed)
                     +-- WeekRow
                          +-- DayCell
                               +-- ExamSlot (course info, color-coded by program)
```

### Input Screen Behavior

1. **FileUploader**: Accepts file via drag-and-drop or file picker. Sends to `POST /api/upload/courses` or `POST /api/upload/dates`. Displays success count or error message.
2. **ProgramSelector**: Populated after courses are loaded (calls `GET /api/programs`). Multi-select dropdown limited to 5. On change, calls `POST /api/programs/select`.
3. **ProgramDrillDown**: After programs are selected, fetches `GET /api/programs/courses` and renders a collapsible tree: Program > Year > Semester > Course list. Obligatory courses shown in bold.
4. **ExamPeriodCalendar**: Renders after dates are loaded. Each date cell is clickable to toggle exclusion (calls `PATCH /api/periods/{index}`). Excluded dates shown with strikethrough/grey. Date range boundaries are editable.
5. **StatusSummary**: Reactively shows counts from session state.
6. **RunButton**: Enabled only when courses > 0, periods > 0, programs > 0. On click, calls `POST /api/generate`, then polls `GET /api/generate/status` every 500ms. On completion, navigates to Output Screen.

### Output Screen Behavior

1. **ScheduleNavigation**: Shows "Schedule X of Y". Previous disabled at index 0, Next disabled at last index. Save button triggers `POST /api/schedules/save`.
2. **ScheduleCalendar**: Fetches `GET /api/schedules/{index}` on mount and on navigation. Renders a year-calendar grid grouped by period (semester + moed), ordered FALL > SPRI > SUMM, Aleph > Bet > Gimel.
3. **ExamSlot**: Renders course number, name, affected program IDs, obligation type, instructor. Color-coded by program (WCAG AA compliant colors).

---

## Non-Blocking Async Execution Strategy

`AppController.run()` is a synchronous, CPU-bound method (backtracking search). To keep the FastAPI event loop responsive:

```python
# In the generate router
import asyncio
from fastapi import BackgroundTasks

async def run_generation_background(session: SessionState):
    """Runs in a background task, off the event loop."""
    try:
        session.generation_status = "running"
        data_provider = APIDataProvider(
            courses=session.courses,
            exam_periods=session.exam_periods,
            selected_programs=session.selected_programs,
        )
        exporter = InMemoryExporter()
        generator = ScheduleGenerator(ExactConflictStrategy())
        controller = AppController(
            data_provider=data_provider,
            exporter=exporter,
            generator=generator,
            selected_programs=session.selected_programs,
        )
        # Run CPU-bound work in a thread pool
        await asyncio.to_thread(controller.run)
        # Store results back in session
        session.schedules_by_period = exporter.schedules_by_period
        session.courses_by_id = exporter.courses_by_id
        session.generation_status = "completed"
        session.generation_error = None
    except Exception as e:
        session.generation_status = "failed"
        session.generation_error = str(e)
        session.schedules_by_period = None
        session.courses_by_id = None
```

**Guarantees**:
- The event loop is never blocked by `controller.run()`
- `GET /api/generate/status` reads `session.generation_status` directly (no lock needed for single-writer pattern)
- All other endpoints remain responsive within 200ms during generation
- If generation fails, no partial results are stored

---

## Data Flow Diagrams

### Flow 1: File Upload (Courses)

```
User -> Frontend (FileUploader): selects courses file
Frontend -> Backend: POST /api/upload/courses?mode=replace
    Backend: saves file to temp path
    Backend: CourseFileReader(temp_path).read() -> List[Course]
    Backend: session.courses = parsed_courses
    Backend: cleanup temp file
Backend -> Frontend: {count: 42, session_id: "..."}
Frontend: updates StatusSummary, enables ProgramSelector
```

### Flow 2: Program Selection

```
User -> Frontend (ProgramSelector): selects programs
Frontend -> Backend: POST /api/programs/select {program_ids: [...]}
    Backend: validates IDs exist in session.courses
    Backend: validates len <= 5
    Backend: session.selected_programs = program_ids
Backend -> Frontend: {selected: [...]}
Frontend -> Backend: GET /api/programs/courses
    Backend: filters and groups courses by program/year/semester
Backend -> Frontend: grouped course data
Frontend: renders ProgramDrillDown
```

### Flow 3: Schedule Generation

```
User -> Frontend (RunButton): clicks Run
Frontend -> Backend: POST /api/generate
    Backend: validates preconditions
    Backend: sets session.generation_status = "running"
    Backend: launches asyncio.to_thread(controller.run) as background task
Backend -> Frontend: 202 {status: "running"}
Frontend: starts polling GET /api/generate/status every 500ms
    Backend (background): AppController.run() executes
    Backend (background): InMemoryExporter captures results
    Backend (background): session.generation_status = "completed"
Frontend: receives {status: "completed", total_schedules: 120}
Frontend: navigates to OutputScreen
```

### Flow 4: Schedule Browsing

```
User -> Frontend (OutputScreen): page loads
Frontend -> Backend: GET /api/schedules/count
Backend -> Frontend: {total: 120}
Frontend -> Backend: GET /api/schedules/0
Backend -> Frontend: ScheduleDetailSchema (full schedule with course details)
Frontend: renders ScheduleCalendar with ExamSlots

User -> Frontend (Next button): clicks Next
Frontend -> Backend: GET /api/schedules/1
Backend -> Frontend: ScheduleDetailSchema
Frontend: re-renders calendar
```

### Flow 5: Save Schedule

```
User -> Frontend (Save button): clicks Save
Frontend -> Backend: POST /api/schedules/save {index: 5}
    Backend: resolves schedule combination at index 5
    Backend: TextFileExporter(output_path).export_schedules(...)
Backend -> Frontend: {file_path: "/path/to/output/schedule_5.txt"}
Frontend: displays success message with file path
```

---

## Error Handling Strategy

| Scenario | HTTP Status | Response Body |
|----------|-------------|---------------|
| File parse error | 422 | `{"detail": "Line 5: missing instructor field"}` |
| Program ID not found | 422 | `{"detail": "Program ID 99999 not found in loaded courses"}` |
| Too many programs (>5) | 422 | `{"detail": "Maximum 5 programs allowed, got 7"}` |
| Invalid date range (start > end) | 422 | `{"detail": "Start date 2025-03-01 is after end date 2025-02-28"}` |
| Generation preconditions unmet | 422 | `{"detail": "Missing: courses, selected programs"}` |
| Generation exception | 500 | `{"detail": "Duplicate exam period found: FALL - Aleph"}` |
| File write failure | 500 | `{"detail": "Permission denied: /output/schedule.txt"}` |
| Schedule index out of range | 404 | `{"detail": "Schedule index 999 out of range (0-119)"}` |
| Session not found | 404 | `{"detail": "Session not found"}` |

---

## FastAPI Application Setup

```python
# src/presentation/app.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.presentation.session_store import SessionStore
from src.presentation.routers import upload, programs, periods, generate, schedules, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize session store
    app.state.session_store = SessionStore()
    yield
    # Shutdown: cleanup


def create_app() -> FastAPI:
    app = FastAPI(
        title="examSchedule v2.0",
        version="2.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],  # Vite dev server
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(upload.router, prefix="/api")
    app.include_router(programs.router, prefix="/api")
    app.include_router(periods.router, prefix="/api")
    app.include_router(generate.router, prefix="/api")
    app.include_router(schedules.router, prefix="/api")
    return app
```

---

## TypeScript API Types (Frontend)

```typescript
// frontend/src/api/types.ts

export interface CourseOffering {
  program_id: string;
  year: number;
  semester: string;
  requirement: string;
}

export interface Course {
  id: string;
  name: string;
  instructor: string;
  evaluation_type: string;
  offerings: CourseOffering[];
}

export interface ExamPeriod {
  semester: string;
  moed: string;
  date_ranges: [string, string][];  // ISO date pairs
  excluded_dates: string[];          // ISO dates
}

export interface Schedule {
  period: ExamPeriod;
  assignments: Record<string, string>;  // course_id -> ISO date
}

export interface ExamAssignmentDetail {
  course: Course;
  assigned_date: string;
  affected_program_ids: string[];
  obligation_type: string;
}

export interface ScheduleDetail {
  period: ExamPeriod;
  assignments: Record<string, string>;
  details: ExamAssignmentDetail[];
}

export interface GenerationStatus {
  status: "idle" | "running" | "completed" | "failed";
  total_schedules?: number;
  error?: string;
}

export interface UploadResponse {
  count: number;
  session_id: string;
}

export interface ProgramInfo {
  id: string;
  name: string;
}
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system - essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Pydantic Schema Round-Trip

*For any* valid domain object (Course, CourseOffering, ExamPeriod, or Schedule), converting it to its corresponding Pydantic schema and then converting back to a domain object SHALL produce an object with field values identical to the original.

**Validates: Requirements 10.6, 10.7**

### Property 2: APIDataProvider Returns Session State Faithfully

*For any* set of courses, exam periods, and selected programs stored in an APIDataProvider instance, calling `get_courses()`, `get_exam_periods()`, and `get_selected_programs()` SHALL return exactly those objects without modification.

**Validates: Requirements 1.2**

### Property 3: InMemoryExporter Captures All Schedules

*For any* `schedules_by_period` dict and `courses_by_id` dict passed to `InMemoryExporter.export_schedules()`, the exporter's stored `schedules_by_period` and `courses_by_id` attributes SHALL be equal to the inputs.

**Validates: Requirements 1.3**

### Property 4: File Upload Round-Trip (Replace Mode)

*For any* valid courses file content, uploading it in "replace" mode SHALL result in session state containing exactly the courses parsed by `CourseFileReader`, with the response count equal to the number of parsed courses.

**Validates: Requirements 2.1, 2.3, 2.6**

### Property 5: File Upload Append Preserves Existing Data

*For any* initial session state containing N courses and any valid courses file producing M new courses, uploading in "append" mode SHALL result in session state containing N + M courses (all original courses preserved, all new courses added).

**Validates: Requirements 2.4**

### Property 6: Malformed File Upload Returns 422

*For any* file content that causes `CourseFileReader.read()` or `ExamPeriodFileReader.read()` to raise a `ValueError`, the upload endpoint SHALL return HTTP 422 with an error message containing the exception detail.

**Validates: Requirements 2.5**

### Property 7: Program List Derivation

*For any* set of courses loaded in session state, the `GET /api/programs` endpoint SHALL return exactly the distinct set of `program_id` values found across all `CourseOffering` objects in those courses.

**Validates: Requirements 3.1**

### Property 8: Program Selection Validation

*For any* list of program IDs submitted to `POST /api/programs/select`, the endpoint SHALL accept the request if and only if all IDs exist in the loaded courses' offerings AND the list length is at most 5. Otherwise it SHALL return HTTP 422 identifying the specific violation.

**Validates: Requirements 3.2, 3.3, 3.4**

### Property 9: Program Courses Grouping Correctness

*For any* valid program selection and loaded courses, the `GET /api/programs/courses` endpoint SHALL return, for each selected program, exactly those courses that have a `CourseOffering` with that program's ID, grouped by year and semester with correct obligation type.

**Validates: Requirements 3.5**

### Property 10: Date Exclusion Toggle is Symmetric

*For any* exam period and any valid date within its date ranges, toggling the exclusion status twice SHALL return the exam period to its original state (the date is back in/out of `excluded_dates` as it was before).

**Validates: Requirements 4.2**

### Property 11: Date Range Validation

*For any* pair of dates (start, end), the `PATCH /api/periods/{index}` endpoint SHALL accept the update if and only if start <= end. When start > end, it SHALL return HTTP 422.

**Validates: Requirements 4.3, 4.4, 4.5**

### Property 12: Generation Precondition Enforcement

*For any* session state, the `POST /api/generate` endpoint SHALL return HTTP 422 listing all unmet preconditions if any of the following are empty: courses, exam_periods, or selected_programs. It SHALL proceed only when all three are non-empty.

**Validates: Requirements 5.1, 5.2**

### Property 13: Generation Failure Leaves No Partial State

*For any* input that causes `AppController.run()` to raise an exception, the session state SHALL have `generation_status = "failed"`, `schedules_by_period = None`, and `courses_by_id = None` (no partial results stored).

**Validates: Requirements 5.5**

### Property 14: Schedule Index Retrieval

*For any* valid schedule index within the range [0, total_schedules), the `GET /api/schedules/{index}` endpoint SHALL return a `ScheduleDetailSchema` containing the correct schedule combination with all course details (name, instructor, program IDs, obligation type) populated.

**Validates: Requirements 6.2**

### Property 15: Calendar Cell Placement Correctness

*For any* schedule and any exam assignment within it, the frontend SHALL render that assignment in the calendar cell whose date matches the assignment's `assigned_date` field.

**Validates: Requirements 6.7, 9.4**

### Property 16: Navigation Button State

*For any* schedule index and total count, the "Previous" button SHALL be disabled if and only if index equals 0, and the "Next" button SHALL be disabled if and only if index equals total - 1.

**Validates: Requirements 6.5, 6.6**

### Property 17: Run Button Precondition Gate

*For any* combination of session state (courses loaded or not, periods loaded or not, programs selected or not), the "Run" button SHALL be enabled if and only if all three conditions are satisfied (courses count > 0 AND periods count > 0 AND selected programs count > 0).

**Validates: Requirements 8.7**

### Property 18: Period Sort Order

*For any* set of exam periods, the Output Screen calendar sections SHALL be ordered by semester (FALL < SPRI < SUMM) and within each semester by moed (Aleph < Bet < Gimel), matching `AppController._sort_exam_periods` ordering.

**Validates: Requirements 9.3**

### Property 19: Status Summary Accuracy

*For any* session state, the status summary SHALL display counts that exactly match `len(session.courses)`, `len(session.exam_periods)`, and `len(session.selected_programs)`.

**Validates: Requirements 8.6**

---

## Testing Strategy

### Unit Tests (Property-Based)

| Property | Test Target | Generator Strategy |
|----------|-------------|-------------------|
| 1 (Schema Round-Trip) | `src/schemas/` | Generate random Course/ExamPeriod/Schedule domain objects |
| 2 (APIDataProvider) | `api_data_provider.py` | Generate random lists of courses/periods/programs |
| 3 (InMemoryExporter) | `in_memory_exporter.py` | Generate random schedules_by_period dicts |
| 4 (Upload Replace) | Upload router | Generate valid course file content strings |
| 5 (Upload Append) | Upload router | Generate initial state + new file content |
| 6 (Malformed Upload) | Upload router | Generate invalid file content (missing fields, bad format) |
| 7 (Program List) | Programs router | Generate courses with various offerings |
| 8 (Program Validation) | Programs router | Generate program ID lists (valid/invalid/oversized) |
| 10 (Exclusion Toggle) | Periods router | Generate exam periods + random dates |
| 11 (Date Range) | Periods router | Generate date pairs (valid and invalid) |
| 12 (Preconditions) | Generate router | Generate session states with various missing data |
| 16 (Nav Buttons) | ScheduleNavigation component | Generate index/total pairs |
| 17 (Run Button) | InputScreen component | Generate boolean triples (loaded/not) |
| 18 (Period Sort) | ScheduleCalendar component | Generate unordered period lists |

### Integration Tests (Guy)

- Full pipeline: upload files -> select programs -> generate -> browse -> save
- Concurrent requests during generation (verify 200ms responsiveness)
- Session isolation (two sessions do not interfere)
- Health endpoint always returns 200
- Startup time < 5 seconds

### Frontend E2E Tests (Guy + Niv)

- Input Screen: file upload success/error, program selection, calendar interaction
- Output Screen: navigation, schedule rendering, save action
- UI reactivity: all non-generation actions complete within 1 second
- WCAG AA color contrast for multi-program exam slots

### Regression

- All 84 existing pytest tests must pass unchanged (CI gate)
- No modifications to files under `src/domain/`, `src/interfaces/`, `src/engine/`, or existing `src/adapters/` files

---

## Dependency Injection via FastAPI

```python
# src/presentation/dependencies.py
from fastapi import Request, Header, HTTPException
from typing import Optional

from src.presentation.session_store import SessionState, SessionStore


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store


def get_session(
    request: Request,
    x_session_id: Optional[str] = Header(None),
) -> SessionState:
    store: SessionStore = request.app.state.session_store
    if x_session_id:
        session = store.get(x_session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    return store.get_or_create()
```

---

## Performance Constraints Summary

| Constraint | Mechanism |
|------------|----------|
| 1s UI reactivity (non-generation) | Frontend optimistic updates + backend responds quickly for all CRUD endpoints |
| 200ms backend responsiveness during generation | asyncio.to_thread() keeps event loop free; generation runs in thread pool |
| Health endpoint always 200 | Stateless handler, no dependencies on session state |
| Startup under 5 seconds | FastAPI cold start is typically under 1 second; no heavy initialization |

---

## Deployment Notes

- **Backend**: uvicorn src.presentation.app:create_app --factory
- **Frontend**: Vite dev server during development
- **Production**: Frontend built to static files, served by FastAPI or a reverse proxy
- **Session persistence**: In-memory only (single-process). For multi-process deployment, replace SessionStore with Redis-backed store (future enhancement).
