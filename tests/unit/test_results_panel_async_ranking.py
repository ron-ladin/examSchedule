import os
import queue
import sqlite3
import sys
import types
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
from src.domain.generation_result import GenerationResult
from src.domain.resource_guard import (
    BatchResourceDeltas,
    ResourceBudget,
    ResourceDecision,
    ResourceSnapshot,
)
from src.domain.schedule import Schedule
from src.domain.sorting import SortCriterion, SortingConfig
from src.engine.ranking_worker import RankingWorkerResult, run_ranking_worker
from src.ui.config_screen import ConfigScreen
from src.ui.input_screen import InputScreen
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


def _resource_snapshot(
    *,
    rss: float = 100,
    db: float = 10,
    wal: float = 1,
    shm: float = 0,
    free_disk: float = 100_000,
) -> ResourceSnapshot:
    return ResourceSnapshot(
        process_rss_mb=rss,
        system_total_ram_mb=16_000,
        system_available_ram_mb=12_000,
        db_size_mb=db,
        wal_size_mb=wal,
        shm_size_mb=shm,
        db_total_size_mb=db + wal + shm,
        free_disk_mb=free_disk,
    )


def _resource_budget() -> ResourceBudget:
    return ResourceBudget(
        ram_soft_limit_mb=1000,
        ram_hard_limit_mb=2000,
        min_free_ram_mb=500,
        max_db_size_mb=50_000,
        min_free_disk_mb=5000,
    )


