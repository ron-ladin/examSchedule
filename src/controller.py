"""
Desktop Controller
-------------------
Thin orchestration layer for the PyQt6 desktop UI.

Responsibilities:
    1. Hold in-memory state: courses, exam periods, selected programmes
    2. Load data from files using existing file readers (replace/append/update modes)
    3. Delegate schedule generation to the engine via the existing AppController
    4. Capture results in a MemoryExporter for display in the UI
    5. Export selected schedules to file via TextFileExporter

Notes:
    - This class is UI-facing. Never import PyQt6 here.
    - Uses InMemoryDataProvider to supply loaded data to the engine.
    - Does NOT modify src/engine/app_controller.py.
"""

import logging
from collections.abc import Iterator
from itertools import islice
from pathlib import Path

from src.adapters.exact_conflict_strategy import ExactConflictStrategy
from src.adapters.in_memory_data_provider import InMemoryDataProvider
from src.adapters.readers.course_file_reader import CourseFileReader
from src.adapters.readers.exam_period_file_reader import ExamPeriodFileReader
from src.adapters.readers.program_selector_reader import ProgramSelectorReader
from src.adapters.text_file_exporter import TextFileExporter
from src.domain.course import Course
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.engine.app_controller import AppController as _EngineController
from src.engine.schedule_generator import ScheduleGenerator
from src.interfaces.i_output_exporter import IOutputExporter

logger = logging.getLogger(__name__)


# Maximum schedules captured per period in the desktop UI.
# Exported so the UI can reference it without hard-coding the literal.
RESULT_CAP: int = 200


# ── Private helper ────────────────────────────────────────────────────────────

class _MemoryExporter(IOutputExporter):
    """Captures generated schedules in memory instead of writing to disk."""

    def __init__(self):
        self.schedules_by_period: dict[str, list[Schedule]] = {}
        self.courses_by_id: dict[str, Course] = {}
        self.truncated_periods: set[str] = set()

    def export_schedules(
        self,
        schedules_by_period: dict[str, Iterator[Schedule]],
        courses_by_id: dict[str, Course],
    ) -> None:
        self.courses_by_id = dict(courses_by_id)
        self.truncated_periods = set()
        for key, schedule_iter in schedules_by_period.items():
            results = list(islice(schedule_iter, RESULT_CAP))
            if next(schedule_iter, None) is not None:
                self.truncated_periods.add(key)
            self.schedules_by_period[key] = results


# ── Public class ──────────────────────────────────────────────────────────────

