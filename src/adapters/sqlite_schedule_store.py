"""
SQLite-backed schedule store
----------------------------
Disk-backed result cache for very large generated schedule sets.

The generator still works lazily.  This adapter only changes what happens to the
items after they are produced: instead of accumulating ``list[Schedule]`` in the
UI, schedules are serialized into a temporary SQLite database and exposed through
an indexable, list-like view.

Why SQLite instead of raw block files?
    * Page reads are cheap: LIMIT / OFFSET.
    * Stable order is explicit through ``position``.
    * Result Ranking can order by precomputed score columns without pulling the
      whole cache back into RAM.
"""

from __future__ import annotations

import os
import pickle
import sqlite3
import tempfile
from collections import OrderedDict
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import overload

from src.domain.course import Course
from src.domain.schedule import Schedule
from src.domain.settings import Settings
from src.domain.sorting import SortCriterion, SortingConfig
from src.domain.sorting_engine import SortingEngine
from src.interfaces.i_output_exporter import IOutputExporter
from src.interfaces.i_schedule_store import IScheduleStore

# Disk is not infinite.  This is intentionally much higher than the RAM cap but
# still bounded so an accidental Auto Load cannot fill the user's drive.
ABSOLUTE_MAX_STORED_SCHEDULES = 1_000_000
_OBJECT_CACHE_MAX_SIZE = 4096

_SCORE_COLUMNS: dict[SortCriterion, str] = {
    SortCriterion.SORT_MIN_DAYS_MANDATORY: "score_min_days_mandatory",
    SortCriterion.SORT_AVG_DAYS_ANY: "score_avg_days_any",
    SortCriterion.SORT_ELECTIVE_COLLISIONS: "score_elective_collisions",
    SortCriterion.SORT_EXAM_PERIOD_SPREAD: "score_exam_period_spread",
    SortCriterion.SORT_MAX_EXAMS_PER_DAY: "score_max_exams_per_day",
}


class StoredScheduleList:
    """A small list-like facade over one period in ``SQLiteScheduleStore``.

    Existing UI code can keep using ``len()``, iteration, indexing and
    ``extend()`` while the Schedule objects themselves live in SQLite.  Iteration
    streams one row at a time; it does not build a full Python list unless caller
    explicitly does ``list(stored_list)``.
    """

    def __init__(
        self,
        store: "SQLiteScheduleStore",
        period_key: str,
        courses: Sequence[Course] | None = None,
        selected_programs: Sequence[str] | None = None,
        sorting: SortingConfig | None = None,
    ) -> None:
        self._store = store
        self._period_key = period_key
        self._courses = list(courses or [])
        self._selected_programs = list(selected_programs or [])
        self._sorting = sorting or SortingConfig()

    @property
    def period_key(self) -> str:
        return self._period_key

    def set_sorting(self, sorting: SortingConfig | None) -> None:
        self._sorting = sorting or SortingConfig()

    def set_scoring_context(
        self,
        courses: Sequence[Course] | None,
        selected_programs: Sequence[str] | None,
    ) -> None:
        self._courses = list(courses or [])
        self._selected_programs = list(selected_programs or [])

    def append(self, schedule: Schedule) -> None:
        self.extend([schedule])

    def extend(self, schedules: Sequence[Schedule]) -> None:
        self._store.append_many(
            self._period_key,
            schedules,
            courses=self._courses,
            selected_programs=self._selected_programs,
        )

    def __len__(self) -> int:
        return self._store.count(self._period_key)

    def __bool__(self) -> bool:
        return len(self) > 0

    @overload
    def __getitem__(self, index: int) -> Schedule:
        ...

    @overload
    def __getitem__(self, index: slice) -> list[Schedule]:
        ...

    def __getitem__(self, index: int | slice) -> Schedule | list[Schedule]:
        if isinstance(index, slice):
            start, stop, step = index.indices(len(self))
            if step != 1:
                return [self[i] for i in range(start, stop, step)]
            return self._store.get_page(
                self._period_key,
                start,
                max(0, stop - start),
                sorting=self._sorting,
            )

        if index < 0:
            index += len(self)
        return self._store.get(self._period_key, index, sorting=self._sorting)

    def __iter__(self) -> Iterator[Schedule]:
        yield from self._store.iter_period(self._period_key, sorting=self._sorting)

    def __eq__(self, other) -> bool:
        if isinstance(other, StoredScheduleList):
            return list(self) == list(other)
        if isinstance(other, list):
            return list(self) == other
        return NotImplemented

    def __repr__(self) -> str:
        return f"StoredScheduleList(period_key={self._period_key!r}, count={len(self)})"


