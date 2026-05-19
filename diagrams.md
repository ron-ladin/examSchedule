# examSchedule — All Diagrams

---

## 1. System Hierarchy

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

    CLI["main.py\n─────────────\nCLI · argparse · wiring"]:::cli

    subgraph CORE["  Engine Layer  "]
        direction LR
        Controller["AppController\n─────────────\norchestrates pipeline"]:::engine
        Generator["ScheduleGenerator\n─────────────\nbacktracking · MCV"]:::engine
    end

    subgraph PORTS["  Interfaces (Ports)  "]
        direction LR
        IDP["IDataProvider"]:::iface
        ICS["IConflictStrategy"]:::iface
        ISG["IScheduleGenerator"]:::iface
        IOE["IOutputExporter"]:::iface
    end

    subgraph ADAPT["  Adapters  "]
        direction LR
        Provider["FileDataProvider"]:::adapter
        Strategy["ExactConflictStrategy"]:::adapter
        Exporter["TextFileExporter"]:::adapter
    end

    subgraph READERS["  Readers  "]
        direction LR
        CR["CourseFileReader"]:::reader
        PR["ExamPeriodFileReader"]:::reader
        RR["ProgramSelectorReader"]:::reader
    end

    subgraph DOMAIN["  Domain  "]
        direction LR
        Course["Course\n+ CourseOffering"]:::domain
        Period["ExamPeriod"]:::domain
        Schedule["Schedule"]:::domain
    end

    subgraph FILES["  Files  "]
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

## 2. Clean Architecture — Layer Dependencies

```mermaid
%%{init: {'theme': 'dark'}}%%
flowchart LR
    classDef cli     fill:#0f2744,stroke:#4a90d9,color:#7ec8f7
    classDef engine  fill:#0f2e1a,stroke:#2ecc71,color:#7effa4
    classDef iface   fill:#1a1a1a,stroke:#555,color:#aaa,stroke-dasharray:4 2
    classDef adapter fill:#2a0f3a,stroke:#c678dd,color:#e0a8ff
    classDef domain  fill:#1a1a2e,stroke:#e05c5c,color:#ff9999

    subgraph CLI_LAYER["CLI"]
        main["main.py"]:::cli
    end

    subgraph ENGINE_LAYER["Engine"]
        AC["AppController"]:::engine
        SG["ScheduleGenerator"]:::engine
    end

    subgraph IFACE_LAYER["Interfaces (Ports)"]
        IDP["IDataProvider"]:::iface
        IOE["IOutputExporter"]:::iface
        ICS["IConflictStrategy"]:::iface
        ISG["IScheduleGenerator"]:::iface
    end

    subgraph ADAPTER_LAYER["Adapters"]
        FDP["FileDataProvider"]:::adapter
        TFE["TextFileExporter"]:::adapter
        ECS["ExactConflictStrategy"]:::adapter
    end

    subgraph DOMAIN_LAYER["Domain"]
        C["Course"]:::domain
        CO["CourseOffering"]:::domain
        EP["ExamPeriod"]:::domain
        S["Schedule"]:::domain
    end

    main --> AC
    AC --> IDP & IOE & ISG
    SG --> ICS
    SG ..|> ISG
    FDP ..|> IDP
    TFE ..|> IOE
    ECS ..|> ICS

    FDP --> C & EP
    ECS --> C
    SG --> S
    S --> EP
    C --> CO

    note["Dependency rule:\ninner layers know nothing\nabout outer layers"]
```

---

## 3. UML Class Diagram

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

## 4. Sequence — Full Pipeline

```mermaid
%%{init: {'theme': 'dark'}}%%
sequenceDiagram
    actor User
    participant CLI as main.py
    participant AC as AppController
    participant FDP as FileDataProvider
    participant SG as ScheduleGenerator
    participant ECS as ExactConflictStrategy
    participant TFE as TextFileExporter

    User->>CLI: python main.py --courses --periods --programs --output
    CLI->>AC: run()

    AC->>FDP: get_selected_programs()
    FDP-->>AC: ["83101", "83102"]

    AC->>FDP: get_courses()
    FDP-->>AC: List[Course]

    AC->>AC: _validate_selected_programs_exist(courses)

    AC->>FDP: get_exam_periods()
    FDP-->>AC: List[ExamPeriod]

    AC->>AC: _sort_exam_periods(periods)

    loop for each ExamPeriod
        AC->>AC: filter relevant courses
        AC->>SG: generate_schedules(courses, period)
        Note over SG: lazy Iterator — not consumed yet
    end

    AC->>TFE: export_schedules(schedules_by_period, courses_by_id)

    loop for each period
        loop for each Schedule (lazy)
            TFE->>SG: next(iterator)
            SG->>ECS: is_conflict(course1, course2)
            ECS-->>SG: bool
            SG-->>TFE: Schedule
            TFE->>TFE: _write_schedule()
        end
    end

    TFE-->>User: schedules.txt written
```

