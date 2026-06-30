"""Shortlist schedule identity and dialog helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from collections.abc import Sequence

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from src.domain.schedule import Schedule
from src.ui.tokens import (
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_DANGER_BORDER,
    COLOR_DISABLED_BG,
    COLOR_DISABLED_TEXT,
    COLOR_PRIMARY_ACTION,
    COLOR_PRIMARY_BUTTON,
    COLOR_SURFACE_SOFT,
    COLOR_TEXT_DARK,
    COLOR_VIOLET_BORDER,
)

DateAssignmentsFingerprint = tuple[tuple[str, str], ...]
RoomAssignmentsFingerprint = tuple[
    tuple[str, tuple[tuple[str, str, str, int, int, str, int], ...]],
    ...,
]
UnassignedFingerprint = tuple[tuple[str, int], ...]
ScheduleFingerprint = tuple[
    DateAssignmentsFingerprint,
    RoomAssignmentsFingerprint,
    UnassignedFingerprint,
]


@dataclass(frozen=True)
class FavoriteSchedule:
    """A shortlisted schedule candidate.

    Kept as ``FavoriteSchedule`` for backwards-compatible tests/imports, but the
    user-facing UI now calls these entries a shortlist because they are temporary
    candidates for final export, not files saved to disk.
    """

    period_key: str
    signature: ScheduleFingerprint
    label: str


# Clearer alias for new code while keeping the old name import-compatible.
ShortlistedSchedule = FavoriteSchedule


def _date_text(value: date) -> str:
    return value.isoformat()


def schedule_fingerprint(schedule: Schedule) -> ScheduleFingerprint:
    """Stable content identity for a schedule, independent of list position."""
    assignments = tuple(
        sorted(
            (str(course_id), _date_text(exam_date))
            for course_id, exam_date in schedule.assignments.items()
        )
    )
    room_assignments: list[
        tuple[str, tuple[tuple[str, str, str, int, int, str, int], ...]]
    ] = []
    for course_id, assignments_for_course in sorted(schedule.classroom_assignments.items()):
        rows = []
        for assignment in assignments_for_course:
            rows.append(
                (
                    assignment.room.room_id,
                    assignment.slot.time.strftime("%H:%M"),
                    assignment.date.isoformat(),
                    assignment.room.capacity,
                    assignment.students_assigned,
                    assignment.exam.program_id,
                    assignment.proctor_count,
                )
            )
        room_assignments.append((str(course_id), tuple(sorted(rows))))

    unassigned = tuple(
        sorted(
            (str(course_id), int(count))
            for course_id, count in schedule.unassigned_classroom_exams.items()
        )
    )
    return (assignments, tuple(room_assignments), unassigned)


def find_schedule_by_fingerprint(
    schedules: Sequence[Schedule],
    signature: ScheduleFingerprint,
) -> int | None:
    for index, schedule in enumerate(schedules):
        if schedule_fingerprint(schedule) == signature:
            return index
    return None


class FavoritesDialog(QDialog):
    """Dialog for opening, deleting, and exporting shortlisted schedules."""

    openRequested = pyqtSignal(int)
    deleteRequested = pyqtSignal(int)
    exportRequested = pyqtSignal(int)

    def __init__(self, favorites: list[FavoriteSchedule], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Shortlisted Schedule Options")
        self.setMinimumWidth(520)
        self.setStyleSheet(
            f"QDialog {{ background: {COLOR_SURFACE_SOFT}; color: {COLOR_TEXT_DARK}; }}"
            f"QLabel {{ color: {COLOR_PRIMARY_ACTION}; font-size: 14px; font-weight: 800; }}"
            f"QListWidget {{ background: #FFFFFF; border: 1px solid {COLOR_VIOLET_BORDER};"
            f" border-radius: 8px; padding: 6px; color: {COLOR_TEXT_DARK}; }}"
            f"QPushButton {{ background: {COLOR_PRIMARY_BUTTON}; color: #FFFFFF; border: none;"
            " border-radius: 8px; padding: 7px 16px; font-weight: 700; }"
            f"QPushButton:disabled {{ background: {COLOR_DISABLED_BG}; color: {COLOR_DISABLED_TEXT}; }}"
        )

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Shortlisted options for final export"))

        self.favorites_list = QListWidget()
        for favorite in favorites:
            self.favorites_list.addItem(favorite.label)
        if favorites:
            self.favorites_list.setCurrentRow(0)
        layout.addWidget(self.favorites_list)

        actions = QHBoxLayout()
        self.open_btn = QPushButton("Open Selected")
        self.open_btn.setEnabled(bool(favorites))
        self.export_btn = QPushButton("Export Shortlist")
        self.export_btn.setEnabled(bool(favorites))
        self.delete_btn = QPushButton("Remove Selected")
        self.delete_btn.setEnabled(bool(favorites))
        self.delete_btn.setStyleSheet(
            f"background: #FFFFFF; color: {COLOR_DANGER};"
            f" border: 1px solid {COLOR_DANGER_BORDER};"
            " border-radius: 8px; padding: 7px 16px; font-weight: 700;"
        )
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            f"background: #FFFFFF; color: {COLOR_TEXT_DARK}; border: 1px solid {COLOR_BORDER};"
            " border-radius: 8px; padding: 7px 16px; font-weight: 700;"
        )
        actions.addStretch()
        actions.addWidget(self.delete_btn)
        actions.addWidget(close_btn)
        actions.addWidget(self.open_btn)
        actions.addWidget(self.export_btn)
        layout.addLayout(actions)

        self.open_btn.clicked.connect(self._open_selected)
        self.export_btn.clicked.connect(self._export_selected)
        self.delete_btn.clicked.connect(self._delete_selected)
        close_btn.clicked.connect(self.reject)
        self.favorites_list.itemDoubleClicked.connect(lambda _item: self._open_selected())

    def _selected_row(self) -> int:
        return self.favorites_list.currentRow()

    def _open_selected(self) -> None:
        row = self._selected_row()
        if row >= 0:
            self.openRequested.emit(row)

    def _export_selected(self) -> None:
        row = self._selected_row()
        if row >= 0:
            self.exportRequested.emit(row)

    def _delete_selected(self) -> None:
        row = self._selected_row()
        if row >= 0:
            self.deleteRequested.emit(row)

    def remove_row(self, row: int, remaining_count: int) -> None:
        self.favorites_list.takeItem(row)
        has_favorites = remaining_count > 0
        self.open_btn.setEnabled(has_favorites)
        self.export_btn.setEnabled(has_favorites)
        self.delete_btn.setEnabled(has_favorites)
        if has_favorites:
            self.favorites_list.setCurrentRow(min(row, remaining_count - 1))
