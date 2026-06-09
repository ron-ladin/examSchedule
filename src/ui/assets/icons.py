"""Painted vector icon widgets — platform-safe replacements for emoji in section headers."""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget


class _BaseIcon(QWidget):
    def __init__(self, size: int = 15, color: str = "#2563EB", parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw(p, float(self.width()))
        p.end()

    def _draw(self, p: QPainter, s: float) -> None:
        raise NotImplementedError


class BookIcon(_BaseIcon):
    """Open two-page book."""

    def _draw(self, p: QPainter, s: float) -> None:
        pen = QPen(self._color, max(1.0, s * 0.09))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(s*0.04, s*0.08, s*0.92, s*0.84), s*0.08, s*0.08)
        p.drawLine(int(s*0.50), int(s*0.08), int(s*0.50), int(s*0.92))
        for frac in (0.30, 0.47, 0.64):
            p.drawLine(int(s*0.10), int(s*frac), int(s*0.43), int(s*frac))
        for frac in (0.30, 0.47, 0.64):
            p.drawLine(int(s*0.57), int(s*frac), int(s*0.90), int(s*frac))


class CalendarIcon(_BaseIcon):
    """Mini calendar with header bar and date dots."""

    def _draw(self, p: QPainter, s: float) -> None:
        pen = QPen(self._color, max(1.0, s * 0.09))
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(s*0.08, s*0.15, s*0.84, s*0.77), s*0.10, s*0.10)
        p.setBrush(self._color)
        p.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.addRoundedRect(QRectF(s*0.08, s*0.15, s*0.84, s*0.27), s*0.10, s*0.10)
        path.addRect(QRectF(s*0.08, s*0.29, s*0.84, s*0.13))
        p.drawPath(path)
        p.setPen(QPen(self._color, max(1.0, s * 0.09)))
        p.drawLine(int(s*0.30), int(s*0.07), int(s*0.30), int(s*0.22))
        p.drawLine(int(s*0.70), int(s*0.07), int(s*0.70), int(s*0.22))
        p.setBrush(self._color)
        p.setPen(Qt.PenStyle.NoPen)
        r = s * 0.08
        for ry in (0.58, 0.75):
            for rx in (0.25, 0.50, 0.75):
                p.drawEllipse(QRectF(s*rx - r, s*ry - r, 2*r, 2*r))


class GraduationIcon(_BaseIcon):
    """Mortarboard / graduation cap."""

    def _draw(self, p: QPainter, s: float) -> None:
        pen = QPen(self._color, max(1.0, s * 0.09))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setBrush(self._color)
        p.setPen(pen)
        diamond = QPainterPath()
        diamond.moveTo(s*0.50, s*0.05)
        diamond.lineTo(s*0.94, s*0.32)
        diamond.lineTo(s*0.50, s*0.50)
        diamond.lineTo(s*0.06, s*0.32)
        diamond.closeSubpath()
        p.drawPath(diamond)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(pen)
        p.drawLine(int(s*0.28), int(s*0.44), int(s*0.28), int(s*0.74))
        p.drawLine(int(s*0.72), int(s*0.44), int(s*0.72), int(s*0.74))
        p.drawArc(int(s*0.18), int(s*0.58), int(s*0.20), int(s*0.30), 180*16, -180*16)
        p.drawArc(int(s*0.62), int(s*0.58), int(s*0.20), int(s*0.30), 0*16, -180*16)
        p.drawLine(int(s*0.50), int(s*0.50), int(s*0.50), int(s*0.82))
        p.drawLine(int(s*0.85), int(s*0.32), int(s*0.85), int(s*0.62))
        p.drawEllipse(QRectF(s*0.79, s*0.61, s*0.12, s*0.12))