---

## 5. Sequence — Data Loading

```mermaid
%%{init: {'theme': 'dark'}}%%
sequenceDiagram
    participant AC as AppController
    participant FDP as FileDataProvider
    participant CR as CourseFileReader
    participant EPR as ExamPeriodFileReader
    participant PSR as ProgramSelectorReader

    AC->>FDP: get_selected_programs()
    FDP->>PSR: read()
    PSR->>PSR: validate (5-digit, ≤5, unique)
    PSR-->>FDP: List[str]
    FDP-->>AC: ["83101", "83102"]

    AC->>FDP: get_courses()
    FDP->>CR: read()
    CR->>CR: _read_records() — split on $$$$
    loop for each record
        CR->>CR: _parse_course_record()
        CR->>CR: _parse_course_offering() per line
        CR->>CR: validate id, year, semester, evaluation, requirement
    end
    CR->>CR: _validate_unique_course_ids()
    CR-->>FDP: List[Course]
    FDP-->>AC: List[Course]

    AC->>FDP: get_exam_periods()
    FDP->>EPR: read()
    EPR->>EPR: _read_records() — split on $$$$
    loop for each record
        EPR->>EPR: _parse_period_header() — semester, moed
        EPR->>EPR: _parse_date_range() — start, end
        EPR->>EPR: _parse_excluded_dates() per line
    end
    EPR-->>FDP: List[ExamPeriod]
    FDP-->>AC: List[ExamPeriod]
```

---

## 6. Scheduling Algorithm — Backtracking + MCV

```mermaid
%%{init: {'theme': 'dark'}}%%
flowchart LR
    classDef start fill:#1a4731,stroke:#2ecc71,color:#fff,rx:20
    classDef step  fill:#1e3a5f,stroke:#4a90d9,color:#fff,rx:6
    classDef check fill:#3d2b00,stroke:#e5a22e,color:#fff,rx:6
    classDef bad   fill:#5c1a1a,stroke:#e74c3c,color:#fff,rx:6
    classDef good  fill:#1a3a3a,stroke:#1abc9c,color:#fff,rx:20

    S([Start]):::start
    DATES["Resolve valid dates\nfrom ExamPeriod\n(exclude Sat + holidays)"]:::step
    GRAPH["Build conflict graph\nO(n²) — once"]:::step
    MCV["Sort courses by\nconflict count DESC\n(MCV heuristic)"]:::step
    TRY["Try next available date\nfor current course"]:::step
    CHK{Date blocked by\nassigned neighbor?}:::check
    ASSIGN["Assign date\nto course"]:::step
    DONE{All courses\nassigned?}:::check
    BACK["Backtrack —\ndel assignment\ntry next date"]:::bad
    WIN([Yield Schedule ✓\nDict[course_id → date]]):::good
    EMPTY([Return — no\nmore schedules]):::bad

    S --> DATES --> GRAPH --> MCV --> TRY --> CHK
    CHK -- No --> ASSIGN --> DONE
    CHK -- Yes --> TRY
    DONE -- Yes --> WIN
    WIN --> TRY
    DONE -- No --> TRY
    TRY -- No dates left --> BACK --> TRY
    BACK -- No courses left --> EMPTY
```

---

## 7. Conflict Detection Logic

```mermaid
%%{init: {'theme': 'dark'}}%%
flowchart TD
    classDef step  fill:#1e3a5f,stroke:#4a90d9,color:#fff,rx:6
    classDef check fill:#3d2b00,stroke:#e5a22e,color:#fff,rx:6
    classDef yes   fill:#1a3a3a,stroke:#e74c3c,color:#ff9999,rx:20
    classDef no    fill:#1a4731,stroke:#2ecc71,color:#7effa4,rx:20

    START["is_conflict(course1, course2)"]:::step

    LOOP1["For each offering O1\nin course1"]:::step
    SEL1{O1.program_id\nin selected_programs?}:::check

    LOOP2["For each offering O2\nin course2"]:::step
    SEL2{O2.program_id\nin selected_programs?}:::check

    MATCH{O1 and O2 share\nprogram + year + semester?}:::check
    ELEC{Both O1 and O2\nare Elective?}:::check

    CONFLICT([return True\n⚠ CONFLICT]):::yes
    NO_CONFLICT([return False\n✓ no conflict]):::no

    START --> LOOP1 --> SEL1
    SEL1 -- No --> LOOP1
    SEL1 -- Yes --> LOOP2 --> SEL2
    SEL2 -- No --> LOOP2
    SEL2 -- Yes --> MATCH
    MATCH -- No --> LOOP2
    MATCH -- Yes --> ELEC
    ELEC -- Yes, both elective --> LOOP2
    ELEC -- No --> CONFLICT
    LOOP1 -- exhausted --> NO_CONFLICT
```

