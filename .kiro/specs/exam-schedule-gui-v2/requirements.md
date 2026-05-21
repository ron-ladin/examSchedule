# Requirements Document

## Introduction

examSchedule v2.0 replaces the CLI composition root with a web-based GUI consisting of a
FastAPI backend and a React/Vue frontend. The existing five-layer Clean Architecture
(Domain → Interfaces → Adapters → Engine → CLI) is preserved without modification to any
existing source file. FastAPI becomes the new outermost composition root, exposing async
REST endpoints that the frontend consumes. The system must deliver two interactive screens —
an Input Screen for data loading and configuration, and an Output Screen for browsing and
saving generated schedules — while keeping all 84 existing pytest tests green and maintaining
a 1-second UI reactivity constraint throughout.

---

## Glossary

- **System**: The examSchedule v2.0 web application (FastAPI backend + React/Vue frontend).
- **Backend**: The FastAPI application that acts as the composition root and exposes REST API endpoints.
- **Frontend**: The React or Vue single-page application that renders the Input Screen and Output Screen.
- **Input Screen**: The frontend view where the user loads data files, selects study programs, and configures exam period dates.
- **Output Screen**: The frontend view where the user browses generated schedules in calendar format and saves a preferred schedule.
- **AppController**: The existing engine-layer orchestrator (`src/engine/app_controller.py`) that runs the scheduling pipeline.
- **IDataProvider**: The existing interface (`src/interfaces/i_data_provider.py`) that the Backend implements via a new adapter.
- **IOutputExporter**: The existing interface (`src/interfaces/i_output_exporter.py`) that the Backend implements via an in-memory adapter.
- **Course**: The existing domain entity (`src/domain/course.py`) representing a university course.
- **CourseOffering**: The existing domain entity (`src/domain/course_offering.py`) representing a program's enrollment in a course.
- **ExamPeriod**: The existing domain entity (`src/domain/exam_period.py`) representing an exam window for a semester and moed.
- **Schedule**: The existing domain entity (`src/domain/schedule.py`) mapping course IDs to assigned exam dates.
- **Study Program**: A 5-digit program identifier (e.g., "83101") present in the courses data file.
- **Moed**: An exam sitting within a semester — one of "Aleph", "Bet", or "Gimel".
- **Pydantic Schema**: A Pydantic `BaseModel` class used to serialize and deserialize domain objects for the REST API.
- **InMemoryExporter**: A new `IOutputExporter` adapter that stores generated schedules in memory instead of writing to a file.
- **APIDataProvider**: A new `IDataProvider` adapter that reads courses and exam periods from server-side session state rather than directly from files.
- **Session State**: Server-side storage (per-request or in-memory) holding the currently loaded courses, exam periods, and selected programs for a user session.
- **Calendar View**: A year-calendar grid rendered by the Frontend, with rows representing weeks and columns representing weekdays.
- **Obligation Type**: Whether a course is "Obligatory" or "Elective" for a given program, derived from `CourseOffering.requirement`.

---

## Requirements

### Requirement 1 — FastAPI Backend as Composition Root

**User Story:** As the development team, we want FastAPI to replace the CLI as the composition root, so that the existing Clean Architecture layers remain untouched while a web API drives the scheduling pipeline.

#### Acceptance Criteria

1. THE Backend SHALL expose all scheduling functionality exclusively through async HTTP endpoints, with no modification to any file under `src/domain/`, `src/interfaces/`, `src/engine/`, or `src/adapters/` (existing files).
2. THE Backend SHALL implement `IDataProvider` through a new `APIDataProvider` adapter that reads courses and exam periods from Session State.
3. THE Backend SHALL implement `IOutputExporter` through a new `InMemoryExporter` adapter that stores generated schedules in memory and returns them to the calling endpoint.
4. WHEN the Backend constructs an `AppController` instance, THE Backend SHALL inject `APIDataProvider`, `InMemoryExporter`, `ExactConflictStrategy`, and `ScheduleGenerator` as dependencies, with no changes to `AppController.__init__`.
5. THE Backend SHALL expose a Pydantic schema for every domain entity exchanged over the API (`Course`, `CourseOffering`, `ExamPeriod`, `Schedule`), authored by Lotem as isolated, non-blocking work.
6. WHILE the existing 84 pytest tests are executed, THE Backend SHALL not introduce any import or dependency that causes a test failure.

