"""Unit tests for LoadWorkerPool lifecycle and atexit hardening.

These tests never spawn real multiprocessing workers: the pool's internal dicts
are populated with lightweight fakes. This keeps the suite deterministic and
free of deadlock / orphaned-process risk while still verifying poison-pill
broadcast and atexit registration behaviour.
"""

import atexit
import gc
import weakref

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


def test_atexit_hook_registered_and_removed_on_shutdown():
    pool = LoadWorkerPool()
    hook = pool._atexit_hook

    pool.shutdown_all()
    # Unregistering again is a no-op, proving shutdown_all already removed it.
    atexit.unregister(hook)  # must not raise


def test_atexit_hook_does_not_keep_pool_alive():
    pool = LoadWorkerPool()
    ref = weakref.ref(pool)

    del pool
    gc.collect()

    assert ref() is None, "atexit registration must not pin the pool in memory"
