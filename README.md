# examSchedule
<img width="1536" height="1024" alt="ChatGPT Image May 2, 2026, 11_23_42 AM" src="https://github.com/user-attachments/assets/1ce7ee46-d956-4f40-bf42-d366cf48f099" />

---

## What It Does

Given a set of courses, exam windows, and selected study programs, `examSchedule` generates every valid conflict-free exam schedule — ensuring no student in a selected program sits two exams on the same day.

The engine uses a **conflict graph** + **Most-Constrained-Variable (MCV) heuristic** to prune the backtracking search space, producing results lazily without loading all schedules into memory.

---

## Architecture

```mermaid
flowchart TD
    classDef cli        fill:#1e3a5f,stroke:#4a90d9,color:#ffffff,rx:6
    classDef engine     fill:#1a4731,stroke:#2ecc71,color:#ffffff,rx:6
    classDef adapter    fill:#4a1942,stroke:#c678dd,color:#ffffff,rx:6
    classDef domain     fill:#3d2b00,stroke:#e5a22e,color:#ffffff,rx:6
    classDef data       fill:#1c1c2e,stroke:#7f8c8d,color:#cccccc,rx:6
    classDef iface      fill:#2c2c2c,stroke:#888888,color:#aaaaaa,rx:6,stroke-dasharray:4 2

    CLI["⌨️  main.py\nCLI Entry Point"]:::cli

    subgraph ENGINE["  Engine Layer  "]
        Controller["AppController\norchestrates the pipeline"]:::engine
        Generator["ScheduleGenerator\nbacktracking + MCV heuristic"]:::engine
    end

    subgraph ADAPTERS["  Adapters Layer  "]
        Provider["FileDataProvider\nreads & validates input"]:::adapter
        Strategy["ExactConflictStrategy\nconflict detection"]:::adapter
        Exporter["TextFileExporter\nwrites schedules.txt"]:::adapter
    end

    subgraph DOMAIN["  Domain Layer  "]
        Course["Course\n+ CourseOffering"]:::domain
        Period["ExamPeriod\ndate ranges & exclusions"]:::domain
        Schedule["Schedule\ncourse → date map"]:::domain
    end

    subgraph DATA["  Input Files  "]
        Courses["📄 courses.txt"]:::data
        Dates["📄 dates.txt"]:::data
        Programs["📄 programs.txt"]:::data
        Output["📄 schedules.txt"]:::data
    end

    CLI --> Controller
    Controller --> Provider
    Controller --> Generator
    Controller --> Exporter

    Provider --> Courses
    Provider --> Dates
    Provider --> Programs

    Generator --> Strategy
    Generator --> Schedule
    Strategy --> Course
    Schedule --> Period

    Exporter --> Output
```

---

## UML Class Diagram

```mermaid
classDiagram
    direction TB

    class AppController {
        -data_provider: IDataProvider
        -generator: IScheduleGenerator
        -exporter: IOutputExporter
        -selected_programs: List~str~
        +run() None
    }

    class ScheduleGenerator {
        -strategy: IConflictStrategy
        +generate_schedules(courses, period) Iterator~Schedule~
        -_build_conflict_graph(courses) Dict
        -_backtrack(assignment, remaining, ...) Iterator~Schedule~
    }

    class ExactConflictStrategy {
        -selected_programs: Set~str~
        +is_conflict(course1, course2) bool
    }

    class Course {
        +id: str
        +name: str
        +instructor: str
        +evaluation_type: str
        +offerings: List~CourseOffering~
        +has_exam() bool
        +is_relevant_for_period(programs, semester) bool
        +get_relevant_offerings(programs, semester) List
    }

    class CourseOffering {
        +program_id: str
        +year: int
        +semester: str
        +requirement: str
        +is_relevant(programs, semester) bool
        +is_elective() bool
        +same_program_year_semester(other) bool
    }

    class ExamPeriod {
        +semester: str
        +moed: str
        +date_ranges: List~Tuple~
        +excluded_dates: Set~date~
        +get_valid_dates() List~date~
        +get_key() str
    }

    class Schedule {
        +period: ExamPeriod
        +assignments: Dict~str, date~
    }

    class IDataProvider {
        <<interface>>
        +get_courses() List~Course~
        +get_exam_periods() List~ExamPeriod~
        +get_selected_programs() List~str~
    }

    class IConflictStrategy {
        <<interface>>
        +is_conflict(c1, c2) bool
    }

    class IScheduleGenerator {
        <<interface>>
        +generate_schedules(courses, period) Iterator~Schedule~
    }

    class IOutputExporter {
        <<interface>>
        +export_schedules(schedules_by_period, courses_by_id) None
    }

    AppController --> IDataProvider
    AppController --> IScheduleGenerator
    AppController --> IOutputExporter

    ScheduleGenerator ..|> IScheduleGenerator
    ScheduleGenerator --> IConflictStrategy
    ScheduleGenerator --> Schedule

    ExactConflictStrategy ..|> IConflictStrategy

    Course "1" --> "*" CourseOffering
    Schedule --> ExamPeriod
```

