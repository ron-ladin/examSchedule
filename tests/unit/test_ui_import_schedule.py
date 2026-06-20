"""
UI tests: ConfigScreen schedule import
--------------------------------------
Focus on the view-layer behaviour of the "Load Schedule" action:

  - oversized files are rejected BEFORE parsing (50 MB cap)
  - a failing Path.stat() (PermissionError / OSError) shows a friendly error
    instead of crashing, and the file is never parsed
  - a successful import delegates parsing to the controller and emits a
    read-only result tuple
"""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip(
    "PyQt6.QtWidgets",
    reason="PyQt6 native GUI libraries are not available in this environment.",
    exc_type=ImportError,
)

QApplication = QtWidgets.QApplication
QFileDialog = QtWidgets.QFileDialog
QMessageBox = QtWidgets.QMessageBox

from src.controller import DesktopController
from src.ui.config_screen import ConfigScreen


_IMPORT_SAMPLE = """\
Schedule #1:
  [FALL - Aleph]
  - Physics 1 | Course ID: 83102 | Date: 29-01-2026 | Instructor: Prof. A

"""


def _get_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _patch_open_dialog(monkeypatch, path: Path) -> None:
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_a, **_k: (str(path), "Text files (*.txt)"),
    )


def _silence_message_boxes(monkeypatch) -> dict[str, int]:
    counts = {"warning": 0, "critical": 0}

    def _warning(*_a, **_k):
        counts["warning"] += 1
        return QMessageBox.StandardButton.Ok

    def _critical(*_a, **_k):
        counts["critical"] += 1
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", _warning)
    monkeypatch.setattr(QMessageBox, "critical", _critical)
    return counts


def test_oversized_file_rejected_before_parsing(tmp_path, monkeypatch):
    app = _get_qapp()
    assert app is not None
    screen = ConfigScreen(DesktopController())

    big = tmp_path / "huge.txt"
    big.write_text(_IMPORT_SAMPLE, encoding="utf-8")

    _patch_open_dialog(monkeypatch, big)
    counts = _silence_message_boxes(monkeypatch)

    # Report a size over the 50 MB cap without writing a real 50 MB file.
    real_stat = Path.stat

    class _FakeStat:
        st_size = 51 * 1024 * 1024

    monkeypatch.setattr(
        Path,
        "stat",
        lambda self, *a, **k: _FakeStat() if self == big else real_stat(self, *a, **k),
    )

    # The controller must never be asked to parse an oversized file.
    parsed: list[Path] = []
    monkeypatch.setattr(
        screen._controller,
        "import_schedule",
        lambda path: parsed.append(path),
    )

    screen._import_schedule()

    assert parsed == []
    assert counts["warning"] == 1


@pytest.mark.parametrize("error", [PermissionError, OSError])
def test_stat_failure_does_not_crash(tmp_path, monkeypatch, error):
    app = _get_qapp()
    assert app is not None
    screen = ConfigScreen(DesktopController())

    target = tmp_path / "schedule.txt"
    target.write_text(_IMPORT_SAMPLE, encoding="utf-8")

    _patch_open_dialog(monkeypatch, target)
    counts = _silence_message_boxes(monkeypatch)

    def _boom(self, *a, **k):
        raise error("stat failed")

    monkeypatch.setattr(Path, "stat", _boom)

    parsed: list[Path] = []
    monkeypatch.setattr(
        screen._controller,
        "import_schedule",
        lambda path: parsed.append(path),
    )

    # Must not raise, must not parse, must surface a friendly error dialog.
    screen._import_schedule()

    assert parsed == []
    assert counts["critical"] == 1


def test_successful_import_emits_read_only_result(tmp_path, monkeypatch):
    app = _get_qapp()
    assert app is not None
    screen = ConfigScreen(DesktopController())

    target = tmp_path / "schedule.txt"
    target.write_text(_IMPORT_SAMPLE, encoding="utf-8")

    _patch_open_dialog(monkeypatch, target)
    _silence_message_boxes(monkeypatch)

    emitted: list[tuple] = []
    screen.schedule_generated.connect(emitted.append)

    screen._import_schedule()

    assert len(emitted) == 1
    result_tuple = emitted[0]
    # Read-only flag is the 6th element.
    assert result_tuple[5] is True
    assert "FALL - Aleph" in result_tuple[1]
    assert screen._controller.read_only_import is True
