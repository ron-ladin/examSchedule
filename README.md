# examSchedule

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'fontSize': '15px'}}}%%
flowchart TD
    classDef cli     fill:#0f2744,stroke:#4a90d9,color:#7ec8f7,rx:8,font-weight:bold
    classDef engine  fill:#0f2e1a,stroke:#2ecc71,color:#7effa4,rx:6,font-weight:bold
    classDef adapter fill:#2a0f3a,stroke:#c678dd,color:#e0a8ff,rx:6
    classDef reader  fill:#2e1f00,stroke:#e5a22e,color:#ffd27e,rx:6
    classDef domain  fill:#1a1a2e,stroke:#e05c5c,color:#ff9999,rx:6
    classDef iface   fill:#111111,stroke:#555555,color:#aaaaaa,rx:4,stroke-dasharray:5 3
    classDef file    fill:#0d1117,stroke:#30363d,color:#8b949e,rx:4

    CLI["⌨️  main.py\n─────────────\nCLI · argparse · wiring"]:::cli

    subgraph CORE["  🧠  Engine Layer  "]
        direction LR
        Controller["AppController\n─────────────\norchestrates pipeline"]:::engine
        Generator["ScheduleGenerator\n─────────────\nbacktracking · MCV"]:::engine
    end

    subgraph PORTS["  🔌  Interfaces (Ports)  "]
        direction LR
        IDP["IDataProvider"]:::iface
        ICS["IConflictStrategy"]:::iface
        ISG["IScheduleGenerator"]:::iface
        IOE["IOutputExporter"]:::iface
    end

    subgraph ADAPT["  🔧  Adapters  "]
        direction LR
        Provider["FileDataProvider"]:::adapter
        Strategy["ExactConflictStrategy"]:::adapter
        Exporter["TextFileExporter"]:::adapter
    end

    subgraph READERS["  📖  Readers  "]
        direction LR
        CR["CourseFileReader"]:::reader
        PR["ExamPeriodFileReader"]:::reader
        RR["ProgramSelectorReader"]:::reader
    end

    subgraph DOMAIN["  🏛️  Domain  "]
        direction LR
        Course["Course\n+ CourseOffering"]:::domain
        Period["ExamPeriod"]:::domain
        Schedule["Schedule"]:::domain
    end

    subgraph FILES["  📁  Files  "]
        direction LR
        F1["courses.txt"]:::file
        F2["dates.txt"]:::file
        F3["programs.txt"]:::file
        F4["schedules.txt"]:::file
    end

    CLI --> Controller
    Controller --> IDP & ISG & IOE

    IDP -.implements.- Provider
    ISG -.implements.- Generator
    IOE -.implements.- Exporter
    ICS -.implements.- Strategy

    Provider --> CR & PR & RR
    Generator --> ICS
    Generator --> Schedule
    Strategy --> Course
    Schedule --> Period

    CR --> F1
    PR --> F2
    RR --> F3
    Exporter --> F4
