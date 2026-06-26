import os
import queue
import sys
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip(
    "PyQt6.QtWidgets",
    reason="PyQt6 native GUI libraries are not available in this environment.",
    exc_type=ImportError,
)

from src.controller import DesktopController
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.engine import ranking_worker
from src.engine.ranking_worker import RankingWorkerResult, _put_ranking_result
from src.ui.results_panel import _ResultsPanel

QApplication = QtWidgets.QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _course() -> Course:
    return Course(
        id="C1",
        name="Algorithms",
        instructor="Dr. Ada",
        evaluation_type="Exam",
        offerings=[CourseOffering("83101", 1, "FALL", "Obligatory")],
    )


def _schedule() -> Schedule:
    period = ExamPeriod(
        "FALL",
        "Aleph",
        [(date(2026, 1, 1), date(2026, 1, 31))],
    )
    return Schedule(period, {"C1": date(2026, 1, 5)})


def _panel(qapp) -> _ResultsPanel:
    controller = DesktopController()
    controller._courses = [_course()]
    controller._last_results = {"FALL - Aleph": [_schedule()]}
    controller.clear_results_stale()
    panel = _ResultsPanel(controller)
    qapp.processEvents()
    return panel


class _ExitedProcess:
    exitcode = 0

    def __init__(self):
        self.join_calls = 0
        self.terminate_called = False
        self.kill_called = False

    def is_alive(self):
        return False

    def join(self, timeout=0):
        self.join_calls += 1

    def terminate(self):
        self.terminate_called = True

    def kill(self):
        self.kill_called = True


class _LiveProcess:
    exitcode = None

    def __init__(self):
        self.join_calls = 0
        self.terminate_called = False
        self.kill_called = False

    def is_alive(self):
        return True

    def join(self, timeout=0):
        self.join_calls += 1

    def terminate(self):
        self.terminate_called = True

    def kill(self):
        self.kill_called = True


def test_poll_ranking_worker_waits_when_exited_process_queue_is_temporarily_empty(qapp):
    panel = _panel(qapp)
    messages = []
    panel._show_message = lambda *args, **kwargs: messages.append(args)
    panel._ranking_queue = queue.Queue()
    panel._ranking_proc = _ExitedProcess()
    panel._set_ranking_busy(True)

    try:
        panel._poll_ranking_worker()

        assert messages == []
        assert panel._ranking_proc is not None
        assert panel._ranking_empty_after_exit_ticks == 1
        assert panel._ranking_btn.isEnabled() is False
    finally:
        panel._cleanup_ranking_worker(terminate=True)
        panel.close()


def test_cleanup_ranking_worker_without_terminate_does_not_kill_live_process(qapp):
    panel = _panel(qapp)
    proc = _LiveProcess()
    panel._ranking_proc = proc

    try:
        panel._cleanup_ranking_worker(terminate=False)

        assert proc.join_calls == 0
        assert proc.terminate_called is False
        assert proc.kill_called is False
        assert panel._ranking_proc is None
    finally:
        panel.close()


def test_put_ranking_result_serializes_before_queue_put(monkeypatch):
    messages = queue.Queue()
    result = RankingWorkerResult.ok()
    serialized = []
    real_dumps = ranking_worker.pickle.dumps

    def spy_dumps(message):
        serialized.append(message)
        return real_dumps(message)

    monkeypatch.setattr(ranking_worker.pickle, "dumps", spy_dumps)

    _put_ranking_result(messages, result)

    assert serialized == [result]
    assert messages.get_nowait() == result
