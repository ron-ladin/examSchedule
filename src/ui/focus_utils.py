"""macOS window-focus restoration after starting worker processes.

Belt-and-suspenders for the macOS focus-steal symptom. The forkserver context
(see ``src.engine.mp_context``) prevents per-worker focus theft, but the
forkserver's own one-time bootstrap still execs a process that can briefly steal
focus on the very first worker. This helper re-raises the app window right after
a worker starts so any residual blip is corrected. No-op off macOS.
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget

_FOCUS_RETRY_DELAY_MS = 250


def restore_focus_on_macos(widget: QWidget | None) -> None:
    """Re-raise and reactivate *widget*'s top-level window, on macOS only.

    Schedules two attempts (immediately and after a short delay) because the
    focus loss can land slightly after the worker starts. Safe to call with a
    hidden or ``None`` widget — it simply does nothing.
    """
    if sys.platform != "darwin":
        return
    if not isinstance(widget, QWidget):
        return

    window = widget.window()
    if window is None or not window.isVisible():
        return

    def restore() -> None:
        window.showNormal()
        window.raise_()
        window.activateWindow()

    QTimer.singleShot(0, restore)
    QTimer.singleShot(_FOCUS_RETRY_DELAY_MS, restore)
