"""Manual generation/ranking benchmark entry point.

Run from the repository root:

    python scripts/benchmark_generation.py

The benchmarks intentionally consume only a bounded generation batch so they are
repeatable and do not try to exhaust large theoretical search spaces.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import islice

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.adapters.sqlite_schedule_store import SQLiteScheduleStore
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.sorting import SortCriterion, SortingConfig
from src.domain.threshold import ThresholdSettings
from src.engine.schedule_generator import ScheduleGenerator


DEFAULT_BENCHMARK_BATCH_SIZE = 5000


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    course_count: int
    day_count: int
    program_count: int = 1
    same_year: bool = True
    student_count: int | None = None


def _course(
    index: int,
    *,
    program_count: int,
    same_year: bool,
    student_count: int | None,
) -> Course:
    course_id = f"C{index:04d}"
    program = f"83{100 + (index % program_count)}"
    year = 1 if same_year else (index % 3) + 1
    requirement = "Obligatory" if index % 2 == 0 else "Elective"
    return Course(
        id=course_id,
        name=f"Course {index}",
        instructor="Benchmark",
        evaluation_type="Exam",
        offerings=[
            CourseOffering(
                program,
                year,
                "FALL",
                requirement,
                student_count,
            )
        ],
    )


def _period(day_count: int) -> ExamPeriod:
    start = date(2026, 1, 5)
    return ExamPeriod(
        "FALL",
        "Aleph",
        [(start, start + timedelta(days=max(0, day_count - 1)))],
    )


def _cases() -> list[BenchmarkCase]:
    return [
        BenchmarkCase("small", course_count=3, day_count=7),
        BenchmarkCase("medium", course_count=5, day_count=14),
        BenchmarkCase("large", course_count=7, day_count=21, program_count=2),
        BenchmarkCase(
            "feature4",
            course_count=5,
            day_count=14,
            program_count=2,
            student_count=120,
        ),
        BenchmarkCase("high-conflict", course_count=6, day_count=10),
        BenchmarkCase(
            "worst-case-ish",
            course_count=8,
            day_count=21,
            program_count=4,
            same_year=False,
        ),
    ]


def run_case(case: BenchmarkCase, batch_size: int) -> dict[str, object]:
    programs = [f"83{100 + idx}" for idx in range(case.program_count)]
    courses = [
        _course(
            index,
            program_count=case.program_count,
            same_year=case.same_year,
            student_count=case.student_count,
        )
        for index in range(case.course_count)
    ]
    period = _period(case.day_count)
    generator = ScheduleGenerator(
        ExactConflictStrategy(selected_programs=programs),
        threshold_settings=ThresholdSettings(),
        selected_programs=programs,
    )

    started = time.perf_counter()
    schedules = list(islice(generator.generate_schedules(courses, period), batch_size))
    generation_seconds = time.perf_counter() - started

    store = SQLiteScheduleStore(delete_on_close=True)
    try:
        stored_started = time.perf_counter()
        stored = store.append_many(
            period.get_key(),
            schedules,
            courses=courses,
            selected_programs=programs,
        )
        store_seconds = time.perf_counter() - stored_started

        sorting = SortingConfig.from_ordered_criteria(
            [SortCriterion.SORT_MIN_DAYS_MANDATORY]
        )
        ranking_started = time.perf_counter()
        store.warm_order(period.get_key(), sorting)
        ranking_seconds = time.perf_counter() - ranking_started
        sqlite_rows = store.total_count()
    finally:
        store.close(delete=True)

    metrics = generator.last_metrics
    return {
        "case": case.name,
        "courses": case.course_count,
        "days": case.day_count,
        "generated": len(schedules),
        "stored": stored,
        "sqlite_rows": sqlite_rows,
        "generation_seconds": generation_seconds,
        "store_seconds": store_seconds,
        "ranking_seconds": ranking_seconds,
        "nodes": metrics.nodes_visited,
        "domain_prunes": metrics.domain_prunes,
        "conflict_prunes": metrics.conflict_prunes,
        "threshold_prunes": metrics.threshold_prunes,
    }


def main() -> None:
    batch_size = DEFAULT_BENCHMARK_BATCH_SIZE
    rows = [run_case(case, batch_size) for case in _cases()]
    headers = (
        "case",
        "courses",
        "days",
        "generated",
        "sqlite_rows",
        "gen_s",
        "store_s",
        "rank_s",
        "nodes",
        "prunes",
    )
    print(" | ".join(headers))
    print("-" * 104)
    for row in rows:
        print(
            " | ".join(
                [
                    str(row["case"]),
                    str(row["courses"]),
                    str(row["days"]),
                    str(row["generated"]),
                    str(row["sqlite_rows"]),
                    f"{row['generation_seconds']:.3f}",
                    f"{row['store_seconds']:.3f}",
                    f"{row['ranking_seconds']:.3f}",
                    str(row["nodes"]),
                    str(
                        row["domain_prunes"]
                        + row["conflict_prunes"]
                        + row["threshold_prunes"]
                    ),
                ]
            )
        )


if __name__ == "__main__":
    main()
