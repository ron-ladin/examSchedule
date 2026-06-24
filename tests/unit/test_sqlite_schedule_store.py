"""Unit tests for the SQLite-backed schedule result store."""

from datetime import date

from src.adapters.sqlite_schedule_store import SQLiteScheduleExporter, SQLiteScheduleStore
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.domain.settings import Settings
from src.domain.sorting import SortCriterion, SortingConfig, SortRule
from src.domain.threshold import ThresholdSettings

PROGRAM = "83101"
PERIOD = ExamPeriod(
    semester="FALL",
    moed="Aleph",
    date_ranges=[(date(2026, 1, 5), date(2026, 1, 31))],
)


def _course(course_id: str) -> Course:
    course = Course(
        id=course_id,
        name=f"Course {course_id}",
        instructor="Dr. Test",
        evaluation_type="Exam",
    )
    course.add_offering(
        CourseOffering(PROGRAM, 1, "FALL", "Obligatory")
    )
    return course


def _schedule(gap: int) -> Schedule:
    return Schedule(
        PERIOD,
        {
            "11111": date(2026, 1, 5),
            "22222": date(2026, 1, 5 + gap),
        },
    )


def _sorting() -> SortingConfig:
    return SortingConfig(
        rules=(
            SortRule(1, SortCriterion.SORT_MIN_DAYS_MANDATORY),
        )
    )


def test_store_supports_len_index_iteration_and_pages(tmp_path):
    store = SQLiteScheduleStore(tmp_path / "schedules.sqlite3", delete_on_close=False)
    schedules = [_schedule(1), _schedule(2), _schedule(3)]

    store.append_many("FALL - Aleph", schedules)
    view = store.as_sequence("FALL - Aleph")

    assert len(view) == 3
    assert view[0] == schedules[0]
    assert view[-1] == schedules[-1]
    assert view[1:] == schedules[1:]
    assert list(view) == schedules

    store.close(delete=True)


def test_store_orders_by_precomputed_scores_without_rewriting_rows(tmp_path):
    store = SQLiteScheduleStore(tmp_path / "schedules.sqlite3", delete_on_close=False)
    courses = [_course("11111"), _course("22222")]
    narrow = _schedule(2)
    wide = _schedule(10)
    medium = _schedule(5)

    store.append_many(
        "FALL - Aleph",
        [narrow, wide, medium],
        courses=courses,
        selected_programs=[PROGRAM],
    )
    view = store.as_sequence(
        "FALL - Aleph",
        courses=courses,
        selected_programs=[PROGRAM],
        sorting=_sorting(),
    )

    assert list(view) == [wide, medium, narrow]

    store.close(delete=True)


def test_sqlite_exporter_streams_generator_in_chunks(tmp_path):
    courses = [_course("11111"), _course("22222")]
    courses_by_id = {course.id: course for course in courses}
    produced = 0

    def schedule_iter():
        nonlocal produced
        for gap in [1, 2, 3, 4, 5]:
            produced += 1
            yield _schedule(gap)

    exporter = SQLiteScheduleExporter(
        settings=Settings(thresholds=ThresholdSettings(), sorting=_sorting()),
        selected_programs=[PROGRAM],
        chunk_size=2,
        store=SQLiteScheduleStore(tmp_path / "schedules.sqlite3", delete_on_close=False),
    )

    exporter.export_schedules({"FALL - Aleph": schedule_iter()}, courses_by_id)

    view = exporter.schedules_by_period["FALL - Aleph"]
    assert produced == 5
    assert len(view) == 5
    assert [s.assignments["22222"] for s in view[:2]] == [
        date(2026, 1, 10),
        date(2026, 1, 9),
    ]

    exporter.store.close(delete=True)