---

### Requirement 2 — Data File Loading

**User Story:** As a user, I want to load courses and exam-period date files into the system, so that the scheduling engine has the data it needs to generate schedules.

#### Acceptance Criteria

1. WHEN the user submits a courses file via the Input Screen, THE Backend SHALL parse the file using the existing `CourseFileReader` and store the resulting `list[Course]` in Session State within 1 second of receiving the request.
2. WHEN the user submits a dates file via the Input Screen, THE Backend SHALL parse the file using the existing `ExamPeriodFileReader` and store the resulting `list[ExamPeriod]` in Session State within 1 second of receiving the request.
3. WHEN the user selects "Replace" load mode, THE Backend SHALL discard all previously stored courses or exam periods (respectively) before storing the newly parsed data.
4. WHEN the user selects "Append" load mode, THE Backend SHALL merge the newly parsed data with the existing Session State data, preserving all previously stored records.
5. IF a submitted file cannot be parsed (malformed format, missing required fields), THEN THE Backend SHALL return an HTTP 422 response containing a human-readable error message that identifies the offending line or field.
6. WHEN a file is successfully loaded, THE Backend SHALL return the count of loaded courses or exam periods in the response body so the Frontend can update the status display.

---

### Requirement 3 — Study Program Selection

**User Story:** As a user, I want to select up to 5 study programs from a dropdown populated from the loaded data, so that the schedule is generated only for the programs I care about.

#### Acceptance Criteria

1. WHEN courses have been loaded into Session State, THE Backend SHALL provide an endpoint that returns the list of distinct 5-digit program IDs and their associated program names derived from `CourseOffering.program_id` values in the loaded courses.
2. WHEN the user submits a program selection, THE Backend SHALL validate that each submitted program ID exists in the currently loaded courses data.
3. WHEN the user submits a program selection containing more than 5 program IDs, THE Backend SHALL return an HTTP 422 response indicating that the maximum selection limit is 5 programs.
4. IF a submitted program ID does not exist in the loaded courses data, THEN THE Backend SHALL return an HTTP 422 response identifying the unrecognised program ID.
5. WHEN a valid program selection is stored in Session State, THE Backend SHALL provide an endpoint that returns, for each selected program, the list of courses grouped by year and semester, including each course's name, ID, obligation type, and evaluation method.

---

### Requirement 4 — Exam Period Date Configuration

**User Story:** As a user, I want to view and edit the exam period dates on the Input Screen, so that I can exclude specific days or adjust the period boundaries before generating schedules.

#### Acceptance Criteria

1. WHEN exam periods have been loaded into Session State, THE Backend SHALL provide an endpoint that returns all `ExamPeriod` objects serialized as Pydantic schemas, including their date ranges and excluded dates.
2. WHEN the user toggles a date's exclusion status, THE Backend SHALL update the corresponding `ExamPeriod.excluded_dates` set in Session State and return the updated `ExamPeriod` in the response.
3. WHEN the user submits a new start or end date for an exam period, THE Backend SHALL validate that the new start date is not later than the new end date.
4. IF the user submits a new start date that is later than the current end date, THEN THE Backend SHALL return an HTTP 422 response indicating the invalid date range.
5. WHEN a valid date range update is submitted, THE Backend SHALL replace the corresponding `ExamPeriod.date_ranges` entry in Session State and return the updated `ExamPeriod`.

---

### Requirement 5 — Schedule Generation

**User Story:** As a user, I want to trigger schedule generation from the Input Screen, so that the engine produces all valid conflict-free exam schedules for my selected programs and configured periods.

#### Acceptance Criteria

