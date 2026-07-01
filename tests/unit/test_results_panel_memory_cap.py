import os
import queue
import sys
from datetime import date
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip(
    "PyQt6.QtWidgets",
    reason="PyQt6 native GUI libraries are not available in this environment.",
    exc_type=ImportError,
)

from src.controller import DesktopController
from src.domain.exam_period import ExamPeriod
from src.domain.generation_result import GenerationResult
from src.domain.schedule import Schedule
from src.engine.generation_workers import ABSOLUTE_MAX_IN_MEMORY_SCHEDULES
from src.ui.results_panel import _ResultsPanel

QApplication = QtWidgets.QApplication
QPushButton = QtWidgets.QPushButton


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _schedule(course_id: str, day: int) -> Schedule:
    period = ExamPeriod(
        "FALL",
        "Aleph",
        [(date(2026, 1, 1), date(2026, 1, 31))],
    )
    return Schedule(period, {course_id: date(2026, 1, day)})


def _in_memory_panel(qapp) -> tuple[_ResultsPanel, str]:
    period_key = "FALL - Aleph"
    panel = _ResultsPanel(DesktopController())
    panel._schedule_store = None
    panel._is_imported_schedule = False
    panel._schedules_by_period = {period_key: [_schedule("C0", 1)]}
    panel._period_indices = {period_key: 0}
    panel._truncated_periods = {period_key}
    qapp.processEvents()
    return panel, period_key


def test_in_memory_schedule_cap_is_disabled():
    assert ABSOLUTE_MAX_IN_MEMORY_SCHEDULES is None


def test_is_at_memory_cap_returns_false_when_cap_is_disabled(monkeypatch, qapp):
    panel, _period_key = _in_memory_panel(qapp)

    def fail_if_counted():
        raise AssertionError("disabled memory cap must not calculate in-memory count")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(panel, "total_in_memory_schedule_count", fail_if_counted)
            assert panel.is_at_memory_cap() is False
    finally:
        panel.close()


def test_append_loaded_schedules_does_not_truncate_without_memory_cap(
    monkeypatch,
    caplog,
    qapp,
):
    panel, period_key = _in_memory_panel(qapp)
    extra = [_schedule(f"C{i}", i + 2) for i in range(5)]

    def fail_if_counted():
        raise AssertionError("disabled memory cap must not calculate headroom")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(panel, "total_in_memory_schedule_count", fail_if_counted)
            panel.append_loaded_schedules(period_key, extra)

        assert len(panel.get_schedules(period_key)) == 6
        assert all(
            "In-memory schedule cap" not in record.getMessage()
            for record in caplog.records
        )
    finally:
        panel.close()


def test_load_more_is_not_disabled_by_memory_cap_state(monkeypatch, qapp):
    panel, period_key = _in_memory_panel(qapp)
    try:
        panel._lm.cardRefreshRequested.disconnect()
    except TypeError:
        pass

    load_more_btn = QPushButton()
    panel._cards[period_key] = SimpleNamespace(
        load_more_btn=load_more_btn,
        auto_date_btn=None,
        auto_variant_btn=None,
    )
    panel.controller.set_has_more_for_period(period_key, True)

    result_queue = queue.Queue()
    result_queue.put(
        GenerationResult.ok(
            {period_key: [_schedule("C1", 2)]},
            {},
            {period_key},
        )
    )

    panel._lm.queues[period_key] = result_queue
    panel._lm.modes[period_key] = "dates"
    panel._lm.ticks[period_key] = 0

    try:
        with monkeypatch.context() as patch:
            patch.setattr(panel, "is_at_memory_cap", lambda: True)
            panel._lm._poll_load_more_inner(period_key)

        assert len(panel.get_schedules(period_key)) == 2
        assert load_more_btn.isEnabled() is True
        assert "Memory limit" not in load_more_btn.text()
        assert "more date options" in load_more_btn.text()
        assert panel.controller.has_more_schedules(period_key) is True
    finally:
        panel.close()
