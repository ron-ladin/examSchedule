"""
Calendar cell rendering for the results panel (spec §4.5).

Extracted from results_panel.py to keep that module focused. Contains the
slot-grouping helper, the slot-group type, and the custom table delegate that
paints either a single date cell or side-by-side per-slot columns.
"""

from typing import TypedDict

from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QBrush, QColor, QFont, QPen
from PyQt6.QtWidgets import QStyledItemDelegate

from src.domain.course import Course
from src.domain.schedule import Schedule

# Spec §4.5: exams in different time slots on the same date get distinct colors.
_SLOT_PALETTE = [
    "#DBEAFE",  # blue-100
    "#DCFCE7",  # green-100
    "#FEF9C3",  # yellow-100
    "#FCE7F3",  # pink-100
    "#EDE9FE",  # violet-100
    "#FFEDD5",  # orange-100
]

# Unassigned ("No slot") exams use a neutral gray, never a real slot color, so
# they are not mistaken for an assigned time slot (spec §4.5).
_NO_SLOT_COLOR = "#E5E7EB"  # gray-200

# Spec §4.5: more than this many exams in one slot collapse to a clickable record.
_SLOT_COLLAPSE_THRESHOLD = 3

# Painting geometry (px) — named to avoid magic numbers in the paint methods.
_CELL_PAD = 5
_DATE_LINE_H = 18
_STRIPE_W = 4
_STRIPE_LEFT_OFFSET = 9
_BODY_LINE_H = 13
_COL_GAP = 3
_COL_INNER_LINE_H = 12
_COL_SLOT_LINE_H = 14
_NAME_MAX_CHARS = 14


class SlotGroup(TypedDict):
    """One time-slot's exams within a single calendar date cell (spec §4.5)."""

    slot: str
    has_slot: bool
    course_ids: list[str]
    names: list[str]
    collapsed: bool


def _group_exams_by_slot(
    course_ids: list[str],
    schedule: Schedule,
    courses_by_id: dict[str, Course],
) -> list[SlotGroup]:
    """Group a date's exams by assigned time slot (spec §4.5).

    Returns slot groups ordered chronologically, with exams that have no room
    (and therefore no slot) coming last. Each group carries ``collapsed`` (True
    when more than ``_SLOT_COLLAPSE_THRESHOLD`` exams share the slot — rendered
    as a single clickable record rather than an enumerated list).
    """
    grouped: dict[str, dict] = {}
    for course_id in course_ids:
        assignments = schedule.classroom_assignments.get(course_id, [])
        if assignments:
            label = assignments[0].slot.time.strftime("%H:%M")
            has_slot = True
        else:
            label = "No slot"
            has_slot = False

        group = grouped.setdefault(
            label,
            {"slot": label, "has_slot": has_slot, "course_ids": [], "names": []},
        )
        course = courses_by_id.get(course_id)
        group["course_ids"].append(course_id)
        group["names"].append(course.name if course else course_id)

    # Zero-padded HH:MM labels sort chronologically; "No slot" groups go last.
    ordered = sorted(grouped.values(), key=lambda g: (not g["has_slot"], g["slot"]))
    for group in ordered:
        group["collapsed"] = len(group["course_ids"]) > _SLOT_COLLAPSE_THRESHOLD
    return ordered  # type: ignore[return-value]


