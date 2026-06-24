# Memory Handling for Large Schedule Sets

> **Audience:** any engineer (or AI reviewer) who needs to understand how this
> application keeps RAM bounded today, *and* who may later be asked to extend it
> with **disk-backed (hard-drive) storage**. This document is intentionally
> detailed: it explains not only *what* the code does but *why*, and it maps out
> the exact extension points for a future disk-spill implementation.

---

## 1. The Problem in One Paragraph

The exam scheduler generates **schedules** — non-trivial Python objects holding
exam dates, classroom assignments, and proctor data. The set of valid schedules
is a **Cartesian product** of independent choices (date options per period ×
classroom variants per date). That product is, for practical inputs,
*effectively unbounded* — it can reach **billions**. Any naive "generate all,
then sort, then show" pipeline would try to hold billions of objects in RAM at
once and be terminated by the operating system's **OOM (Out-Of-Memory) killer**.
Everything below exists to make that impossible while still giving the user a
fully correct, fully ranked view of the results.

---

## 2. Current Architecture: Bounded Lazy Sampling

The system never enumerates the solution space. It relies on three cooperating
mechanisms.

### 2.1 Lazy generation (`O(n)` memory)

- `ScheduleGenerator` (`src/engine/schedule_generator.py`) is a recursive DFS
  backtracker that **`yield`s one complete schedule at a time**. The partial
  assignment is mutated in place and restored on backtrack, so the generator's
  own footprint is `O(n)` in the number of courses — *independent of how many
  solutions exist*.
- `ClassroomAssigner` (`src/engine/classroom_assigner.py`) likewise streams room
  variants through a generator-based DFS. Iterators are **kept alive between page
  requests**, so "Load More" resumes exactly where the previous page stopped
  instead of regenerating from scratch.

**Key invariant:** nothing is materialised until something explicitly *pages it
in*. Generation cost — not storage — is the real bottleneck.

### 2.2 The capture layer: `_MemoryExporter`

`_MemoryExporter` (`src/engine/generation_workers.py`) implements
`IOutputExporter`. It runs inside a **separate `multiprocessing.Process`** worker
(see `_run_load_more_worker` / `load_worker_pool.py`) and captures generated
schedules into a `schedules_by_period: dict[str, list[Schedule]]`.

- `cap=None` → full generation (collect everything for a period).
- `cap=<int>` → paged generation: it pulls `islice(iter, offset, offset+cap+1)`,
  keeps `cap` schedules, and uses the extra `+1` element purely as a
  **"is there more?" probe** (`truncated_periods`). This `cap+1` look-ahead trick
  is how the UI knows whether to keep the "Load More" button enabled without
  ever over-fetching.

Because this runs in a child process, a runaway generation cannot freeze the GUI
event loop; the parent only receives **picklable batches** over a queue.

### 2.3 The hard ceiling: `ABSOLUTE_MAX_IN_MEMORY_SCHEDULES`

Defined in `src/engine/generation_workers.py`:

```python
ABSOLUTE_MAX_IN_MEMORY_SCHEDULES = 100_000
```

This is the **single most important anti-OOM guardrail**. It is a *population*
cap — the maximum total number of `Schedule` objects the UI may hold in RAM
**across every period and across every Load More / Auto Load request combined**.
It is **not** a generation limit and **not** a per-page limit.

It is enforced at the one and only accumulation point, `ResultsPanel`:

- `ResultsPanel._schedules_by_period: dict[str, list[Schedule]]`
  (`src/ui/results_panel.py`) is the master in-memory store.
- `append_loaded_schedules(period_key, extra)` is the **only** method that grows
  that store. Before extending it:
  - computes `headroom = ABSOLUTE_MAX_IN_MEMORY_SCHEDULES - total_in_memory_schedule_count()`;
  - if `headroom <= 0`, the batch is **refused entirely** (logged, returns);
  - if `len(extra) > headroom`, the batch is **truncated** to the headroom.
- `total_in_memory_schedule_count()` sums `len()` across all periods.
- `is_at_memory_cap()` returns whether the ceiling has been reached.

`LoadMoreController` (`src/ui/load_more_controller.py`) consults
`panel.is_at_memory_cap()` after each merge. At the cap it:

- forces `should_continue_auto = False` (Auto Load stops),
- disables the Load More button and relabels it **"Memory limit reached"**,
- calls `stop_auto_load(...)`.

The result: a user who abuses Auto Load gets a **graceful stop**, never a crash.

### 2.4 CPU vs. memory — two *separate* safeties

It is critical not to confuse these:

| Concern | Mechanism | What it protects |
|---|---|---|
| **CPU** during re-sort | `@lru_cache(maxsize=8192)` on metric helpers in `sorting_engine.py` (`_min_gap`, `_avg_gap`, `_count_same_day_pairs`) | Avoids re-computing the same metrics millions of times across sort-key permutations |
| **Memory** during accumulation | `ABSOLUTE_MAX_IN_MEMORY_SCHEDULES` population cap | Stops the resident object count from growing toward OOM |

The `lru_cache` does **nothing** for memory: re-sorting 200k resident schedules
is CPU-cheap thanks to memoization, but the 200k objects themselves are the OOM
risk. That is why the population cap, not the cache, is the load-bearing fix.

### 2.5 "Result Ranking" re-sorts only the bounded page

When the user re-ranks, `cache_generated_results(...)` sorts the **bounded set
already in memory** (≤ `ABSOLUTE_MAX_IN_MEMORY_SCHEDULES`), not the theoretical
billions. The visible population is treated as a **representative sample** of the
solution space; the user always sees a fully and correctly ranked set that is
*guaranteed to fit in RAM*.

---

## 3. Why External Merge-Sort Was Rejected (today)

External merge-sort (sort RAM-sized chunks, spill to disk, k-way merge) is the
textbook fix for "data larger than memory." It was **deliberately rejected** for
the *current* design because:

1. External merge-sort only helps when the dataset is **large but finite and
   already exists**. Here the billions of schedules **do not exist yet** — they
   would have to be *generated* to feed the merge.
2. Driving the lazy generator to completion to produce every chunk would **hang
   the application** and burn unbounded CPU/disk for a result no human will ever
   page through.
3. The bottleneck is **generation cost**, not merge I/O. A merge-sort solves a
   problem we don't have while leaving the real one — runaway materialisation —
   untouched.

A bounded sample is the correct abstraction. An external sort is a more
expensive way to still crash. **This conclusion is conditional on the current
product requirement** (rank a bounded, human-reviewable sample). Section 4 is
for the day that requirement changes.

---

## 4. Future Work: Adding Disk-Backed (Hard-Drive) Storage

> Read this section before attempting any "spill to disk" change. It exists so a
> future implementation reuses the existing seams instead of bolting on a second,
> conflicting architecture.

### 4.1 When disk-backing actually becomes justified

Only pursue this if a **new product requirement** appears, e.g.:

- the user must rank/export **more than `ABSOLUTE_MAX_IN_MEMORY_SCHEDULES`**
  schedules with a **total ordering across the whole set** (not just a sample);
- or results must **persist across sessions** without regenerating.

If the requirement is still "show the user a good, bounded, ranked set," **do not
add disk storage** — raise the cap instead and measure. Disk-backing trades RAM
for large amounts of I/O, code complexity, and new failure modes (disk full,
corruption, stale temp files, cleanup on crash).

### 4.2 The right shape: a pluggable schedule store

The cleanest path is to introduce a **storage abstraction** that both the current
in-memory path and a future disk path implement, then swap implementations
behind a flag. Sketch:

```python
# src/interfaces/i_schedule_store.py  (NEW)
from typing import Protocol, Iterator
from src.domain.schedule import Schedule

class IScheduleStore(Protocol):
    def append(self, period_key: str, batch: list[Schedule]) -> int: ...   # returns count stored
    def count(self, period_key: str | None = None) -> int: ...
    def page(self, period_key: str, offset: int, limit: int) -> list[Schedule]: ...
    def iter_sorted(self, period_key: str, key) -> Iterator[Schedule]: ...  # external sort lives here
    def clear(self) -> None: ...
```

- **In-memory implementation** = a thin wrapper over today's
  `_schedules_by_period` dict (no behaviour change; keeps the cap).
- **Disk implementation** = one of the options in §4.3.

`ResultsPanel` would depend on `IScheduleStore` instead of holding a raw dict, so
`append_loaded_schedules`, `total_in_memory_schedule_count`, `get_schedules`, and
the navigation model (`NavigationModel`, which already takes a
`schedules_source` callable) all route through the store. **The
`schedules_source` callable seam in `NavigationModel.__init__` is the single most
important existing hook** — it was built to read from a provider, so a disk-backed
provider drops in without touching navigation logic.

### 4.3 Concrete disk-backing options (ranked)