---

## 8. Data Flow — Input to Output

```mermaid
%%{init: {'theme': 'dark'}}%%
flowchart LR
    classDef file    fill:#0d1117,stroke:#30363d,color:#8b949e,rx:4
    classDef reader  fill:#2e1f00,stroke:#e5a22e,color:#ffd27e,rx:6
    classDef domain  fill:#1a1a2e,stroke:#e05c5c,color:#ff9999,rx:6
    classDef engine  fill:#0f2e1a,stroke:#2ecc71,color:#7effa4,rx:6
    classDef output  fill:#0f2744,stroke:#4a90d9,color:#7ec8f7,rx:6

    F1["courses.txt"]:::file
    F2["dates.txt"]:::file
    F3["programs.txt"]:::file

    CR["CourseFileReader\nparse · validate"]:::reader
    EPR["ExamPeriodFileReader\nparse · validate"]:::reader
    PSR["ProgramSelectorReader\nparse · validate"]:::reader

    C["List[Course]\n+ CourseOffering"]:::domain
    EP["List[ExamPeriod]\nvalid dates computed"]:::domain
    P["List[str]\nselected program IDs"]:::domain

    AC["AppController\nfilter · sort · orchestrate"]:::engine
    SG["ScheduleGenerator\nbacktrack · MCV · yield"]:::engine

    S["Iterator[Schedule]\nDict[course_id → date]"]:::domain

    TFE["TextFileExporter\nformat · write"]:::engine
    OUT["schedules.txt"]:::output

    F1 --> CR --> C
    F2 --> EPR --> EP
    F3 --> PSR --> P
    C & EP & P --> AC
    AC --> SG --> S --> TFE --> OUT
```

---

## 9. Test Architecture

```mermaid
%%{init: {'theme': 'dark'}}%%
flowchart TD
    classDef layer fill:#1e3a5f,stroke:#4a90d9,color:#fff,rx:6
    classDef unit  fill:#1a4731,stroke:#2ecc71,color:#7effa4,rx:4
    classDef e2e   fill:#4a1942,stroke:#c678dd,color:#e0a8ff,rx:4
    classDef stat  fill:#0d1117,stroke:#30363d,color:#8b949e,rx:4

    UNIT["Unit Tests\n74 functions"]:::layer
    E2E["E2E Tests\n10 functions"]:::layer

    U1["test_course.py\n12 tests"]:::unit
    U2["test_course_offering.py\n10 tests"]:::unit
    U3["test_exam_period.py\n9 tests"]:::unit
    U4["test_schedule.py\n2 tests"]:::unit
    U5["test_conflict_strategy.py\n7 tests · 1 parametrized×6"]:::unit
    U6["test_schedule_generator.py\n12 tests"]:::unit
    U7["test_file_data_provider.py\n15 tests"]:::unit
    U8["test_text_file_exporter.py\n7 tests"]:::unit

    E1["test_full_pipeline.py\n10 tests\nsynthetic + real data"]:::e2e

    TOTAL["84 functions · 89 pytest runs\nAll passing ✓"]:::stat

    UNIT --> U1 & U2 & U3 & U4 & U5 & U6 & U7 & U8
    E2E --> E1
    UNIT & E2E --> TOTAL
```

---

## 10. Semester Normalization

```mermaid
%%{init: {'theme': 'dark'}}%%
flowchart LR
    classDef input  fill:#2e1f00,stroke:#e5a22e,color:#ffd27e,rx:6
    classDef norm   fill:#1e3a5f,stroke:#4a90d9,color:#7ec8f7,rx:6
    classDef disp   fill:#1a4731,stroke:#2ecc71,color:#7effa4,rx:6

    IN1["FALL / fall / Fall"]:::input
    IN2["SPRI / spri\nSPRING / spring"]:::input
    IN3["SUMM / summ\nSUMMER / summer"]:::input

    N1["FALL"]:::norm
    N2["SPRI"]:::norm
    N3["SUMM"]:::norm

    D1["FALL"]:::disp
    D2["SPRING"]:::disp
    D3["SUMMER"]:::disp

    IN1 -- normalize_semester --> N1
    IN2 -- normalize_semester --> N2
    IN3 -- normalize_semester --> N3

    N1 -- display_semester --> D1
    N2 -- display_semester --> D2
    N3 -- display_semester --> D3
```
