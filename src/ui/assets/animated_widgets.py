"""Animated background widgets: header with floating orbs + empty-state placeholder."""
import math

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class AnimatedHeader(QWidget):
    """App header bar with subtle animated orbs in the right margin.

    Callers set up the content layout after construction:
        header = AnimatedHeader(parent)
        layout = QHBoxLayout(header)
        layout.addWidget(...)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("appHeader")
        self.setFixedHeight(54)
        self._phase = 0.0
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(50)  # 20 fps — smooth yet lightweight

    def _tick(self) -> None:
        self._phase = (self._phase + 1.5) % 360.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        phase_r = math.radians(self._phase)

        # White base
        p.fillRect(0, 0, w, h, QColor("#FFFFFF"))

        # Soft animated orbs — right 35 % of header only
        _ORBS = [
            (0.73, 0.50, 58, 38, "#BFDBFE"),
            (0.87, 0.28, 42, 30, "#C7D2FE"),
            (0.96, 0.72, 36, 24, "#DDD6FE"),
        ]
        p.setPen(Qt.PenStyle.NoPen)
        for ox, oy, radius, base_alpha, hex_color in _ORBS:
            c = QColor(hex_color)
            # Breathing effect: alpha oscillates ±30 %
            alpha = int(base_alpha * (0.70 + 0.30 * math.sin(phase_r + ox * 4.0)))
            c.setAlpha(alpha)
            x = int(w * ox + math.cos(phase_r + ox * 5.0) * 7)
            y = int(h * oy + math.sin(phase_r + oy * 3.0) * 4)
            p.setBrush(QBrush(c))
            p.drawEllipse(x - radius, y - radius, radius * 2, radius * 2)

        # Bottom separator
        p.setPen(QPen(QColor("#E2E8F0"), 1))
        p.drawLine(0, h - 1, w, h - 1)
        p.end()


class AnimatedPlaceholder(QWidget):
    """Empty-state widget: floating pastel orbs behind a centred message label."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(50)

        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("font-size: 13px; color: #94A3B8; background: transparent;")

        lay = QVBoxLayout(self)
        lay.addStretch()
        lay.addWidget(lbl)
        lay.addStretch()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.6) % 360.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        phase_r = math.radians(self._phase)

        p.fillRect(0, 0, w, h, QColor("#FFFFFF"))

        # Large soft orbs that drift slowly — low saturation pastels
        _ORBS = [
            (0.18, 0.28, 100, "#DBEAFE"),
            (0.72, 0.65, 120, "#E0E7FF"),
            (0.50, 0.18, 75,  "#EDE9FE"),
            (0.85, 0.40, 85,  "#BAE6FD"),
            (0.12, 0.75, 110, "#E0F2FE"),
        ]
        p.setPen(Qt.PenStyle.NoPen)
        for ox, oy, radius, hex_color in _ORBS:
            c = QColor(hex_color)
            x = int(w * ox + math.cos(phase_r + ox * 6.0) * 14)
            y = int(h * oy + math.sin(phase_r + oy * 4.0) * 10)
            p.setBrush(QBrush(c))
            p.drawEllipse(x - radius, y - radius, radius * 2, radius * 2)
        p.end()
