# ADR: Partial Classroom Placement — "Always place what you can, flag the gap"

- Status: Accepted
- Date: 2026-06-26
- Tickets: SCRUM-390

## Problem

Feature 4 assigns rooms and time slots to every exam in a generated date
schedule. A single exam whose student count exceeds the combined usable capacity
of all available rooms can never be placed under any room arrangement. With the
original strict behaviour, one such oversized exam caused `ClassroomAssigner` to
reject **every** candidate schedule, blanking the entire solution space. The
user saw "no schedules could be generated" even though every other exam was
perfectly placeable, with no indication of which exam caused the failure.

Two distinct failure modes share this symptom:

1. **Structural capacity shortfall** — the exam is larger than the total usable
   capacity of all rooms combined. It is un-placeable regardless of scheduling.
2. **Runtime assignment failure** — the exam fits the total capacity, but no
   valid room combination is free at assignment time (e.g. two same-day exams
   contending for the same rooms in the only time slot).

## Decision

Adopt a "always place what you can, flag the gap" strategy:

- A pure, capacity-only pre-flight (`Feature4Validator.unplaceable_exams`)
  detects structural shortfalls before generation.
- A dedicated business policy (`PartialPlacementPolicy`) decides whether a period
  must route through the unassigned fallback and **why**, returning an explicit
  `PlacementFailureReason` (`STRUCTURAL_CAPACITY_SHORTFALL` or
  `RUNTIME_ASSIGNMENT_FAILURE`). `AppController` only orchestrates — it asks the
  policy and acts on the answer.
- `ClassroomAssigner` places every exam it can and records the rest in
  `unassigned_classroom_exams` instead of discarding the whole schedule.
- The two failure modes are kept distinct internally, even though they can lead
  to the same user-visible outcome (an exam flagged as unassigned).

## Alternatives considered

- **Keep strict all-or-nothing placement.** Rejected: a single oversized exam
  blanks the whole run and gives the user no actionable information.
- **Silently drop un-placeable exams.** Rejected: violates "never silently
  swallow errors"; the user must see which exams need attention.
- **Hard-fail with an error before generation.** Rejected: the user still wants
  the placeable exams scheduled; failing the whole run is heavier than needed.
- **Collapse both failure modes into one flag.** Rejected: structural and
  runtime failures need different remediation (add capacity vs. relax
  scheduling), so they must remain distinguishable internally and in logs.

## Consequences

- Generation degrades gracefully: placeable exams are always scheduled, and
  un-placeable ones are flagged rather than hidden.
- Structured diagnostics (course id/name, student count, max usable capacity,
  failure reason) make production troubleshooting straightforward.
- Business policy is isolated in `PartialPlacementPolicy`, so the controller
  stays a thin orchestration layer and the rule is unit-testable in isolation.
- Runtime failures only surface while the exporter consumes the lazy schedule
  iterator, so per-exam runtime logging cannot happen at pre-flight time; the
  controller logs that the runtime fallback is enabled for the period instead.

## Why "always place what you can" was chosen

The product goal is to help a human scheduler converge on a workable plan. A
single oversized exam is a data/capacity problem the scheduler must resolve out
of band (add rooms, split the exam). Blocking all other valid placements until
then wastes their time and hides the rest of the schedule. Placing everything
possible and clearly flagging the gap turns a dead-end into an actionable,
incremental workflow.