1. WHEN the user triggers schedule generation, THE Backend SHALL validate that at least one study program is selected, at least one course is loaded, and at least one exam period is loaded before invoking `AppController.run()`.
2. IF any of the preconditions in criterion 1 are not met, THEN THE Backend SHALL return an HTTP 422 response listing the unmet preconditions.
3. WHEN `AppController.run()` is invoked, THE Backend SHALL execute it in a non-blocking async context so that the HTTP server remains responsive to other requests during computation.
4. WHEN schedule generation completes successfully, THE Backend SHALL store the resulting `schedules_by_period` and `courses_by_id` in Session State and return the total count of generated schedules across all periods.
5. IF `AppController.run()` raises an exception, THEN THE Backend SHALL return an HTTP 500 response containing the exception message and SHALL NOT store partial results in Session State.
6. WHILE schedule generation is in progress, THE Backend SHALL respond to a status-polling endpoint with a "running" status within 200 milliseconds.

---

### Requirement 6 — Output Screen: Schedule Browsing

**User Story:** As a user, I want to browse generated schedules one at a time in a year-calendar format on the Output Screen, so that I can evaluate each schedule visually.

#### Acceptance Criteria

1. WHEN the user navigates to the Output Screen after a successful generation run, THE Frontend SHALL display the first schedule (index 0) in calendar format without requiring an additional user action.
2. THE Backend SHALL provide an endpoint that accepts a schedule index and returns the corresponding `Schedule` serialized as a Pydantic schema, including all exam assignments with course ID, course name, affected program IDs, obligation type, and instructor name.
3. WHEN the user requests the next or previous schedule, THE Frontend SHALL fetch and render the new schedule within 1 second of the navigation action.
4. THE Frontend SHALL display a counter label showing the current schedule index (1-based) and the total schedule count in the format "Schedule X of Y".
5. WHEN the current schedule index is 0, THE Frontend SHALL disable the "Previous" navigation control.
6. WHEN the current schedule index equals the total schedule count minus 1, THE Frontend SHALL disable the "Next" navigation control.
7. THE Frontend SHALL render each exam assignment in the calendar cell corresponding to its assigned date, showing course number, course name, affected program IDs, obligation type, and instructor name.

---

### Requirement 7 — Output Screen: Save Schedule

**User Story:** As a user, I want to save my preferred schedule to a human-readable file, so that I can share or archive the result.

#### Acceptance Criteria

1. WHEN the user clicks the save action on the Output Screen, THE Frontend SHALL send the current schedule index to the Backend save endpoint.
2. WHEN the Backend receives a save request with a valid schedule index, THE Backend SHALL invoke the existing `TextFileExporter` with the single selected `Schedule` and write the output to the server's `output/` directory.
3. WHEN the file is written successfully, THE Backend SHALL return the absolute file path of the saved file in the response body.
4. IF the Backend cannot write the output file (permission error, disk full), THEN THE Backend SHALL return an HTTP 500 response with a descriptive error message.
5. THE saved file SHALL conform to the existing `TextFileExporter` output format so that the file is human-readable and consistent with v1.0 output.

---

### Requirement 8 — Frontend Input Screen Layout

**User Story:** As a user, I want the Input Screen to present file loading, program selection, and calendar configuration in a clear, organised layout, so that I can configure a run without confusion.

#### Acceptance Criteria

1. THE Frontend SHALL render the Input Screen with a sidebar panel containing file-loading controls and a program selector, and a main panel containing the exam period calendar and a status summary.
2. THE Frontend SHALL populate the program selection dropdown from the list of program IDs returned by the Backend after courses are loaded, without requiring a page reload.
3. THE Frontend SHALL display, for each selected program, a drill-down view listing the program's courses grouped by year and semester, with obligatory courses visually distinguished from elective courses.
4. THE Frontend SHALL render the exam period calendar highlighting excluded dates distinctly from valid exam dates and from dates outside the exam window.
5. WHEN the user modifies an exam period date or exclusion on the calendar, THE Frontend SHALL send the update to the Backend and re-render the calendar to reflect the confirmed state within 1 second.
6. THE Frontend SHALL display a status summary showing the count of loaded courses, the count of loaded exam periods, and the count of selected programs, updating the summary reactively after each data-loading or selection action.
7. THE Frontend SHALL disable the "Run" button until at least one program is selected, at least one course file has been loaded, and at least one dates file has been loaded.

