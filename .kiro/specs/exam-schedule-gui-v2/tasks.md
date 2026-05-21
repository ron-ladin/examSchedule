# Implementation Plan: examSchedule GUI v2.0 — Sprint Plan

## Overview

Convert examSchedule from a CLI application to a web-based GUI using FastAPI (backend) and React/TypeScript (frontend). The existing Clean Architecture layers remain untouched — FastAPI replaces the CLI as the composition root, injecting new adapter implementations. Work is parallelized across 5 team members in a single 2.5-week sprint.

---

## Sprint Timeline (2.5 Weeks)

| Day | Date Range | Milestone | Key Deliverables |
|-----|-----------|-----------|-----------------|
| **D1–D2** | Week 1 Mon–Tue | Foundation | Alon: scaffolding complete (task 1). Lotem: schemas complete (task 2). Niv: frontend project initialized (task 9.1). |
| **D3–D4** | Week 1 Wed–Thu | Upload & Types | Ron: file upload endpoints live (task 3). Niv: API client + types ready (task 9.2, 9.3). |
| **D5** | Week 1 Fri | Programs & Periods | Ron: program selection + period endpoints (tasks 4, 5). Niv: Input Screen layout started (task 10.1). |
| **D6–D7** | Week 2 Mon–Tue | Generation & Input UI | Ron: generation + schedule endpoints (tasks 6, 7). Niv: Input Screen components (tasks 10.2–10.7). |
| **D8** | Week 2 Wed | Backend Checkpoint | All backend endpoints complete. Checkpoint review (task 8). |
| **D9–D10** | Week 2 Thu–Fri | Output Screen | Niv: Output Screen complete (task 11). Guy: begins API integration tests (task 13). |
| **D11** | Week 3 Mon | Frontend Checkpoint | Frontend complete. Checkpoint review (task 12). Guy: integration tests continue. |
| **D12** | Week 3 Tue | Testing Sprint | Guy: property tests + E2E tests (tasks 14, 15, 16). |
| **D12.5** | Week 3 Wed AM | Final Integration | Alon: integration verification (task 17). Final checkpoint (task 18). |

---

## Team Delegation Matrix

### Lotem (Miluim — Isolated, Non-Blocking)

| Aspect | Detail |
|--------|--------|
| **Assigned Task** | Task 2 — Pydantic Schemas |
| **Scope** | `src/schemas/` module only |
| **Dependencies IN** | None — works from domain entity definitions only |
| **Dependencies OUT** | Ron's endpoints import schemas (but can stub until ready) |
| **Blocking?** | ❌ Completely non-blocking. Can be merged independently at any time. |
| **Isolation Proof** | Zero imports from `src/presentation/`. Zero imports from `frontend/`. No shared state. Schemas are pure data models with conversion helpers. |

### Alon (Team Lead — Architecture & Integration)

| Aspect | Detail |
|--------|--------|
| **Assigned Tasks** | Task 1 (scaffolding), Task 17 (integration verification) |
| **Cross-Layer Responsibilities** | Defines the FastAPI app factory that all routers plug into. Creates the session store that all endpoints depend on. Implements the two adapter classes (APIDataProvider, InMemoryExporter) that bridge presentation→engine layers. Final integration verification spans backend + frontend + existing tests. |
| **PR Review Scope** | All PRs from Ron, Niv, Guy, Lotem |
| **Blocking?** | ✅ Task 1 blocks Ron's work (tasks 3–7). Task 17 is the final gate. |

### Ron (Backend — Heavy Algorithm Work)

| Aspect | Detail |
|--------|--------|
| **Assigned Tasks** | Tasks 3, 4, 5, 6, 7 |
| **Scope** | All `src/presentation/routers/` endpoint implementations |
| **Key Complexity** | Schedule generation orchestration (wiring AppController with asyncio.to_thread), Cartesian product index mapping for schedule browsing, file parsing error handling |
| **Dependencies IN** | Alon's scaffolding (task 1) must be complete before Ron starts |
| **Dependencies OUT** | Niv's frontend consumes Ron's API. Guy's tests validate Ron's endpoints. |

### Niv (Frontend — React SPA)

| Aspect | Detail |
|--------|--------|
| **Assigned Tasks** | Tasks 9, 10, 11 |
| **Scope** | Entire `frontend/` directory |
| **Key Complexity** | Interactive calendar component with date toggling, generation polling with status transitions, Cartesian product schedule navigation |
| **Dependencies IN** | API contract (types.ts can be written from design doc on D1). Actual API available from D3+. |
| **Dependencies OUT** | Guy's E2E tests run against Niv's frontend. |
| **Parallel Start** | Can begin on D1 with project setup + API types (task 9.1, 9.2) before backend is ready. |

### Guy (Testing — Full QA Scope)

| Aspect | Detail |
|--------|--------|
| **Assigned Tasks** | Tasks 13, 14, 15, 16 |
| **Scope** | All test files — integration, property-based, E2E, performance |
| **Dependencies IN** | Backend complete (task 8 checkpoint) for integration tests. Frontend complete (task 12 checkpoint) for E2E tests. |
| **Dependencies OUT** | None — testing is the final validation layer. |
| **Start Timing** | Can begin writing test scaffolding on D8, full execution from D9. |

---

## Critical Path

```
Task 1 (Alon, D1-D2)
  └──► Task 3 (Ron, D3-D4)
        └──► Task 4 (Ron, D5)
              └──► Task 5 (Ron, D5)
                    └──► Task 6 (Ron, D6-D7)
                          └──► Task 7 (Ron, D6-D7)
                                └──► Task 8 (Checkpoint)
                                      └──► Task 13 (Guy, D9-D10)
                                            └──► Task 17 (Alon, D12.5)
                                                  └──► Task 18 (Final Checkpoint)
```

**Secondary Path (Frontend — parallel):**
```
Task 9 (Niv, D1-D4)
  └──► Task 10 (Niv, D5-D7)
        └──► Task 11 (Niv, D9-D10)
              └──► Task 12 (Checkpoint)
                    └──► Task 15 (Guy, D11-D12)
```

**Isolated Path (Non-blocking):**
```
Task 2 (Lotem, D1-D2) — merges independently, no downstream blockers
```

**Key Insight:** The critical path runs through Alon→Ron→Guy→Alon. Any delay in Ron's backend work directly delays the sprint. Niv's frontend runs in parallel and is NOT on the critical path (can use mocked API during development).

---

## Tasks