class DesktopController:
    """
    Manages application state and orchestrates the scheduling pipeline
    for the standalone desktop UI.
    """

    def __init__(self) -> None:
        self._courses: list[Course] = []
        self._exam_periods: list[ExamPeriod] = []
        self._selected_programs: list[str] = []
        self._loaded_program_ids: list[str] = []  # populated by load_programs()

    # ── Data loading ──────────────────────────────────────────────────────────

    def load_courses(self, path: Path, mode: str = "replace") -> int:
        """
        Load courses from a file into memory.
        mode: "replace" | "append" | "update"
        Returns the total number of courses now in memory.
        """
        reader = CourseFileReader(Path(path))
        new_courses = reader.read()
        self._merge_by_key(self._courses, new_courses, mode, key_fn=lambda c: c.id)
        logger.info(
            "load_courses: mode=%s, loaded=%d, total=%d",
            mode, len(new_courses), len(self._courses),
        )
        return len(self._courses)

    def load_programs(self, path: Path) -> int:
        """
        Load programme IDs from a comma-separated programmes file.
        Returns the number of programme IDs loaded.
        """
        reader = ProgramSelectorReader(Path(path))
        self._loaded_program_ids = reader.read()
        logger.info(
            "load_programs: loaded=%d ids=%s",
            len(self._loaded_program_ids),
            self._loaded_program_ids,
        )
        return len(self._loaded_program_ids)

    def load_periods(self, path: Path, mode: str = "replace") -> int:
        """
        Load exam periods from a file into memory.
        mode: "replace" | "append" | "update"
        Returns the total number of periods now in memory.
        """
        reader = ExamPeriodFileReader(Path(path))
        new_periods = reader.read()
        self._merge_by_key(
            self._exam_periods, new_periods, mode, key_fn=lambda p: p.get_key()
        )
        logger.info(
            "load_periods: mode=%s, loaded=%d, total=%d",
            mode, len(new_periods), len(self._exam_periods),
        )
        return len(self._exam_periods)

    def _merge_by_key(
        self, existing: list, new_items: list, mode: str, key_fn
    ) -> None:
        """Apply replace / append / update merge strategy to an in-memory list."""
        if mode == "replace":
            existing.clear()
            existing.extend(new_items)
        elif mode == "append":
            existing.extend(new_items)
        elif mode == "update":
            key_to_idx: dict[str, int] = {
                key_fn(item): i for i, item in enumerate(existing)
            }
            for item in new_items:
                k = key_fn(item)
                if k in key_to_idx:
                    existing[key_to_idx[k]] = item
                else:
                    existing.append(item)
                    key_to_idx[k] = len(existing) - 1
        else:
            raise ValueError(f"Unknown merge mode: '{mode}'. Use replace, append, or update.")

    # ── State queries ─────────────────────────────────────────────────────────

    @property
    def courses(self) -> list[Course]:
        return list(self._courses)

    @property
    def has_courses(self) -> bool:
        return bool(self._courses)

    @property
    def has_periods(self) -> bool:
        return bool(self._exam_periods)

    def get_programme_ids(self) -> list[str]:
        """
        Return programme IDs to display in the sidebar list.
        Prefers the explicitly loaded programs file; falls back to IDs
        derived from course offerings if no programs file has been loaded.
        """
        if self._loaded_program_ids:
            return list(self._loaded_program_ids)
        ids: set = set()
        for course in self._courses:
            for offering in course.offerings:
                ids.add(offering.program_id)
        return sorted(ids)

    def get_exam_periods(self) -> list[ExamPeriod]:
        return list(self._exam_periods)

    def get_courses_by_programme(self, program_id: str) -> list[Course]:
        """Return all courses that have at least one offering for the given programme."""
        return [
            c for c in self._courses
            if any(o.program_id == program_id for o in c.offerings)
        ]

    # ── State mutation ────────────────────────────────────────────────────────

    def set_selected_programs(self, program_ids: list[str]) -> None:
        """Set which programmes to schedule (max 5)."""
        if len(program_ids) > 5:
            raise ValueError("Maximum 5 programmes may be selected.")
        self._selected_programs = list(program_ids)

    def update_exam_periods(self, periods: list[ExamPeriod]) -> None:
        """Replace in-memory periods with edited versions from the UI."""
        self._exam_periods = list(periods)

    # ── Generation ────────────────────────────────────────────────────────────

    def generate(self) -> tuple[dict[str, list[Schedule]], dict[str, Course], set[str]]:
        """
        Run the CSP engine and return
        (schedules_by_period, courses_by_id, truncated_periods).

        schedules_by_period  — dict mapping period key → list of Schedule (capped at RESULT_CAP)
        courses_by_id        — dict mapping course ID → Course
        truncated_periods    — set of period keys where results were capped at RESULT_CAP

        Raises ValueError if preconditions are not met (no programmes selected,
        no courses loaded, or no exam periods loaded).
        """
        if not self._selected_programs:
            raise ValueError("No programmes selected. Select at least one programme.")
        if not self._courses:
            raise ValueError("No courses loaded. Load a courses file first.")
        if not self._exam_periods:
            raise ValueError("No exam periods loaded. Load a periods file first.")

        data_provider = InMemoryDataProvider(
            courses=self._courses,
            exam_periods=self._exam_periods,
            selected_programs=self._selected_programs,
        )
        conflict_strategy = ExactConflictStrategy(selected_programs=self._selected_programs)
        generator = ScheduleGenerator(conflict_strategy=conflict_strategy)
        memory_exporter = _MemoryExporter()

        engine = _EngineController(
            data_provider=data_provider,
            exporter=memory_exporter,
            generator=generator,
            selected_programs=self._selected_programs,
        )
        engine.run()

        return (
            memory_exporter.schedules_by_period,
            memory_exporter.courses_by_id,
            memory_exporter.truncated_periods,
        )

    # ── Export ────────────────────────────────────────────────────────────────

    def export(
        self,
        schedules_by_period: dict[str, list[Schedule]],
        output_path: Path,
    ) -> None:
        """Write selected schedules to a text file using TextFileExporter."""
        courses_by_id = {c.id: c for c in self._courses}
        exporter = TextFileExporter(output_path=Path(output_path))
        exporter.export_schedules(schedules_by_period, courses_by_id)
        logger.info("Exported schedules to %s", output_path)
