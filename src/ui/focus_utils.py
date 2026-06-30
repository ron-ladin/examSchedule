"""macOS window-focus restoration after starting worker processes.

The forkserver context prevents direct GUI-process forks, but macOS can still
briefly treat worker/bootstrap Python processes as foreground applications. This
helper retries reactivation of the existing visible Qt window without blocking
or opening any new UI.
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget

_FOCUS_RETRY_DELAYS_MS = (0, 100, 250, 500, 900, 1400)


def _activate_macos_app() -> None:
    """Ask AppKit to foreground this process when PyObjC is available."""
    if sys.platform != "darwin":
        return

    try:
        from AppKit import NSApplication  # type: ignore

        app = NSApplication.sharedApplication()
        app.activateIgnoringOtherApps_(True)
    except Exception:
        # PyObjC/AppKit is optional; Qt activation below is still safe.
        return


def restore_focus_on_macos(widget: QWidget | None) -> None:
    """Retry reactivation of *widget*'s visible top-level window on macOS."""
    if sys.platform != "darwin":
        return

    if not isinstance(widget, QWidget):
        return

    window = widget.window()
    if window is None:
        return

    def restore() -> None:
        if not window.isVisible():
            return

        _activate_macos_app()

        if window.isMinimized():
            window.showNormal()

        window.raise_()
        window.activateWindow()

    for delay_ms in _FOCUS_RETRY_DELAYS_MS:
        QTimer.singleShot(delay_ms, restore)
