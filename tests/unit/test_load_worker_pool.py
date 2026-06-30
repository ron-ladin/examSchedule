"""Unit tests for LoadWorkerPool lifecycle and atexit hardening.

These tests never spawn real multiprocessing workers: the pool's internal dicts
are populated with lightweight fakes. This keeps the suite deterministic and
free of deadlock / orphaned-process risk while still verifying poison-pill
broadcast and atexit registration behaviour.
"""

import atexit
import gc
import types
import weakref

import src.engine.load_worker_pool as lwp
from src.engine.load_worker_pool import LoadWorkerPool


class _FakeQueue:
    def __init__(self) -> None:
        self.put_items: list = []
        self.closed = False
        self.cancelled = False

    def put(self, item) -> None:
        self.put_items.append(item)

    def cancel_join_thread(self) -> None:
        self.cancelled = True

    def close(self) -> None:
        self.closed = True


class _FakeProc:
    def __init__(self) -> None:
        self.terminated = False
        self.killed = False
        self._alive = True

    def is_alive(self) -> bool:
        return self._alive

    def terminate(self) -> None:
        self.terminated = True
        self._alive = False

    def kill(self) -> None:
        self.killed = True
        self._alive = False

    def join(self, timeout=None) -> None:
        self._alive = False


def _seed_worker(pool: LoadWorkerPool, period_key: str) -> tuple:
    task_q, result_q, proc = _FakeQueue(), _FakeQueue(), _FakeProc()
    pool._task_queues[period_key] = task_q
    pool._result_queues[period_key] = result_q
    pool._procs[period_key] = proc
    return task_q, result_q, proc


def test_cleanup_without_terminate_sends_poison_pill():
    pool = LoadWorkerPool()
    task_q, _result_q, _proc = _seed_worker(pool, "FALL - Aleph")

    pool.cleanup("FALL - Aleph", terminate=False)

    assert task_q.put_items == [None], "graceful cleanup must broadcast poison pill"
    assert task_q.closed is True
    assert "FALL - Aleph" not in pool._procs


def test_shutdown_all_terminates_every_worker():
    pool = LoadWorkerPool()
    _seed_worker(pool, "FALL - Aleph")
    _seed_worker(pool, "SPRING - Bet")
    procs = list(pool._procs.values())

    pool.shutdown_all()

    assert pool._procs == {}
    assert all(p.terminated for p in procs), "shutdown_all must terminate workers"


class _RecordingProc(_FakeProc):
    """A spawnable _FakeProc that records construction args and start()."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__()
        self.started = False
        self.construct_args = (args, kwargs)

    def start(self) -> None:
        self.started = True


def _patch_spawning(monkeypatch) -> dict:
    """Replace multiprocessing.Queue/Process so get_or_start spawns fakes.

    Keeps the reuse tests fully process-free while still letting get_or_start
    run its real start-a-new-worker branch.
    """
    created: dict[str, list] = {"queues": [], "procs": []}

    def fake_queue() -> _FakeQueue:
        q = _FakeQueue()
        created["queues"].append(q)
        return q

    def fake_process(*args, **kwargs) -> _RecordingProc:
        p = _RecordingProc(*args, **kwargs)
        created["procs"].append(p)
        return p

    monkeypatch.setattr(
        lwp,
        "worker_context",
        lambda: types.SimpleNamespace(Queue=fake_queue, Process=fake_process),
    )
    return created


def test_get_or_start_reuses_alive_worker(monkeypatch):
    pool = LoadWorkerPool()
    task_q, result_q, proc = _seed_worker(pool, "FALL - Aleph")

    def _no_spawn(*_args, **_kwargs):
        raise AssertionError("get_or_start must not spawn for a live worker")

    monkeypatch.setattr(
        lwp,
        "worker_context",
        lambda: types.SimpleNamespace(Process=_no_spawn, Queue=_no_spawn),
    )

    assert pool.get_or_start("FALL - Aleph") == (task_q, result_q, proc)


def test_get_or_start_starts_new_worker_for_different_period(monkeypatch):
    pool = LoadWorkerPool()
    _task_q, _result_q, existing = _seed_worker(pool, "FALL - Aleph")
    created = _patch_spawning(monkeypatch)

    _new_task, _new_result, new_proc = pool.get_or_start("SPRING - Bet")

    assert new_proc is not existing, "a different period must get its own worker"
    assert new_proc.started is True
    assert created["procs"] == [new_proc]
    # The unrelated period's worker stays untouched.
    assert pool._procs["FALL - Aleph"] is existing
    assert pool._procs["SPRING - Bet"] is new_proc


def test_get_or_start_creates_queues_and_process_from_same_context(monkeypatch):
    pool = LoadWorkerPool()
    created = _patch_spawning(monkeypatch)

    task_q, result_q, proc = pool.get_or_start("FALL - Aleph")

    _args, kwargs = proc.construct_args
    assert created["queues"] == [task_q, result_q]
    assert created["procs"] == [proc]
    assert kwargs["args"] == (task_q, result_q)


def test_get_or_start_replaces_dead_worker(monkeypatch):
    pool = LoadWorkerPool()
    _task_q, _result_q, dead = _seed_worker(pool, "FALL - Aleph")
    dead._alive = False  # simulate a crashed/finished worker
    created = _patch_spawning(monkeypatch)

    _new_task, _new_result, new_proc = pool.get_or_start("FALL - Aleph")

    assert new_proc is not dead, "a dead worker must be replaced, not reused"
    assert new_proc.started is True
    assert created["procs"] == [new_proc]
    assert pool._procs["FALL - Aleph"] is new_proc


def test_atexit_hook_stays_registered_after_shutdown(monkeypatch):
    pool = LoadWorkerPool()
    hook = pool._atexit_hook

    pool.shutdown_all()

    # shutdown_all must NOT drop the hook: a reused pool still needs exit-time
    # protection for any workers started afterwards.
    assert pool._atexit_hook is hook

    # Prove the still-registered hook protects workers created after shutdown.
    _patch_spawning(monkeypatch)
    _task_q, _result_q, proc = pool.get_or_start("FALL - Aleph")

    hook()  # simulate interpreter exit firing the still-live atexit hook

    assert proc.terminated is True
    assert pool._procs == {}


def test_atexit_hook_does_not_keep_pool_alive():
    pool = LoadWorkerPool()
    ref = weakref.ref(pool)

    del pool
    gc.collect()

    assert ref() is None, "atexit registration must not pin the pool in memory"