def _resource_decision(
    *,
    can_continue: bool,
    should_warn: bool = False,
    reason: str | None = None,
    snapshot: ResourceSnapshot | None = None,
) -> ResourceDecision:
    return ResourceDecision(
        can_continue=can_continue,
        should_warn=should_warn,
        reason=reason,
        snapshot=snapshot or _resource_snapshot(),
        budget=_resource_budget(),
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


def _panel_with_sqlite_results(qapp, tmp_path):
    period_key = "FALL - Aleph"
    first = _schedule("C1", 5)
    second = _schedule("C1", 10)
    course = _course()
    store = SQLiteScheduleStore(tmp_path / "schedules.sqlite3", delete_on_close=False)
    store.append_many(period_key, [first, second], courses=[course])
    stored = store.as_sequence(period_key, courses=[course])

    controller = DesktopController()
    controller._courses = [course]
    controller._last_results = {period_key: stored}
    controller.clear_results_stale()

    panel = _ResultsPanel(controller)
    panel._schedule_store = store
    panel._schedules_by_period = {period_key: stored}
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


def test_begin_heavy_task_rejects_second_task_even_with_same_kind():
    controller = DesktopController()

    assert controller.begin_heavy_task("loading") is True
    assert controller.begin_heavy_task("loading") is False
    assert controller.heavy_task_kind == "loading"


def test_settings_sort_change_does_not_call_resort(monkeypatch, qapp):
    controller = DesktopController()
    screen = ConfigScreen(controller)
    applied = []

    monkeypatch.setattr(
        controller,
        "resort",
        lambda _config: pytest.fail("Settings sort change must not re-rank synchronously"),
    )

    original_apply_sort = controller.apply_sort

    def record_apply_sort(config):
        applied.append(config)
        original_apply_sort(config)

    monkeypatch.setattr(controller, "apply_sort", record_apply_sort)

    try:
        screen._on_sort_order_changed(_sorting())

        assert applied == [_sorting()]
        assert controller.settings.sorting == _sorting()
    finally:
        screen.close()


def test_apply_ranking_starts_async_and_does_not_call_resort(monkeypatch, qapp):
    panel, controller, _period_key, _first, _second = _panel_with_memory_results(qapp)
    _FakeRunningProcess.created.clear()
    created = {"queues": [], "procs": []}

    class _ContextQueue(queue.Queue):
        def close(self):
            pass

    def fake_queue():
        queue_obj = _ContextQueue()
        created["queues"].append(queue_obj)
        return queue_obj

    def fake_process(*args, **kwargs):
        proc = _FakeRunningProcess(*args, **kwargs)
        created["procs"].append(proc)
        return proc

    monkeypatch.setattr(controller, "resort", lambda _config: pytest.fail("resort called"))
    monkeypatch.setattr(
        "src.ui.results_panel.worker_context",
        lambda: types.SimpleNamespace(Process=fake_process, Queue=fake_queue),
    )

    try:
        panel._apply_ranking(_sorting())

        assert len(_FakeRunningProcess.created) == 1
        proc = _FakeRunningProcess.created[0]
        assert proc.target is run_ranking_worker
        assert created["queues"] == [panel._ranking_queue]
        assert created["procs"] == [proc]
        assert proc.args[0] is panel._ranking_queue
        assert proc.started is True
        assert panel._ranking_proc is proc
        assert panel._ranking_btn.isEnabled() is False
        assert panel._ranking_btn.text() == "Ranking results..."
    finally:
        panel._cleanup_ranking_worker(terminate=True)
        panel.close()


@pytest.mark.parametrize("heavy_kind", ["loading", "generation"])
def test_apply_ranking_is_blocked_while_loading_or_generation_is_active(
    monkeypatch,
    qapp,
    heavy_kind,
):
    panel, controller, _period_key, _first, _second = _panel_with_memory_results(qapp)
    messages = []
    panel._show_message = lambda *args, **kwargs: messages.append(args)
    monkeypatch.setattr(
        "src.ui.results_panel.worker_context",
        lambda: types.SimpleNamespace(
            Process=lambda *args, **kwargs: pytest.fail("ranking process should not start"),
            Queue=queue.Queue,
        ),
    )
    controller.begin_heavy_task(heavy_kind)
    panel.sync_heavy_task_state()

    try:
        panel._apply_ranking(_sorting())

        assert panel._ranking_proc is None
        assert panel._ranking_btn.isEnabled() is False
        assert panel._ranking_btn.text() == "Ranking available after loading finishes"
        assert messages and messages[0][0] == "Ranking Unavailable"
    finally:
        controller.end_heavy_task(heavy_kind)
        panel.close()


def test_ranking_success_updates_displayed_order(qapp):
    panel, controller, period_key, first, second = _panel_with_memory_results(qapp)
    result_queue = queue.Queue()
    result_queue.put(RankingWorkerResult.ok({period_key: [second, first]}))
    panel._ranking_queue = result_queue
    panel._ranking_proc = _FinishedProcess()
    panel._ranking_config = _sorting()
    panel._set_ranking_busy(True)
    panel.mark_ranking_dirty(
        "Sort settings changed. Click Result Ranking to apply to current results."
    )

    try:
        panel._poll_ranking_worker()

        assert controller.settings.sorting == _sorting()
        assert panel.get_schedules(period_key) == [second, first]
        assert panel.get_current_index(period_key) == 0
        assert panel._ranking_btn.isEnabled() is True
        assert panel._ranking_dirty is False
        assert "Click Result Ranking" not in panel._summary_lbl.text()
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


def test_load_more_is_blocked_while_ranking_is_active(monkeypatch, qapp):
    panel, controller, period_key, _first, _second = _panel_with_memory_results(qapp)
    messages = []
    try:
        panel._lm.messageRequested.disconnect()
    except TypeError:
        pass
    panel._lm.messageRequested.connect(lambda *args: messages.append(args))
    monkeypatch.setattr(
        controller,
        "start_load_more_date_options_for_period",
        lambda *args, **kwargs: pytest.fail("load worker should not start"),
    )
    monkeypatch.setattr(
        panel._lm,
        "_check_resources_before_batch",
        lambda *_args, **_kwargs: pytest.fail(
            "resource guard should not run while ranking is active"
        ),
    )
    controller.begin_heavy_task("ranking")

    try:
        panel._lm.on_load_more_dates(period_key)

        assert panel._lm.procs == {}
        assert messages and messages[0][0] == "Ranking In Progress"
    finally:
        controller.end_heavy_task("ranking")
        panel.close()


def test_load_more_variants_is_blocked_before_resource_guard_while_ranking(
    monkeypatch,
    qapp,
):
    panel, controller, period_key, _first, _second = _panel_with_memory_results(qapp)
    messages = []
    try:
        panel._lm.messageRequested.disconnect()
    except TypeError:
        pass
    panel._lm.messageRequested.connect(lambda *args: messages.append(args))
    monkeypatch.setattr(
        controller,
        "start_load_variants_for_schedule",
        lambda *args, **kwargs: pytest.fail("variant worker should not start"),
    )
    monkeypatch.setattr(
        panel._lm,
        "_check_resources_before_batch",
        lambda *_args, **_kwargs: pytest.fail(
            "resource guard should not run while ranking is active"
        ),
    )
    controller.begin_heavy_task("ranking")

    try:
        panel._lm.on_load_more_variants(period_key)

        assert panel._lm.procs == {}
        assert messages and messages[0][0] == "Ranking In Progress"
    finally:
        controller.end_heavy_task("ranking")
        panel.close()


def test_load_more_sets_loading_status_without_popup(monkeypatch, qapp):
    panel, controller, period_key, _first, _second = _panel_with_memory_results(qapp)
    monkeypatch.setattr(
        controller,
        "start_load_more_date_options_for_period",
        lambda *_args, **_kwargs: (queue.Queue(), _FinishedProcess()),
    )
    monkeypatch.setattr(
        panel._lm,
        "_start_load_more_process",
        lambda *_args, **_kwargs: None,
    )

    try:
        panel._lm.on_load_more_dates(period_key)

        assert "Loading 5,000 more date options" in panel._summary_lbl.text()
    finally:
        controller.end_heavy_task("loading")
        panel.close()


def test_auto_load_is_blocked_while_ranking_is_active(monkeypatch, qapp):
    panel, controller, period_key, _first, _second = _panel_with_memory_results(qapp)
    messages = []
    try:
        panel._lm.messageRequested.disconnect()
    except TypeError:
        pass
    panel._lm.messageRequested.connect(lambda *args: messages.append(args))
    monkeypatch.setattr(
        panel._lm,
        "start_auto_load",
        lambda *args, **kwargs: pytest.fail("auto-load should not start"),
    )
    controller.set_has_more_for_period(period_key, True)
    controller.begin_heavy_task("ranking")

    try:
        panel._lm.toggle_auto_load_dates(period_key)

        assert panel._lm.auto_load_periods == set()
        assert messages and messages[0][0] == "Ranking In Progress"
    finally:
        controller.end_heavy_task("ranking")
        panel.close()


def test_auto_load_pauses_before_hard_resource_limit(qapp):
    period_key = "FALL - Aleph"
    controller = DesktopController()
    controller._courses = [_course()]
    controller.set_has_more_for_period(period_key, True)
    panel = _ResultsPanel(controller)
    panel.load({period_key: [_schedule("C1", 5)]}, {"C1": _course()}, {}, {period_key})
    messages = []

    class _HardLimitGuard:
        def estimate_next_batch(self, _count):
            return {"estimated_ram_growth_mb": 0, "estimated_db_growth_mb": 0}

        def evaluate(self, **_kwargs):
            return _resource_decision(
                can_continue=False,
                should_warn=True,
                reason="disk reserve",
                snapshot=_resource_snapshot(rss=1500, db=2048, free_disk=2048),
            )

    panel._lm._resource_guard = _HardLimitGuard()
    try:
        panel._lm.messageRequested.disconnect()
    except TypeError:
        pass
    panel._lm.messageRequested.connect(
        lambda title, text, icon: messages.append((title, text, icon))
    )

    try:
        panel._lm.start_auto_load(period_key, "dates")

        assert period_key not in panel._lm.auto_load_periods
        assert panel._lm.procs == {}
        assert len(panel.get_schedules(period_key)) == 1
        assert messages
        assert messages[0][0] == "Resource Limit Reached"
        assert "Auto Load was paused to protect system resources" in messages[0][1]
        assert "Already loaded 1 schedules" in messages[0][1]
    finally:
        panel.close()


def test_load_batch_records_resource_deltas(qapp):
    period_key = "FALL - Aleph"
    controller = DesktopController()
    controller._courses = [_course()]
    panel = _ResultsPanel(controller)
    panel.load({period_key: [_schedule("C1", 5)]}, {"C1": _course()}, {}, set())
    before = _resource_snapshot(rss=100, db=10, wal=1, free_disk=100_000)
    after = _resource_snapshot(rss=102, db=13, wal=2, free_disk=99_996)
    recorded = {}

    class _RecordingGuard:
        def snapshot(self):
            return after

        def record_batch(self, before_snapshot, after_snapshot, schedule_count):
            recorded["args"] = (before_snapshot, after_snapshot, schedule_count)
            return BatchResourceDeltas(
                rss_delta_mb=2,
                db_delta_mb=3,
                wal_delta_mb=1,
                sqlite_total_delta_mb=4,
                ram_per_schedule_kb=2048,
                db_per_schedule_kb=3072,
                wal_per_schedule_kb=1024,
                sqlite_total_per_schedule_kb=4096,
                rolling_ram_per_schedule_kb=2048,
                rolling_db_per_schedule_kb=3072,
                rolling_wal_per_schedule_kb=1024,
                rolling_sqlite_total_per_schedule_kb=4096,
            )

    result_queue = queue.Queue()
    result_queue.put(
        GenerationResult.ok({period_key: [_schedule("C1", 10)]}, {}, set())
    )
    panel._lm._resource_guard = _RecordingGuard()
    panel._lm.resource_snapshots_before[period_key] = before
    panel._lm.queues[period_key] = result_queue
    panel._lm.modes[period_key] = "dates"
    panel._lm.ticks[period_key] = 0

    try:
        panel._lm._poll_load_more_inner(period_key)

        assert len(panel.get_schedules(period_key)) == 2
        assert recorded["args"] == (before, after, 1)
    finally:
        panel.close()


def test_auto_load_delay_is_adaptive(qapp):
    controller = DesktopController()
    panel = _ResultsPanel(controller)

    try:
        assert (
            panel._lm._next_auto_load_delay_ms(
                total_batch_seconds=0.2,
                resource_pressure=False,
                resource_warning=False,
            )
            == 100
        )
        assert (
            panel._lm._next_auto_load_delay_ms(
                total_batch_seconds=1.0,
                resource_pressure=False,
                resource_warning=False,
            )
            == 250
        )
        assert (
            panel._lm._next_auto_load_delay_ms(
                total_batch_seconds=3.0,
                resource_pressure=False,
                resource_warning=False,
            )
            == 500
        )
        assert (
            panel._lm._next_auto_load_delay_ms(
                total_batch_seconds=0.2,
                resource_pressure=False,
                resource_warning=True,
            )
            == 500
        )
        assert (
            panel._lm._next_auto_load_delay_ms(
                total_batch_seconds=0.2,
                resource_pressure=True,
                resource_warning=False,
            )
            == 1000
        )
    finally:
        panel.close()


def test_ranking_button_text_restores_after_loading_finishes(qapp):
    panel, controller, _period_key, _first, _second = _panel_with_memory_results(qapp)

    try:
        assert controller.begin_heavy_task("loading") is True
        panel.sync_heavy_task_state()

        assert panel._ranking_btn.isEnabled() is False
        assert panel._ranking_btn.text() == "Ranking available after loading finishes"

        assert controller.end_heavy_task("loading") is True
        panel.sync_heavy_task_state()

        assert panel._ranking_btn.isEnabled() is True
        assert panel._ranking_btn.text() == "⇅  Result Ranking"
    finally:
        controller.end_heavy_task()
        panel.close()


def test_append_loaded_schedules_marks_ranking_dirty_message(
    monkeypatch,
    qapp,
):
    panel, controller, period_key, first, second = _panel_with_memory_results(qapp)
    controller.apply_sort(_sorting())
    monkeypatch.setattr(
        controller,
        "cache_generated_results",
        lambda *_args, **_kwargs: pytest.fail("full rerank should not run"),
    )
    panel._rebuild_navigation_cache(period_key)
    append_calls = []
    original_append = panel._nav_model.append_entries

    def record_append(period, start_index, count):
        append_calls.append((period, start_index, count))
        original_append(period, start_index, count)

    monkeypatch.setattr(panel._nav_model, "append_entries", record_append)
    monkeypatch.setattr(
        panel._nav_model,
        "rebuild",
        lambda *_args, **_kwargs: pytest.fail("append should not rebuild nav cache"),
    )
    extra = [_schedule("C1", 20)]

    try:
        panel.append_loaded_schedules(period_key, extra)

        assert panel.get_schedules(period_key) == [first, second, extra[0]]
        assert controller._last_results[period_key] == [first, second, extra[0]]
        assert panel._ranking_dirty is True
        assert "Re-rank" in panel._summary_lbl.text()
        assert append_calls == [(period_key, 2, 1)]
    finally:
        panel.close()


def test_append_loaded_schedules_marks_sqlite_results_ranking_dirty(
    monkeypatch,
    qapp,
    tmp_path,
):
    panel, controller, period_key, _first, _second = _panel_with_sqlite_results(
        qapp,
        tmp_path,
    )
    controller.apply_sort(_sorting())
    monkeypatch.setattr(
        controller,
        "cache_generated_results",
        lambda *_args, **_kwargs: pytest.fail("full rerank should not run"),
    )
    extra = [_schedule("C1", 20)]

    try:
        panel.append_loaded_schedules(period_key, extra)

        assert len(panel.get_schedules(period_key)) == 3
        assert len(controller._last_results[period_key]) == 3
        assert panel._ranking_dirty is True
        assert "Re-rank" in panel._summary_lbl.text()
    finally:
        panel.close()


def test_append_loaded_schedules_uses_sqlite_navigation_range_without_rebuild(
    monkeypatch,
    qapp,
    tmp_path,
):
    panel, _controller, period_key, _first, _second = _panel_with_sqlite_results(
        qapp,
        tmp_path,
    )
    schedules = panel.get_schedules(period_key)
    panel._rebuild_navigation_cache(period_key)
    range_calls = []
    original_range = schedules.navigation_entries_range

    def record_range(start_index, count):
        range_calls.append((start_index, count))
        return original_range(start_index, count)

    monkeypatch.setattr(schedules, "navigation_entries_range", record_range)
    monkeypatch.setattr(
        panel._nav_model,
        "rebuild",
        lambda *_args, **_kwargs: pytest.fail("append should not rebuild nav cache"),
    )
    extra = [_schedule("C1", 20)]

    try:
        panel.append_loaded_schedules(period_key, extra)

        assert len(panel.get_schedules(period_key)) == 3
        assert range_calls == [(2, 1)]
        assert panel._nav_model.nav_position(period_key, 2) == (2, 0)
    finally:
        panel.close()


def test_append_loaded_schedules_switches_sqlite_view_to_append_order_when_dirty(
    qapp,
    tmp_path,
):
    period_key = "FALL - Aleph"
    period = ExamPeriod("FALL", "Aleph", [(date(2026, 1, 1), date(2026, 1, 31))])
    course_1 = _course()
    course_2 = Course(
        id="C2",
        name="Data Structures",
        instructor="Dr. Sort",
        evaluation_type="Exam",
        offerings=[CourseOffering("83101", 1, "FALL", "Obligatory")],
    )
    narrow = Schedule(
        period,
        {"C1": date(2026, 1, 5), "C2": date(2026, 1, 6)},
    )
    wide = Schedule(
        period,
        {"C1": date(2026, 1, 5), "C2": date(2026, 1, 20)},
    )
    extra = Schedule(
        period,
        {"C1": date(2026, 1, 5), "C2": date(2026, 1, 10)},
    )

    store = SQLiteScheduleStore(tmp_path / "schedules.sqlite3", delete_on_close=False)
    store.append_many(
        period_key,
        [narrow, wide],
        courses=[course_1, course_2],
        selected_programs=["83101"],
    )
    stored = store.as_sequence(
        period_key,
        courses=[course_1, course_2],
        selected_programs=["83101"],
        sorting=_sorting(),
    )
    assert list(stored) == [wide, narrow]

    controller = DesktopController()
    controller._courses = [course_1, course_2]
    controller._selected_programs = ["83101"]
    controller.apply_sort(_sorting())
    controller._last_results = {period_key: stored}
    controller.clear_results_stale()

    panel = _ResultsPanel(controller)
    panel._schedule_store = store
    panel._schedules_by_period = {period_key: stored}
    panel._period_indices = {period_key: 0}

    try:
        panel.append_loaded_schedules(period_key, [extra])

        assert panel._ranking_dirty is True
        assert list(panel.get_schedules(period_key)) == [narrow, wide, extra]
    finally:
        panel.close()


def test_sqlite_write_failure_stops_auto_load_and_keeps_existing_results(
    monkeypatch,
    qapp,
    tmp_path,
):
    panel, _controller, period_key, _first, _second = _panel_with_sqlite_results(
        qapp,
        tmp_path,
    )
    messages = []
    try:
        panel._lm.messageRequested.disconnect()
    except TypeError:
        pass
    panel._lm.messageRequested.connect(
        lambda title, text, icon: messages.append((title, text, icon))
    )

    def fail_append_many(*_args, **_kwargs):
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(panel._schedule_store, "append_many", fail_append_many)

    result_queue = queue.Queue()
    result_queue.put(
        GenerationResult.ok(
            {period_key: [_schedule("C1", 20)]},
            {},
            {period_key},
        )
    )
    panel._lm.queues[period_key] = result_queue
    panel._lm.modes[period_key] = "dates"
    panel._lm.ticks[period_key] = 0
    panel._lm.auto_load_periods.add(period_key)
    panel._lm.auto_load_modes[period_key] = "dates"

    try:
        panel._lm._poll_load_more_inner(period_key)

        assert len(panel.get_schedules(period_key)) == 2
        assert period_key not in panel._lm.auto_load_periods
        assert messages
        assert messages[0][0] == "Storage Failed"
        assert "Already loaded 2 schedules" in messages[0][1]
    finally:
        panel.close()


def test_results_panel_release_deletes_store_and_clears_navigation(qapp, tmp_path):
    panel, _controller, period_key, _first, _second = _panel_with_sqlite_results(
        qapp,
        tmp_path,
    )
    db_path = panel._schedule_store.path
    wal_path = db_path.with_name(db_path.name + "-wal")
    shm_path = db_path.with_name(db_path.name + "-shm")
    panel._rebuild_navigation_cache(period_key)
    panel._cell_data[period_key] = {(0, 0): ("cell",)}
    panel._favorite_schedules.append(object())
    panel._schedule_store.close(delete=False)
    wal_path.write_bytes(b"wal")
    shm_path.write_bytes(b"shm")

    panel.release_results(delete_db=True)
    panel.release_results(delete_db=True)

    assert panel._schedules_by_period == {}
    assert panel._period_indices == {}
    assert panel._truncated_periods == set()
    assert panel._total_by_period == {}
    assert panel._cell_data == {}
    assert panel._nav_model._date_option_cache == {}
    assert panel._nav_model._index_nav_cache == {}
    assert panel._nav_model._signature_pos_cache == {}
    assert panel._favorite_schedules == []
    assert not db_path.exists()
    assert not wal_path.exists()
    assert not shm_path.exists()


def test_back_to_input_discards_results_and_deletes_temp_db(
    monkeypatch,
    qapp,
):
    period_key = "FALL - Aleph"
    controller = DesktopController()
    controller._courses = [_course()]
    screen = InputScreen(controller)
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QtWidgets.QMessageBox.StandardButton.Yes,
    )

    try:
        screen._results.load(
            {period_key: [_schedule("C1", 5)]},
            {"C1": _course()},
            {},
            set(),
        )
        db_path = screen._results._results_panel._schedule_store.path
        wal_path = db_path.with_name(db_path.name + "-wal")
        shm_path = db_path.with_name(db_path.name + "-shm")
        screen._results._results_panel._schedule_store.close(delete=False)
        wal_path.write_bytes(b"wal")
        shm_path.write_bytes(b"shm")

        screen._on_back_requested()

        assert screen._stacked.currentIndex() == 0
        assert screen._results.has_results_loaded() is False
        assert controller._last_results is None
        assert not db_path.exists()
        assert not wal_path.exists()
        assert not shm_path.exists()
    finally:
        screen.close()


