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

from src.adapters.sqlite_schedule_store import SQLiteScheduleStore
from src.controller import DesktopController
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.schedule import Schedule
from src.domain.sorting import SortCriterion, SortingConfig
from src.engine.ranking_worker import RankingWorkerResult, run_ranking_worker
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


def _schedule(course_id: str, day: int) -> Schedule:
    period = ExamPeriod(
        "FALL",
        "Aleph",
        [(date(2026, 1, 1), date(2026, 1, 31))],
    )
    return Schedule(period, {course_id: date(2026, 1, day)})


def _sorting() -> SortingConfig:
    return SortingConfig.from_ordered_criteria(
        [SortCriterion.SORT_MIN_DAYS_MANDATORY]
    )


def _panel_with_memory_results(qapp):
    period_key = "FALL - Aleph"
    first = _schedule("C1", 5)
    second = _schedule("C1", 10)
    controller = DesktopController()
    controller._courses = [_course()]
    controller._last_results = {period_key: [first, second]}
    controller.clear_results_stale()

    panel = _ResultsPanel(controller)
    panel._schedules_by_period = {period_key: [first, second]}
    panel._period_indices = {period_key: 0}
    qapp.processEvents()
    return panel, controller, period_key, first, second


class _FakeRunningProcess:
    created = []

    def __init__(self, target, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.daemon = daemon
        self.started = False
        self.exitcode = None
        _FakeRunningProcess.created.append(self)

    def start(self):
        self.started = True

    def is_alive(self):
        return self.started and self.exitcode is None

    def terminate(self):
        self.exitcode = -15

    def kill(self):
        self.exitcode = -9

    def join(self, timeout=0):
        return None


class _FinishedProcess:
    exitcode = 0

    def is_alive(self):
        return False

    def join(self, timeout=0):
        return None


def test_apply_ranking_starts_async_and_does_not_call_resort(monkeypatch, qapp):
    panel, controller, _period_key, _first, _second = _panel_with_memory_results(qapp)
    _FakeRunningProcess.created.clear()
    monkeypatch.setattr(controller, "resort", lambda _config: pytest.fail("resort called"))
    monkeypatch.setattr(
        "src.ui.results_panel.multiprocessing.Process",
        _FakeRunningProcess,
    )

    try:
        panel._apply_ranking(_sorting())

        assert len(_FakeRunningProcess.created) == 1
        proc = _FakeRunningProcess.created[0]
        assert proc.target is run_ranking_worker
        assert proc.started is True
        assert panel._ranking_proc is proc
        assert panel._ranking_btn.isEnabled() is False
        assert panel._ranking_btn.text() == "Ranking results..."
    finally:
        panel._cleanup_ranking_worker(terminate=True)
        panel.close()


def test_ranking_success_updates_displayed_order(qapp):
    panel, controller, period_key, first, second = _panel_with_memory_results(qapp)
    result_queue = queue.Queue()
    result_queue.put(RankingWorkerResult.ok({period_key: [second, first]}))
    panel._ranking_queue = result_queue
    panel._ranking_proc = _FinishedProcess()
    panel._ranking_config = _sorting()
    panel._set_ranking_busy(True)

    try:
        panel._poll_ranking_worker()

        assert controller.settings.sorting == _sorting()
        assert panel.get_schedules(period_key) == [second, first]
        assert panel.get_current_index(period_key) == 0
        assert panel._ranking_btn.isEnabled() is True
    finally:
        panel.close()


def test_ranking_failure_restores_ui_and_reports_error(qapp):
    panel, controller, _period_key, _first, _second = _panel_with_memory_results(qapp)
    messages = []
    panel._show_message = lambda *args, **kwargs: messages.append(args)
    result_queue = queue.Queue()
    result_queue.put(RankingWorkerResult.failure("boom"))
    panel._ranking_queue = result_queue
    panel._ranking_proc = _FinishedProcess()
    panel._ranking_config = _sorting()
    panel._set_ranking_busy(True)

    try:
        panel._poll_ranking_worker()

        assert controller.settings.sorting != _sorting()
        assert panel._ranking_btn.isEnabled() is True
        assert messages
        assert messages[0][0] == "Ranking Failed"
        assert "boom" in messages[0][1]
    finally:
        panel.close()


def test_ranking_refreshes_only_visible_period(monkeypatch, qapp):
    panel, _controller, period_key, first, second = _panel_with_memory_results(qapp)
    other_key = "FALL - Bet"
    panel._schedules_by_period[other_key] = [_schedule("C1", 20)]
    panel._period_indices[other_key] = 0
    panel._cards = {period_key: object(), other_key: object()}
    refreshed = []
    monkeypatch.setattr(panel, "_current_period_key", lambda: other_key)
    monkeypatch.setattr(panel, "_refresh_period_card", refreshed.append)

    try:
        panel._finish_ranking_success(
            {
                period_key: [second, first],
                other_key: panel._schedules_by_period[other_key],
            }
        )

        assert refreshed == [other_key]
    finally:
        panel.close()


def test_sqlite_ranking_job_uses_store_reference_not_schedule_payload(tmp_path):
    period_key = "FALL - Aleph"
    store = SQLiteScheduleStore(tmp_path / "schedules.sqlite3", delete_on_close=False)
    schedule = _schedule("C1", 5)
    store.append_many(period_key, [schedule], courses=[_course()])
    controller = DesktopController()
    controller._last_results = {
        period_key: store.as_sequence(period_key, courses=[_course()])
    }

    try:
        job = controller.build_ranking_job(_sorting())

        assert job.schedules_by_period == {}
        assert job.sqlite_store_specs == ((str(store.path), (period_key,)),)
    finally:
        store.close(delete=True)
