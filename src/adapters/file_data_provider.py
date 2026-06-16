"""
Infrastructure Adapter: FileDataProvider
-----------------------------------------
Implements IDataProvider by delegating file reading to three focused readers.

Readers:
    - CourseFileReader
    - ExamPeriodFileReader
    - ProgramSelectorReader

Spec §6.1 caching: parsed domain objects are cached keyed on the SHA-256 of the
three input files (FileHashCache). When the files are unchanged since the last
run, the cached objects are returned instead of re-parsing the raw text. The
cache is purely a performance hint — any miss, corruption, or deserialization
error silently falls back to a fresh parse, so correctness never depends on it.
"""

from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from src.adapters.file_hash_cache import FileHashCache
from src.adapters.readers.course_file_reader import CourseFileReader
from src.adapters.readers.exam_period_file_reader import ExamPeriodFileReader
from src.adapters.readers.program_selector_reader import ProgramSelectorReader
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.interfaces.i_data_provider import IDataProvider

_DEFAULT_CACHE_DIR = Path(".cache")
_DATE_FMT = "%Y-%m-%d"


def _serialize(
    courses: List[Course],
    periods: List[ExamPeriod],
    programs: List[str],
) -> Dict[str, Any]:
    """Convert parsed domain objects into a JSON-safe dict for the cache."""
    return {
        "courses": [
            {
                "id": c.id,
                "name": c.name,
                "instructor": c.instructor,
                "evaluation_type": c.evaluation_type,
                "offerings": [
                    {
                        "program_id": o.program_id,
                        "year": o.year,
                        "semester": o.semester,
                        "requirement": o.requirement,
                        "student_count": o.student_count,
                    }
                    for o in c.offerings
                ],
            }
            for c in courses
        ],
        "periods": [
            {
                "semester": p.semester,
                "moed": p.moed,
                "date_ranges": [
                    [start.strftime(_DATE_FMT), end.strftime(_DATE_FMT)]
                    for start, end in p.date_ranges
                ],
                "excluded_dates": [d.strftime(_DATE_FMT) for d in p.excluded_dates],
            }
            for p in periods
        ],
        "programs": list(programs),
    }


def _deserialize(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Rebuild domain objects from a cached dict (inverse of _serialize)."""
    courses = [
        Course(
            c["id"],
            c["name"],
            c["instructor"],
            c["evaluation_type"],
            [
                CourseOffering(
                    o["program_id"],
                    o["year"],
                    o["semester"],
                    o["requirement"],
                    o["student_count"],
                )
                for o in c["offerings"]
            ],
        )
        for c in payload["courses"]
    ]
    periods = [
        ExamPeriod(
            p["semester"],
            p["moed"],
            [
                (date.fromisoformat(start), date.fromisoformat(end))
                for start, end in p["date_ranges"]
            ],
            {date.fromisoformat(d) for d in p["excluded_dates"]},
        )
        for p in payload["periods"]
    ]
    return {"courses": courses, "periods": periods, "programs": list(payload["programs"])}


class FileDataProvider(IDataProvider):

    def __init__(
        self,
        courses_path: Path,
        periods_path: Path,
        programs_path: Path,
        cache_dir: Path | None = None,
    ):
        self.course_reader = CourseFileReader(courses_path)
        self.exam_period_reader = ExamPeriodFileReader(periods_path)
        self.program_reader = ProgramSelectorReader(programs_path)

        self._cache = FileHashCache(
            cache_dir or _DEFAULT_CACHE_DIR,
            [Path(courses_path), Path(periods_path), Path(programs_path)],
        )
        # Combined cache hit (all files unchanged); None until first lookup.
        self._cached: Dict[str, Any] | None = None
        self._cache_checked = False
        # Per-field memo for the cache-miss path, read lazily and independently
        # so a malformed/missing file only errors when its own getter is called
        # (preserves the original reader-per-getter error semantics).
        self._loaded: Dict[str, Any] = {}

    def _cache_hit(self) -> Dict[str, Any] | None:
        """Return the deserialized combined cache once, if files are unchanged."""
        if not self._cache_checked:
            self._cache_checked = True
            cached = self._cache.load()
            if cached is not None:
                try:
                    self._cached = _deserialize(cached)
                except (KeyError, ValueError, TypeError):
                    self._cached = None  # corrupt/incompatible → fresh parse
        return self._cached

    def _get(self, key: str, reader) -> Any:
        """Serve one slice from the cache on a hit, else read its file lazily."""
        hit = self._cache_hit()
        if hit is not None:
            return hit[key]

        if key not in self._loaded:
            self._loaded[key] = reader()
            self._maybe_save()
        return self._loaded[key]

    def _maybe_save(self) -> None:
        """Persist the combined cache once all three slices have been parsed."""
        if {"courses", "periods", "programs"} <= self._loaded.keys():
            self._cache.save(
                _serialize(
                    self._loaded["courses"],
                    self._loaded["periods"],
                    self._loaded["programs"],
                )
            )

    def get_courses(self) -> List[Course]:
        return self._get("courses", self.course_reader.read)

    def get_exam_periods(self) -> List[ExamPeriod]:
        return self._get("periods", self.exam_period_reader.read)

    def get_selected_programs(self) -> List[str]:
        return self._get("programs", self.program_reader.read)
