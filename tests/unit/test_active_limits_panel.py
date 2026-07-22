import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip(
    "PyQt6.QtWidgets",
    reason="PyQt6 native GUI libraries are not available in this environment.",
    exc_type=ImportError,
)
QApplication = QtWidgets.QApplication

from src.domain.threshold import Criterion, ThresholdEntry, ThresholdSettings
from src.ui.active_limits_panel import ActiveLimitsPanel, format_threshold_entry


def _get_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _settings(*entries: ThresholdEntry) -> ThresholdSettings:
    return ThresholdSettings(entries=tuple(entries))


def test_active_limits_panel_no_active_limits_hidden():
    app = _get_qapp()
    panel = ActiveLimitsPanel()

    panel.show_limits(_settings(), imported_schedule=False)

    assert panel.isVisible() is False
    assert panel.details.text() == ""
    panel.close()
    app.processEvents()


def test_active_limits_panel_one_active_limit_collapses_and_expands():
    app = _get_qapp()
    panel = ActiveLimitsPanel()
    entry = ThresholdEntry(Criterion.MAX_EXAMS_PER_DAY, True, 2)

    panel.show_limits(_settings(entry), imported_schedule=False)

    assert panel.isVisible() is True
    assert panel.toggle.text() == "Active scheduling limits (1)"
    assert format_threshold_entry(entry) in panel.details.text()
    assert panel.details.isVisible() is False

    panel.toggle.setChecked(True)

    assert panel.details.isVisible() is True
    panel.close()
    app.processEvents()


def test_active_limits_panel_multiple_limits_and_new_generation_refresh():
    app = _get_qapp()
    panel = ActiveLimitsPanel()

    panel.show_limits(
        _settings(
            ThresholdEntry(Criterion.MAX_EXAMS_PER_DAY, True, 2),
            ThresholdEntry(Criterion.MAX_ELECTIVE_COLLISIONS, True, 1),
        ),
        imported_schedule=False,
    )

    assert panel.toggle.text() == "Active scheduling limits (2)"
    assert "Exams per day" in panel.details.text()
    assert "Elective collisions" in panel.details.text()

    panel.show_limits(
        _settings(ThresholdEntry(Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS, True, 3)),
        imported_schedule=False,
    )

    assert panel.toggle.text() == "Active scheduling limits (1)"
    assert "Any exam gap" in panel.details.text()
    assert "Elective collisions" not in panel.details.text()
    panel.close()
    app.processEvents()