---

## Scheduling Algorithm

```mermaid
flowchart LR
    classDef start   fill:#1a4731,stroke:#2ecc71,color:#fff,rx:20
    classDef step    fill:#1e3a5f,stroke:#4a90d9,color:#fff,rx:6
    classDef check   fill:#3d2b00,stroke:#e5a22e,color:#fff,rx:6
    classDef bad     fill:#5c1a1a,stroke:#e74c3c,color:#fff,rx:6
    classDef good    fill:#1a3a3a,stroke:#1abc9c,color:#fff,rx:20

    S([Start]):::start
    MCV["Select course\nwith most conflicts\n(MCV heuristic)"]:::step
    TRY["Try next\navailable date"]:::step
    CHK{Conflict\nwith assigned\nneighbors?}:::check
    ASSIGN["Assign date\nto course"]:::step
    DONE{All courses\nassigned?}:::check
    BACK["Backtrack —\nundo last\nassignment"]:::bad
    WIN([Yield Schedule ✓]):::good

    S --> MCV --> TRY --> CHK
    CHK -- No --> ASSIGN --> DONE
    CHK -- Yes --> TRY
    DONE -- Yes --> WIN
    DONE -- No --> MCV
    TRY -- No dates left --> BACK --> MCV
```

---

## Project Structure

```
examSchedule/
├── main.py                        # CLI entry point (argparse wiring)
├── data/
│   ├── courses.txt                # Course catalog with offerings
│   ├── dates.txt                  # Exam periods, date ranges, exclusions
│   └── programs.txt               # Selected program IDs (up to 5)
├── src/
│   ├── domain/                    # Pure domain entities — no I/O
│   │   ├── course.py
│   │   ├── course_offering.py
│   │   ├── exam_period.py
│   │   ├── schedule.py
│   │   └── semester.py
│   ├── interfaces/                # Abstract ports (ABC)
│   │   ├── i_data_provider.py
│   │   ├── i_conflict_strategy.py
│   │   ├── i_schedule_generator.py
│   │   └── i_output_exporter.py
│   ├── engine/                    # Core logic — depends only on interfaces
│   │   ├── app_controller.py
│   │   └── schedule_generator.py
│   └── adapters/                  # Concrete implementations
│       ├── exact_conflict_strategy.py
│       ├── file_data_provider.py
│       ├── text_file_exporter.py
│       └── readers/
│           ├── course_file_reader.py
│           ├── exam_period_file_reader.py
│           └── program_selector_reader.py
└── tests/
    ├── unit/                      # 74 tests — fast, no pipeline
    └── e2e/                       # 10 tests — full pipeline, real + synthetic data
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

**courses.txt** — records separated by `$$$$`:
```
Calculus 1
83112
Dr. Erez Scheiner
83101, 1, FALL, Obligatory
Exam
$$$$
```

**dates.txt** — exam period records separated by `$$$$`:
```
FALL, Aleph
29-01-2026, 11-03-2026
- 14-02-2026
$$$$
```

---

## Running Tests

```bash
.venv/bin/python -m pytest tests/ -v
```

**84 test functions · 89 pytest runs · all passing**

| Layer | Tests | Focus |
|-------|-------|-------|
| Unit | 74 | Per-class, no pipeline I/O |
| E2E | 10 | Full pipeline, real + synthetic data |
