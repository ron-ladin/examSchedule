# ExamSchedule — Desktop App Development Guide

## Stack
PyQt6 standalone desktop application. No server, no frontend build step.

---

## App Structure

```
src/
  controller.py     # DesktopController — bridge between UI and engine
  ui/               # PyQt6 desktop application
    app.py          # QMainWindow, sets up the window
    input_screen.py # Main widget: file loading, generation, results tabs
    date_editor.py  # Inline date-range editor widget
    style.py        # QSS stylesheet loader (lazy-cached)
    stylesheet.qss  # Organic Noir design tokens
    tokens.py       # Colour and spacing constants
  adapters/         # File readers and exporters
  domain/           # Core domain models (Course, ExamPeriod, Schedule, ...)
  engine/           # Scheduling logic (AppController, ScheduleGenerator)
  interfaces/       # Abstract base classes (ports)
main.py             # Entry point — launches QApplication (or --cli for headless)
```

---

## Screen Flow

The app is a single `QMainWindow` with one `InputScreen` widget and three tabs:

```
InputScreen (tab: Input)      — load files, select programmes
InputScreen (tab: Generate)   — configure periods, run generation
InputScreen (tab: Results)    — paginated calendar view, per-schedule save
```

All tabs live inside one window; there is no `OutputScreen` or screen-switching.

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
| `courses.txt` | Course records, one per `$$$$`-delimited block |
| `dates.txt` | Exam period records, one per `$$$$`-delimited block |
| `programs.txt` | Programme IDs to include in schedule generation |

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