def test_auto_dates_background_batch_refreshes_counters_without_calendar(
    monkeypatch,
    qapp,
):
    period_key = "FALL - Aleph"
    first = _schedule("C1", 5)
    extra = _schedule("C1", 10)
    controller = DesktopController()
    controller._courses = [_course()]
    controller.set_has_more_for_period(period_key, True)
    panel = _ResultsPanel(controller)
    panel.load({period_key: [first]}, {"C1": _course()}, {}, {period_key})

    def fail_calendar_populate(*_args, **_kwargs):
        raise AssertionError("background Auto Dates must not repaint the calendar")

    monkeypatch.setattr(panel._calendar, "populate", fail_calendar_populate)
    result_queue = queue.Queue()
    result_queue.put(
        GenerationResult.ok(
            {period_key: [extra]},
            {},
            set(),
        )
    )
    panel._lm.queues[period_key] = result_queue
    panel._lm.modes[period_key] = "dates"
    panel._lm.ticks[period_key] = 0
    panel._lm.auto_load_periods.add(period_key)
    panel._lm.auto_load_modes[period_key] = "dates"

    try:
        panel._lm._poll_load_more_inner(period_key)

        assert len(panel.get_schedules(period_key)) == 2
        assert "Date option:" in panel._cards[period_key].date_counter_label.text()
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


def test_ranking_preserves_shortlist_by_fingerprint(qapp):
    """Shortlist entries survive ranking because they use schedule fingerprints."""
    panel, _controller, period_key, first, second = _panel_with_memory_results(qapp)

    try:
        panel._period_indices[period_key] = 1
        panel._save_current_favorite(period_key)
        assert len(panel._favorite_schedules) == 1

        # Re-rank reverses the order; the shortlist should still point at the
        # same schedule content rather than the old positional index.
        panel._finish_ranking_success({period_key: [second, first]})

        assert len(panel._favorite_schedules) == 1
        assert panel._favorites_btn.text() == "Shortlist (1)"
        assert panel._favorites_btn.isEnabled() is True
        assert panel._open_favorite_at(0) is True
        assert panel._period_indices[period_key] == 0
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
