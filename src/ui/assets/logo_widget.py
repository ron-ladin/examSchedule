"""Custom painted Syncacademic logo widget."""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

# Palette
_COLOR_SLATE_BLUE = QColor("#6B98B5")
_COLOR_STEEL_GRAY = QColor("#9BADB6")

# Logical canvas size (all geometry defined at this scale)
_CANVAS = 40.0


def _ring_path(cx: float, cy: float, outer: float, inner: float, radius: float) -> QPainterPath:
    """Return a hollow rounded-square ring path centred at (cx, cy).

    The ring is the area inside the outer rounded-rect minus the inner one,
    achieved with even-odd fill.
    """
    half_o = outer / 2.0
    half_i = inner / 2.0

    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    path.addRoundedRect(QRectF(cx - half_o, cy - half_o, outer, outer), radius, radius)
    path.addRoundedRect(QRectF(cx - half_i, cy - half_i, inner, inner), radius * 0.55, radius * 0.55)
    return path


class LogoWidget(QWidget):
    """Paints the Syncacademic two-ring interlocked logo."""

    def __init__(self, size: int = 36, parent=None) -> None:
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        scale = self._size / _CANVAS
        painter.scale(scale, scale)

        # --- Shape dimensions (at 40×40 logical units) ---
        outer_side = 18.0   # outer edge of the ring square
        stroke = 4.5        # ring thickness → inner = outer - 2*stroke
        inner_side = outer_side - 2 * stroke
        corner_r = 4.5      # corner radius for outer rect

        # Centre of each ring (offset to create the chain-link overlap)
        cx1, cy1 = 16.0, 16.0   # left / upper ring
        cx2, cy2 = 24.0, 24.0   # right / lower ring

        # --- Ring 1: slate-blue, rotated 45° around its own centre ---
        painter.save()
        painter.translate(cx1, cy1)
        painter.rotate(45.0)
        painter.translate(-cx1, -cy1)

        ring1 = _ring_path(cx1, cy1, outer_side, inner_side, corner_r)
        painter.fillPath(ring1, _COLOR_SLATE_BLUE)
        painter.restore()

        # --- Ring 2: steel-gray, also rotated 45°, drawn partially on top ---
        painter.save()
        painter.translate(cx2, cy2)
        painter.rotate(45.0)
        painter.translate(-cx2, -cy2)

        ring2 = _ring_path(cx2, cy2, outer_side, inner_side, corner_r)
        painter.fillPath(ring2, _COLOR_STEEL_GRAY)
        painter.restore()

        painter.end()