```

---

## What It Does

Given a set of courses, exam windows, and selected study programs, `examSchedule` generates every valid conflict-free exam schedule — ensuring no student in a selected program sits two exams on the same day.

The engine uses a **conflict graph** + **Most-Constrained-Variable (MCV) heuristic** to prune the backtracking search space, producing results lazily without loading all schedules into memory.

---

## UML Class Diagram

```mermaid
classDiagram
    direction TB

    namespace Domain {
        class Course {
            +id : str
            +name : str
            +instructor : str
            +evaluation_type : str
            +offerings : List~CourseOffering~
            +add_offering(offering: CourseOffering) None
            +has_exam() bool
            +get_relevant_offerings(programs: List, semester: str) List~CourseOffering~
            +is_relevant_for_period(programs: List, semester: str) bool
        }
        class CourseOffering {
            +program_id : str
            +year : int
            +semester : str
            +requirement : str
            +is_relevant(programs: List, semester: str) bool
            +is_elective() bool
            +same_program_year_semester(other: CourseOffering) bool
        }
        class ExamPeriod {
            +semester : str
            +moed : str
            +date_ranges : List~Tuple~date_date~~
            +excluded_dates : Set~date~
            +get_valid_dates() List~date~
            +get_key() str
        }
        class Schedule {
            +period : ExamPeriod
            +assignments : Dict~str_date~
        }
    }

    namespace Interfaces {
        class IDataProvider {
            <<interface>>
            +get_courses() List~Course~
            +get_exam_periods() List~ExamPeriod~
            +get_selected_programs() List~str~
        }
        class IOutputExporter {
            <<interface>>
            +export_schedules(schedules_by_period: Dict, courses_by_id: Dict) None
        }
        class IConflictStrategy {
            <<interface>>
            +is_conflict(course1: Course, course2: Course) bool
        }
        class IScheduleGenerator {
            <<interface>>
            +generate_schedules(courses: List, period: ExamPeriod) Iterator~Schedule~
        }
    }

    namespace Engine {
        class AppController {
            <<controller>>
            -_data_provider : IDataProvider
            -_exporter : IOutputExporter
            -_generator : IScheduleGenerator
            -_selected_programs : List~str~
            +run() None
            -_sort_exam_periods(periods) List~ExamPeriod~
            -_validate_selected_programs_exist(courses) None
        }
        class ScheduleGenerator {
            <<engine>>
            -_strategy : IConflictStrategy
            +generate_schedules(courses: List, period: ExamPeriod) Iterator~Schedule~
            -_build_conflict_graph(courses: List) Dict~Course_Set~Course~~
            -_backtrack(assignment remaining valid_dates conflict_graph period) Iterator~Schedule~
        }
    }

    namespace Adapters {
        class FileDataProvider {
            <<adapter>>
            +course_reader : CourseFileReader
            +exam_period_reader : ExamPeriodFileReader
            +program_reader : ProgramSelectorReader
            +get_courses() List~Course~
            +get_exam_periods() List~ExamPeriod~
            +get_selected_programs() List~str~
        }
        class TextFileExporter {
            <<adapter>>
            +output_path : Path
            +export_schedules(schedules_by_period: Dict, courses_by_id: Dict) None
            -_write_period_header(file semester: str, moed: str) None
            -_write_schedule(file n: int, schedule: Schedule, courses_by_id: Dict) None
            -_split_period_key(period_key: str) Tuple~str_str~
        }
        class ExactConflictStrategy {
            <<adapter>>
            -_selected_programs : Set~str~
            +is_conflict(course1: Course, course2: Course) bool
        }
    }

    namespace Readers {
        class CourseFileReader {
            +courses_path : Path
            +read() List~Course~
        }
        class ExamPeriodFileReader {
            +periods_path : Path
            +read() List~ExamPeriod~
        }
        class ProgramSelectorReader {
            +programs_path : Path
            +read() List~str~
        }
    }

    Course "1" *-- "0..*" CourseOffering : contains
    Schedule --> ExamPeriod : period

    FileDataProvider ..|> IDataProvider
    TextFileExporter ..|> IOutputExporter
    ExactConflictStrategy ..|> IConflictStrategy
    ScheduleGenerator ..|> IScheduleGenerator

    AppController --> IDataProvider : uses
    AppController --> IScheduleGenerator : uses
    AppController --> IOutputExporter : uses
    ScheduleGenerator --> IConflictStrategy : consults
    ScheduleGenerator ..> Schedule : yields

    FileDataProvider --> CourseFileReader : delegates
    FileDataProvider --> ExamPeriodFileReader : delegates
    FileDataProvider --> ProgramSelectorReader : delegates
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

## How to run

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

---

## All Diagrams

Full diagram set (architecture, sequences, data flow, conflict logic, test strategy): [diagrams.md](./diagrams.md)