class SQLiteScheduleExporter(IOutputExporter):
    """IOutputExporter implementation that streams generation results to SQLite.

    It consumes schedule iterators in bounded chunks, so even the legacy
    in-process ``DesktopController.generate()`` path no longer needs to build a
    giant list of Schedule objects before returning results.
    """

    def __init__(
        self,
        *,
        settings: Settings | SortingConfig | None = None,
        selected_programs: Sequence[str] | None = None,
        chunk_size: int = 1000,
        store: SQLiteScheduleStore | None = None,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self._settings = settings or SortingConfig()
        self._selected_programs = list(selected_programs or [])
        self._chunk_size = chunk_size
        self.store = store or SQLiteScheduleStore()
        self.schedules_by_period: dict[str, StoredScheduleList] = {}
        self.courses_by_id: dict[str, Course] = {}

    def export_schedules(
        self,
        schedules_by_period: dict[str, Iterator[Schedule]],
        courses_by_id: dict[str, Course],
    ) -> None:
        self.courses_by_id = dict(courses_by_id)
        self.schedules_by_period.clear()
        self.store.clear()

        courses = list(courses_by_id.values())
        for period_key, schedule_iter in schedules_by_period.items():
            chunk: list[Schedule] = []
            for schedule in schedule_iter:
                chunk.append(schedule)
                if len(chunk) >= self._chunk_size:
                    self.store.append_many(
                        period_key,
                        chunk,
                        courses=courses,
                        selected_programs=self._selected_programs,
                    )
                    chunk.clear()
            if chunk:
                self.store.append_many(
                    period_key,
                    chunk,
                    courses=courses,
                    selected_programs=self._selected_programs,
                )

            self.schedules_by_period[period_key] = self.store.as_sequence(
                period_key,
                courses=courses,
                selected_programs=self._selected_programs,
                sorting=(
                    self._settings.sorting
                    if isinstance(self._settings, Settings)
                    else self._settings
                ),
            )


class SQLiteScheduleStore(IScheduleStore):
    """Temporary SQLite-backed cache for generated schedules."""

    def __init__(self, path: Path | str | None = None, *, delete_on_close: bool = True) -> None:
        self._delete_on_close = delete_on_close
        self._closed = False

        if path is None:
            fd, tmp = tempfile.mkstemp(prefix="exam_schedule_cache_", suffix=".sqlite3")
            os.close(fd)
            self.path = Path(tmp)
        else:
            self.path = Path(path)

        self._conn = sqlite3.connect(self.path)
        self._object_cache: OrderedDict[int, Schedule] = OrderedDict()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._create_schema()

    def _create_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period_key TEXT NOT NULL,
                position INTEGER NOT NULL,
                score_min_days_mandatory REAL NOT NULL DEFAULT 0,
                score_avg_days_any REAL NOT NULL DEFAULT 0,
                score_elective_collisions REAL NOT NULL DEFAULT 0,
                score_exam_period_spread REAL NOT NULL DEFAULT 0,
                score_max_exams_per_day REAL NOT NULL DEFAULT 0,
                schedule_blob BLOB NOT NULL,
                UNIQUE(period_key, position)
            );

            CREATE INDEX IF NOT EXISTS idx_schedules_period_position
                ON schedules(period_key, position);
            CREATE INDEX IF NOT EXISTS idx_schedules_period_scores
                ON schedules(
                    period_key,
                    score_min_days_mandatory,
                    score_avg_days_any,
                    score_elective_collisions,
                    score_exam_period_spread,
                    score_max_exams_per_day,
                    position
                );
            """
        )
        self._conn.commit()

    def as_sequence(
        self,
        period_key: str,
        *,
        courses: Sequence[Course] | None = None,
        selected_programs: Sequence[str] | None = None,
        sorting: SortingConfig | None = None,
    ) -> StoredScheduleList:
        return StoredScheduleList(
            self,
            period_key,
            courses=courses,
            selected_programs=selected_programs,
            sorting=sorting,
        )

    def append_many(
        self,
        period_key: str,
        schedules: Sequence[Schedule],
        courses: Sequence[Course] | None = None,
        selected_programs: Sequence[str] | None = None,
    ) -> int:
        self._ensure_open()
        if not schedules:
            return 0

        current_total = self.total_count()
        if current_total >= ABSOLUTE_MAX_STORED_SCHEDULES:
            return 0

        headroom = ABSOLUTE_MAX_STORED_SCHEDULES - current_total
        to_store = list(schedules[:headroom])
        if not to_store:
            return 0

        next_position = self.count(period_key)
        rows = []
        course_list = list(courses or [])
        prog_set = set(selected_programs or [])

        for offset, schedule in enumerate(to_store):
            scores = self._scores(schedule, course_list, prog_set)
            rows.append(
                (
                    period_key,
                    next_position + offset,
                    scores[SortCriterion.SORT_MIN_DAYS_MANDATORY],
                    scores[SortCriterion.SORT_AVG_DAYS_ANY],
                    scores[SortCriterion.SORT_ELECTIVE_COLLISIONS],
                    scores[SortCriterion.SORT_EXAM_PERIOD_SPREAD],
                    scores[SortCriterion.SORT_MAX_EXAMS_PER_DAY],
                    sqlite3.Binary(pickle.dumps(schedule, protocol=pickle.HIGHEST_PROTOCOL)),
                )
            )

        with self._conn:
            self._conn.executemany(
                """
                INSERT INTO schedules (
                    period_key,
                    position,
                    score_min_days_mandatory,
                    score_avg_days_any,
                    score_elective_collisions,
                    score_exam_period_spread,
                    score_max_exams_per_day,
                    schedule_blob
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def replace_period(
        self,
        period_key: str,
        schedules: Sequence[Schedule],
        courses: Sequence[Course] | None = None,
        selected_programs: Sequence[str] | None = None,
    ) -> int:
        self.clear_period(period_key)
        return self.append_many(period_key, schedules, courses, selected_programs)

    def get(self, period_key: str, index: int, sorting: SortingConfig | None = None) -> Schedule:
        if index < 0 or index >= self.count(period_key):
            raise IndexError(f"Schedule index {index} out of range for {period_key}.")
        page = self.get_page(period_key, index, 1, sorting=sorting)
        if not page:
            raise IndexError(f"Schedule index {index} out of range for {period_key}.")
        return page[0]

    def get_page(
        self,
        period_key: str,
        offset: int,
        limit: int,
        sorting: SortingConfig | None = None,
    ) -> list[Schedule]:
        self._ensure_open()
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if limit < 0:
            raise ValueError("limit must be non-negative")
        if limit == 0:
            return []

        order_by = self._order_by(sorting)
        rows = self._conn.execute(
            f"""
            SELECT id, schedule_blob
            FROM schedules
            WHERE period_key = ?
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
            """,
            (period_key, limit, offset),
        ).fetchall()
        return [self._schedule_from_row(row[0], row[1]) for row in rows]

    def iter_period(
        self,
        period_key: str,
        sorting: SortingConfig | None = None,
        page_size: int = 512,
    ) -> Iterator[Schedule]:
        offset = 0
        while True:
            page = self.get_page(period_key, offset, page_size, sorting=sorting)
            if not page:
                return
            yield from page
            offset += len(page)

    def count(self, period_key: str) -> int:
        self._ensure_open()
        row = self._conn.execute(
            "SELECT COUNT(*) FROM schedules WHERE period_key = ?",
            (period_key,),
        ).fetchone()
        return int(row[0])

    def total_count(self) -> int:
        self._ensure_open()
        row = self._conn.execute("SELECT COUNT(*) FROM schedules").fetchone()
        return int(row[0])

    def period_keys(self) -> list[str]:
        self._ensure_open()
        rows = self._conn.execute(
            "SELECT DISTINCT period_key FROM schedules ORDER BY period_key"
        ).fetchall()
        return [row[0] for row in rows]

    def clear_period(self, period_key: str) -> None:
        self._ensure_open()
        with self._conn:
            self._conn.execute("DELETE FROM schedules WHERE period_key = ?", (period_key,))
        self._object_cache.clear()

    def clear(self) -> None:
        self._ensure_open()
        with self._conn:
            self._conn.execute("DELETE FROM schedules")
        self._object_cache.clear()

    def close(self, *, delete: bool | None = None) -> None:
        if self._closed:
            return
        self._conn.close()
        self._closed = True

        should_delete = self._delete_on_close if delete is None else delete
        if should_delete:
            for suffix in ("", "-wal", "-shm"):
                try:
                    self.path.with_name(self.path.name + suffix).unlink(missing_ok=True)
                except OSError:
                    pass

    def _schedule_from_row(self, row_id: int, blob: bytes) -> Schedule:
        cached = self._object_cache.get(row_id)
        if cached is not None:
            self._object_cache.move_to_end(row_id)
            return cached

        schedule = pickle.loads(blob)
        self._object_cache[row_id] = schedule
        if len(self._object_cache) > _OBJECT_CACHE_MAX_SIZE:
            self._object_cache.popitem(last=False)
        return schedule

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("SQLiteScheduleStore is closed.")

    def _scores(
        self,
        schedule: Schedule,
        courses: Sequence[Course],
        prog_set: set[str],
    ) -> dict[SortCriterion, float]:
        return SortingEngine.scores(schedule, list(courses), list(prog_set))

    def _order_by(self, sorting: SortingConfig | None) -> str:
        criteria = (sorting or SortingConfig()).criteria_in_order()
        if not criteria:
            return "position ASC"

        parts = [f"{_SCORE_COLUMNS[criterion]} DESC" for criterion in criteria]
        parts.append("position ASC")
        return ", ".join(parts)

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def __enter__(self) -> "SQLiteScheduleStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