class _CalendarCellDelegate(QStyledItemDelegate):
    """Custom painter for schedule calendar cells.

    Dates WITH exams: bold purple header (signals clickability).
    Dates without exams: muted gray header.
    Course lines: name darker, meta line lighter.
    """

    _DATE_FG_EXAM = QColor("#7C3AED")
    _DATE_FG_EMPTY = QColor("#94A3B8")
    _COURSE_FG = QColor("#1F2937")
    _META_FG = QColor("#6B7280")
    _SEP_COLOR = QColor("#BFDBFE")

    def paint(self, painter, option, index) -> None:
        payload = index.data(Qt.ItemDataRole.UserRole)
        text: str = index.data(Qt.ItemDataRole.DisplayRole) or ""
        bg = index.data(Qt.ItemDataRole.BackgroundRole)

        painter.save()

        rect = option.rect
        if bg is not None:
            painter.fillRect(rect, bg)
        else:
            painter.fillRect(rect, Qt.GlobalColor.white)

        if isinstance(payload, dict) and payload.get("groups"):
            self._draw_slot_columns(painter, rect, payload["header"], payload["groups"])
        elif text:
            self._draw_cell(painter, rect, text, bg)

        painter.restore()

    def _draw_cell(self, painter, rect, text: str, bg=None) -> None:
        lines = text.split("\n")
        pad = _CELL_PAD

        has_exams = len(lines) > 2
        left_offset = pad

        if has_exams and bg is not None:
            stripe_color = bg.color() if isinstance(bg, QBrush) else QColor(bg)
            stripe_color.setAlpha(210)
            painter.fillRect(
                QRect(rect.left(), rect.top(), _STRIPE_W, rect.height()),
                stripe_color,
            )
            left_offset = _STRIPE_LEFT_OFFSET

        r = rect.adjusted(left_offset, pad, -pad, -pad)
        y = r.top()

        date_font = QFont(painter.font())
        date_font.setBold(True)
        date_font.setPointSize(9)
        painter.setFont(date_font)
        painter.setPen(self._DATE_FG_EXAM if has_exams else self._DATE_FG_EMPTY)
        painter.drawText(
            QRect(r.left(), y, r.width(), _DATE_LINE_H),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            lines[0],
        )
        y += _DATE_LINE_H

        rest_start = 1
        if len(lines) > 1 and "─" in lines[1]:
            painter.setPen(QPen(self._SEP_COLOR, 1))
            painter.drawLine(r.left(), y + 1, r.left() + min(r.width(), 70), y + 1)
            y += 6
            rest_start = 2

        body_font = QFont(painter.font())
        body_font.setBold(False)
        body_font.setPointSize(8)
        painter.setFont(body_font)

        for line in lines[rest_start:]:
            if y + 12 > r.bottom():
                break

            is_meta = "·" in line
            painter.setPen(self._META_FG if is_meta else self._COURSE_FG)
            painter.drawText(
                QRect(r.left(), y, r.width(), _BODY_LINE_H),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                line.strip(),
            )
            y += _BODY_LINE_H

    def sizeHint(self, option, index) -> QSize:
        text: str = index.data(Qt.ItemDataRole.DisplayRole) or ""
        n = max(1, text.count("\n") + 1)
        return QSize(option.rect.width() or 120, max(52, 24 + n * _BODY_LINE_H))

    def _draw_slot_columns(self, painter, rect, header: str, groups: list) -> None:
        """Paint same-date exams as side-by-side, per-slot colored columns (§4.5)."""
        pad = _CELL_PAD
        r = rect.adjusted(pad, pad, -pad, -pad)

        date_font = QFont(painter.font())
        date_font.setBold(True)
        date_font.setPointSize(9)
        painter.setFont(date_font)
        painter.setPen(self._DATE_FG_EXAM)
        painter.drawText(
            QRect(r.left(), r.top(), r.width(), 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            header,
        )

        body_top = r.top() + _DATE_LINE_H
        columns = len(groups)
        if columns == 0:
            return

        gap = _COL_GAP
        col_w = max(1, (r.width() - gap * (columns - 1)) // columns)

        for i, group in enumerate(groups):
            x = r.left() + i * (col_w + gap)
            col_rect = QRect(x, body_top, col_w, r.bottom() - body_top)
            col_color = (
                _SLOT_PALETTE[i % len(_SLOT_PALETTE)]
                if group.get("has_slot", True)
                else _NO_SLOT_COLOR
            )
            painter.fillRect(col_rect, QColor(col_color))

            inner = col_rect.adjusted(4, 3, -3, -3)
            y = inner.top()

            slot_font = QFont(painter.font())
            slot_font.setBold(True)
            slot_font.setPointSize(8)
            painter.setFont(slot_font)
            painter.setPen(self._COURSE_FG)
            painter.drawText(
                QRect(inner.left(), y, inner.width(), _COL_INNER_LINE_H),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                group["slot"],
            )
            y += _COL_SLOT_LINE_H

            body_font = QFont(painter.font())
            body_font.setBold(False)
            body_font.setPointSize(8)
            painter.setFont(body_font)
            painter.setPen(self._META_FG)

            if group["collapsed"]:
                # §4.5: >3 exams in a slot become one clickable summary record.
                for summary in (f"{len(group['course_ids'])} exams", "(click to view)"):
                    painter.drawText(
                        QRect(inner.left(), y, inner.width(), _COL_INNER_LINE_H),
                        Qt.AlignmentFlag.AlignLeft,
                        summary,
                    )
                    y += _COL_INNER_LINE_H
            else:
                for name in group["names"]:
                    if y + _COL_INNER_LINE_H > inner.bottom():
                        break
                    painter.drawText(
                        QRect(inner.left(), y, inner.width(), _COL_INNER_LINE_H),
                        Qt.AlignmentFlag.AlignLeft,
                        name[:_NAME_MAX_CHARS],
                    )
                    y += _COL_INNER_LINE_H
