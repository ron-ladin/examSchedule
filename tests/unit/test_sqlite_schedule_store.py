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


def test_append_many_does_not_consult_legacy_total_count_cap(monkeypatch, tmp_path):
    store = SQLiteScheduleStore(tmp_path / "schedules.sqlite3", delete_on_close=False)
    original_total_count = store.total_count

    def fail_if_called():
        raise AssertionError("append_many must not enforce a total row-count cap")

    monkeypatch.setattr(store, "total_count", fail_if_called)

    try:
        stored = store.append_many("FALL - Aleph", [_schedule(1)])

        assert stored == 1
        assert store.count("FALL - Aleph") == 1
        assert original_total_count() == 1
    finally:
        store.close(delete=True)


def test_count_cache_updates_without_repeated_sql_count_queries(tmp_path):
    store = SQLiteScheduleStore(tmp_path / "schedules.sqlite3", delete_on_close=False)

    try:
        store.append_many("FALL - Aleph", [_schedule(1), _schedule(2)])
        store.append_many("SPRING - Bet", [_schedule(3)])

        assert store.count("FALL - Aleph") == 2
        assert store.count("SPRING - Bet") == 1
        assert store.total_count() == 3

        statements: list[str] = []
        store._conn.set_trace_callback(statements.append)
        view = store.as_sequence("FALL - Aleph")
        for _ in range(3):
            assert len(view) == 2
            assert store.total_count() == 3
        store._conn.set_trace_callback(None)

        assert not any("COUNT(" in statement.upper() for statement in statements)

        store.clear_period("FALL - Aleph")
        assert store.count("FALL - Aleph") == 0
        assert store.count("SPRING - Bet") == 1
        assert store.total_count() == 1

        store.clear()
        assert store.count("SPRING - Bet") == 0
        assert store.total_count() == 0
    finally:
        store._conn.set_trace_callback(None)
        store.close(delete=True)


def test_get_page_uses_position_lookup_without_sorting(tmp_path):
    store = SQLiteScheduleStore(tmp_path / "schedules.sqlite3", delete_on_close=False)
    store.append_many(
        "FALL - Aleph",
        [_schedule(1), _schedule(2), _schedule(3), _schedule(4)],
    )
    view = store.as_sequence("FALL - Aleph")
    statements: list[str] = []
    store._conn.set_trace_callback(statements.append)

    try:
        assert view[2] == _schedule(3)

        sql = "\n".join(statements).upper()
        assert "POSITION = 2" in sql
        assert "OFFSET" not in sql
    finally:
        store._conn.set_trace_callback(None)
        store.close(delete=True)


def test_get_page_uses_position_range_for_unsorted_slices(tmp_path):
    store = SQLiteScheduleStore(tmp_path / "schedules.sqlite3", delete_on_close=False)
    schedules = [_schedule(1), _schedule(2), _schedule(3), _schedule(4)]
    store.append_many("FALL - Aleph", schedules)
    view = store.as_sequence("FALL - Aleph")
    statements: list[str] = []
    store._conn.set_trace_callback(statements.append)

    try:
        assert view[1:3] == schedules[1:3]

        sql = "\n".join(statements).upper()
        assert "POSITION >= 1" in sql
        assert "POSITION < 3" in sql
        assert "OFFSET" not in sql
    finally:
        store._conn.set_trace_callback(None)
        store.close(delete=True)


def test_get_page_keeps_order_by_offset_when_sorting_is_active(tmp_path):
    store = SQLiteScheduleStore(tmp_path / "schedules.sqlite3", delete_on_close=False)
    courses = [_course("11111"), _course("22222")]
    store.append_many(
        "FALL - Aleph",
        [_schedule(1), _schedule(2), _schedule(3)],
        courses=courses,
        selected_programs=[PROGRAM],
    )
    view = store.as_sequence(
        "FALL - Aleph",
        courses=courses,
        selected_programs=[PROGRAM],
        sorting=_sorting(),
    )
    statements: list[str] = []
    store._conn.set_trace_callback(statements.append)

    try:
        _ = view[1]

        sql = "\n".join(statements).upper()
        assert "ORDER BY" in sql
        assert "OFFSET 1" in sql
    finally:
        store._conn.set_trace_callback(None)
        store.close(delete=True)


def test_explain_order_query_reports_index_for_position_order(tmp_path):
    store = SQLiteScheduleStore(tmp_path / "schedules.sqlite3", delete_on_close=False)
    store.append_many("FALL - Aleph", [_schedule(1), _schedule(2)])

    try:
        position_plan = " ".join(
            store.explain_order_query("FALL - Aleph", SortingConfig())
        )
        sorted_plan = " ".join(store.explain_order_query("FALL - Aleph", _sorting()))

        assert "idx_schedules_period_position" in position_plan
        assert "schedules" in sorted_plan.lower()
    finally:
        store.close(delete=True)


def test_close_delete_removes_main_wal_and_shm_and_is_idempotent(tmp_path):
    db_path = tmp_path / "schedules.sqlite3"
    store = SQLiteScheduleStore(db_path, delete_on_close=False)
    store.append_many("FALL - Aleph", [_schedule(1)])
    wal_path = db_path.with_name(db_path.name + "-wal")
    shm_path = db_path.with_name(db_path.name + "-shm")
    store.close(delete=False)
    wal_path.write_bytes(b"wal")
    shm_path.write_bytes(b"shm")

    store.close(delete=True)
    store.close(delete=True)

    assert not db_path.exists()
    assert not wal_path.exists()
    assert not shm_path.exists()