---

### Requirement 9 — Frontend Output Screen Layout

**User Story:** As a user, I want the Output Screen to present schedules in a year-calendar grid with navigation controls, so that I can compare schedules efficiently.

#### Acceptance Criteria

1. THE Frontend SHALL render the Output Screen with a navigation toolbar containing "Previous" and "Next" controls, a schedule counter label, and a "Save" action.
2. THE Frontend SHALL render each schedule as a year-calendar grid where rows represent weeks and columns represent weekdays (Sunday through Friday), with exam assignments placed in the cell matching their assigned date.
3. THE Frontend SHALL group calendar sections by semester and moed, ordered by the same sort order used by `AppController._sort_exam_periods` (FALL before SPRI before SUMM; Aleph before Bet before Gimel).
4. THE Frontend SHALL render each exam slot within a calendar cell showing the course number, course name, the affected program IDs, the obligation type indicator, and the instructor name.
5. WHERE more than one study program is selected, THE Frontend SHALL apply a distinct colour per program to exam slots, using colours that meet WCAG AA contrast requirements against the cell background.

---

### Requirement 10 — Pydantic Serialization Schemas (Lotem's Task)

**User Story:** As the Backend developer, I want Pydantic schemas for all domain entities, so that FastAPI can automatically serialize and deserialize domain objects in API request and response bodies.

#### Acceptance Criteria

1. THE System SHALL provide a `CourseSchema` Pydantic `BaseModel` with fields matching `Course`: `id` (str), `name` (str), `instructor` (str), `evaluation_type` (str), and `offerings` (list of `CourseOfferingSchema`).
2. THE System SHALL provide a `CourseOfferingSchema` Pydantic `BaseModel` with fields matching `CourseOffering`: `program_id` (str), `year` (int), `semester` (str), and `requirement` (str).
3. THE System SHALL provide an `ExamPeriodSchema` Pydantic `BaseModel` with fields matching `ExamPeriod`: `semester` (str), `moed` (str), `date_ranges` (list of two-element date tuples), and `excluded_dates` (set of dates).
4. THE System SHALL provide a `ScheduleSchema` Pydantic `BaseModel` with fields matching `Schedule`: `period` (`ExamPeriodSchema`) and `assignments` (dict mapping course ID strings to date strings in ISO 8601 format).
5. THE System SHALL provide a `ScheduleDetailSchema` Pydantic `BaseModel` that extends `ScheduleSchema` by embedding, for each assignment, the full `CourseSchema` of the assigned course alongside the assigned date.
6. WHEN a domain object is converted to its corresponding Pydantic schema, THE System SHALL produce a JSON-serializable representation with no loss of data required by the Frontend.
7. WHEN a Pydantic schema is converted back to a domain object, THE System SHALL reconstruct the domain object with field values identical to the original.
8. THE System SHALL implement all Pydantic schemas in a dedicated module (`src/schemas/`) with no imports from `src/presentation/` or any web-framework-specific module, so that the schemas remain usable independently of FastAPI.

---

### Requirement 11 — Non-Functional: Performance and Reliability

**User Story:** As a user, I want the application to remain responsive at all times, so that I am never blocked waiting for the UI to react to my actions.

#### Acceptance Criteria

1. WHEN the user performs any UI action (button click, navigation, calendar toggle) that does not trigger schedule generation, THE Frontend SHALL update the UI state within 1 second of the action.
2. WHEN schedule generation is running, THE Backend SHALL continue to respond to all non-generation endpoints within 200 milliseconds.
3. THE Backend SHALL run `AppController.run()` in a non-blocking async context (e.g., `asyncio.to_thread` or a background task) so that the event loop is not blocked during computation.
4. WHEN the Backend is started, THE Backend SHALL be reachable at its configured host and port within 5 seconds of process startup.
5. THE Backend SHALL return HTTP 200 from a `/health` endpoint at all times when the process is running and the application is initialised.
