"""Tests for macOS focus restoration helpers."""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtCore", exc_type=ImportError)

from src.ui import focus_utils


class _FocusWindow:
    def __init__(self, *, visible: bool = True, minimized: bool = False) -> None:
        self.visible = visible
        self.minimized = minimized
        self.normal_calls = 0
        self.raise_calls = 0
        self.activate_calls = 0

    def window(self):
        return self

    def isVisible(self) -> bool:  # noqa: N802 - Qt API name
        return self.visible

    def isMinimized(self) -> bool:  # noqa: N802 - Qt API name
        return self.minimized

    def showNormal(self) -> None:  # noqa: N802 - Qt API name
        self.normal_calls += 1
        self.minimized = False

    def raise_(self) -> None:
        self.raise_calls += 1

    def activateWindow(self) -> None:  # noqa: N802 - Qt API name
        self.activate_calls += 1


@pytest.fixture
def fake_qwidget_type(monkeypatch):
    monkeypatch.setattr(focus_utils, "QWidget", _FocusWindow)
    return _FocusWindow


def test_restore_focus_noops_off_macos(monkeypatch, fake_qwidget_type):
    window = fake_qwidget_type()
    monkeypatch.setattr(focus_utils.sys, "platform", "linux")
    monkeypatch.setattr(
        focus_utils.QTimer,
        "singleShot",
        lambda *_args, **_kwargs: pytest.fail("focus restore should be a no-op"),
    )

    focus_utils.restore_focus_on_macos(window)


def test_restore_focus_schedules_multiple_retries_on_macos(
    monkeypatch,
    fake_qwidget_type,
):
    window = fake_qwidget_type()
    scheduled: list[tuple[int, object]] = []
    monkeypatch.setattr(focus_utils.sys, "platform", "darwin")
    monkeypatch.setattr(
        focus_utils.QTimer,
        "singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )

    focus_utils.restore_focus_on_macos(window)

    assert [delay for delay, _callback in scheduled] == list(
        focus_utils._FOCUS_RETRY_DELAYS_MS
    )


def test_restore_focus_does_not_require_appkit(monkeypatch, fake_qwidget_type):
    window = fake_qwidget_type()
    scheduled = []
    monkeypatch.setattr(focus_utils.sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "AppKit", None)
    monkeypatch.setattr(
        focus_utils.QTimer,
        "singleShot",
        lambda _delay, callback: scheduled.append(callback),
    )

    focus_utils.restore_focus_on_macos(window)
    scheduled[0]()

    assert window.raise_calls == 1
    assert window.activate_calls == 1


def test_restore_focus_raises_existing_visible_window(monkeypatch, fake_qwidget_type):
    window = fake_qwidget_type(minimized=True)
    scheduled = []
    monkeypatch.setattr(focus_utils.sys, "platform", "darwin")
    monkeypatch.setattr(
        focus_utils,
        "_activate_macos_app",
        lambda: None,
    )
    monkeypatch.setattr(
        focus_utils.QTimer,
        "singleShot",
        lambda _delay, callback: scheduled.append(callback),
    )

    focus_utils.restore_focus_on_macos(window)
    scheduled[0]()

    assert window.normal_calls == 1
    assert window.raise_calls == 1
    assert window.activate_calls == 1
