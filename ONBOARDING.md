# ExamSchedule — Desktop App Development Guide

## Stack
PyQt6 standalone desktop application. No server, no frontend build step.

---

## App Structure

```
src/
  ui/               # PyQt6 screens (InputScreen, OutputScreen)
  adapters/         # File readers and exporters
  domain/           # Core domain models (Course, ExamPeriod, Schedule, ...)
  use_cases/        # Scheduling logic
  interfaces/       # Abstract base classes
main.py             # Entry point — launches QApplication
```

---

## Screen Flow

```
InputScreen  →  OutputScreen
(load files,     (paginated calendar view,
 select           per-schedule save)
 programmes,
 generate)
```

---

## Running Locally

```bash
pip install -r requirements.txt
python main.py
```

No environment variables or servers needed.

---

## Input Files

| File | Purpose |
|------|---------|
| `CourseDB.txt` | Course records, one per `$$$$`-delimited block |
| `ExamDates.txt` | Exam period records, one per `$$$$`-delimited block |

---

## Running Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Coverage must stay at or above **85%**. CI enforces this with `--cov-fail-under=85`.

`src/ui` is excluded from coverage and pylint — PyQt6 requires a display to import.

---

## Linting

```bash
python -m pylint src --ignore=ui
```
