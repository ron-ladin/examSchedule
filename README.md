# examSchedule

> Automated university exam scheduling via constraint-based backtracking.

<img width="1536" height="1024" alt="ChatGPT Image May 2, 2026, 11_23_42 AM" src="https://github.com/user-attachments/assets/1ce7ee46-d956-4f40-bf42-d366cf48f099" />

---

## What It Does

Given a set of courses, exam windows, and selected study programs, `examSchedule` generates every valid conflict-free exam schedule — ensuring no student in a selected program sits two exams on the same day.

The engine uses a **conflict graph** + **Most-Constrained-Variable (MCV) heuristic** to prune the backtracking search space, producing results lazily without loading all schedules into memory.

---

## Project Structure

```
examSchedule/
├── main.py                   # CLI entry point
├── data/                     # Input data and generated output
├── src/
│   ├── domain/               # Core entities: Course, Schedule, ExamPeriod, ...
│   ├── engine/               # ScheduleGenerator (backtracking), AppController
│   ├── adapters/             # FileDataProvider, TextFileExporter, ExactConflictStrategy
│   └── interfaces/           # Abstract interfaces (IDataProvider, IOutputExporter, ...)
└── tests/
    ├── unit/
    └── e2e/
```

---

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pytest
```

---

## Usage

```bash
.venv/bin/python main.py \
  --programs data/programs.txt \
  --courses  data/courses.txt \
  --periods  data/dates.txt \
  --output   data/schedules.txt
```

---

## Input File Formats

**programs.txt** — up to 5 comma-separated 5-digit program IDs:
```
83101, 83102, 83108
```

**courses.txt** — records separated by `$$$$` (name, id, instructor, offerings..., evaluation type):
```
Calculus 1
83112
Dr. Erez Scheiner
83101, 1, FALL, Obligatory
Exam
$$$$
```

**dates.txt** — exam period records separated by `$$$$` (semester + moed, date range, optional exclusions):
```
FALL, Aleph
29-01-2026, 19-04-2026
- 14-02-2026, 22-02-2026
$$$$
```

---

## Running Tests

```bash
.venv/bin/python -m pytest tests/ -v
```