1. **SQLite spill (recommended first choice).**
   - Store each schedule as a row (pickled blob + a few indexed sort columns:
     min_gap, avg_gap, same_day_pairs, etc.).
   - `ORDER BY <sort columns> LIMIT/OFFSET` gives **disk-backed sorting and
     pagination for free**, with the OS page cache doing the heavy lifting.
   - Pre-compute and store the sort metrics at insert time (reuse the same
     functions as `sorting_engine.py`) so ranking is an indexed query, not a
     Python sort.
   - Pros: transactional, crash-safe, no hand-rolled merge logic, trivial paging.
   - Cons: pickle blobs are opaque; schema migration needed if `Schedule` shape
     changes.

2. **True external merge-sort to flat run files.**
   - Generate in chunks of N, sort each chunk in RAM, write each as a sorted
     "run" file (pickle or msgpack), then k-way merge with `heapq.merge`.
   - Only worth it if SQLite's `ORDER BY` proves too slow at the required scale
     (unlikely for hundreds of thousands of rows).
   - **Still requires bounding generation** — see §4.4. The merge does not make
     an infinite generator finite.

3. **Memory-mapped / Arrow columnar store.**
   - Heaviest option; justified only if downstream analytics on millions of
     schedules are needed. Probably overkill for this product.

### 4.4 The non-negotiable rule for *any* disk approach

Even with infinite disk, **you must still bound generation**. The generator can
produce billions; disk just moves the OOM wall to a "disk full" / "never
finishes" wall. So a disk-backed mode must keep a **generation budget** (max
schedules to *generate*, distinct from max to hold in RAM) and the same graceful
"limit reached" UX. Reuse the `cap`/`truncated_periods` look-ahead probe in
`_MemoryExporter` as the budget enforcement point.

### 4.5 Operational concerns a reviewer must check

- **Temp file lifecycle.** Disk runs/DB must live under a managed temp dir and be
  deleted on normal exit *and* on crash (atexit + process-pool teardown in
  `load_worker_pool.py`). Orphaned multi-GB temp files are a real risk.
- **Worker boundary.** Today schedules cross a `multiprocessing.Queue` as
  picklable batches. A disk store should be written by the **child worker** (near
  generation) and read by the parent, or you reintroduce the GUI-freeze problem.
- **Sort stability & determinism.** The in-memory sort is stable; an external/SQL
  sort must reproduce the same tie-breaking (carry an explicit insertion-order
  column) or ranking output will silently differ.
- **Cap interplay.** `ABSOLUTE_MAX_IN_MEMORY_SCHEDULES` becomes the *RAM working
  set* size (page/window size from the store), while a new `MAX_GENERATED_*`
  budget bounds total disk volume. Document both clearly.

---

## 5. File / Symbol Map (quick reference)

| Symbol | File | Role |
|---|---|---|
| `ABSOLUTE_MAX_IN_MEMORY_SCHEDULES` | `src/engine/generation_workers.py` | Hard RAM population cap (100_000) |
| `_MemoryExporter` | `src/engine/generation_workers.py` | Captures schedules in a worker process; `cap+1` look-ahead probe |
| `_run_load_more_worker` | `src/engine/generation_workers.py` | Persistent paging worker entry point |
| `LoadWorkerPool` | `src/engine/load_worker_pool.py` | Process lifecycle for Load More / Auto Load |
| `ResultsPanel._schedules_by_period` | `src/ui/results_panel.py` | Master in-memory store (the accumulation point) |
| `append_loaded_schedules` | `src/ui/results_panel.py` | **Only** writer to the store; enforces the cap |
| `total_in_memory_schedule_count` / `is_at_memory_cap` | `src/ui/results_panel.py` | Cap accounting helpers |
| `LoadMoreController.poll_load_more` | `src/ui/load_more_controller.py` | Stops Auto Load + disables button at the cap |
| `NavigationModel(schedules_source=...)` | `src/ui/navigation_model.py` | Reads store via a callable seam — the future disk-store injection point |
| `_min_gap`/`_avg_gap`/`_count_same_day_pairs` + `lru_cache(8192)` | `src/domain/sorting_engine.py` | CPU memoization (not memory) |

---

## 6. TL;DR for a Reviewer

- RAM is bounded by a **population cap (`100_000`)** enforced in
  `append_loaded_schedules`; CPU is bounded by an **`lru_cache`** in
  `sorting_engine`. They are independent and both necessary.
- We rank a **bounded sample**, never the full Cartesian product.
- External merge-sort is rejected **today** because the data must be *generated*,
  not just sorted — bounding generation is the real lever.
- To go disk-backed later: introduce `IScheduleStore`, inject it through the
  existing `NavigationModel(schedules_source=...)` seam, prefer **SQLite spill**,
  and **keep a generation budget** — disk does not remove the need to bound
  generation.
