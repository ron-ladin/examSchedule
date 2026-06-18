"""
LoadWorkerPool — persistent background worker management.

Manages one reusable multiprocessing worker per period key so that
Auto-Dates / Auto-Variants do not open a new process per batch.
DesktopController holds one instance and delegates all worker lifecycle
calls here.
"""

import atexit
import logging
import multiprocessing
import weakref

from src.engine.generation_workers import _run_load_more_worker

logger = logging.getLogger(__name__)


class LoadWorkerPool:
    """Manages persistent background load-more workers per period.

    Workers are ``daemon=True``, so Python's multiprocessing exit handler and
    the OS already terminate them when the main process dies. As a defensive
    belt-and-braces measure for normal interpreter exit, the pool also registers
    an ``atexit`` hook that broadcasts the ``None`` poison pill and terminates
    every live worker. The hook holds only a weak reference to the pool so that
    short-lived pools (e.g. in tests) remain garbage-collectable.

    Raw ``SIGINT``/``SIGTERM`` handlers are intentionally *not* installed here:
    signal handlers may only be set from the main thread and would conflict with
    PyQt's own signal handling and with the test runner. daemon + atexit covers
    the orphaned-process case without that risk.
    """

    def __init__(self) -> None:
        self._task_queues: dict[str, multiprocessing.Queue] = {}
        self._result_queues: dict[str, multiprocessing.Queue] = {}
        self._procs: dict[str, multiprocessing.Process] = {}

        # Best-effort cleanup on normal exit. Bound through a weakref so the
        # registration does not keep this pool alive for the whole process.
        pool_ref = weakref.ref(self)

        def _atexit_shutdown() -> None:
            pool = pool_ref()
            if pool is not None:
                pool._safe_shutdown_all()

        self._atexit_hook = _atexit_shutdown
        atexit.register(_atexit_shutdown)

    def _safe_shutdown_all(self) -> None:
        """Shut down every worker, swallowing errors (used from atexit)."""
        try:
            self.shutdown_all()
        except Exception:
            # At interpreter exit multiprocessing internals may be partially
            # torn down; never raise from the atexit hook.
            logger.debug("atexit load-worker shutdown failed", exc_info=True)

    def get_or_start(
        self,
        period_key: str,
    ) -> "tuple[multiprocessing.Queue, multiprocessing.Queue, multiprocessing.Process]":
        """Return a reusable (task_queue, result_queue, proc) for *period_key*.

        Starting a multiprocessing process is expensive on Windows and may flash
        a console window. This method starts the worker once and keeps it alive
        for the next batch.
        """
        proc = self._procs.get(period_key)
        task_queue = self._task_queues.get(period_key)
        result_queue = self._result_queues.get(period_key)

        if (
            proc is not None
            and task_queue is not None
            and result_queue is not None
            and proc.is_alive()
        ):
            return task_queue, result_queue, proc

        self.cleanup(period_key, terminate=True)

        task_queue = multiprocessing.Queue()
        result_queue = multiprocessing.Queue()
        proc = multiprocessing.Process(
            target=_run_load_more_worker,
            args=(task_queue, result_queue),
            daemon=True,
        )
        proc.start()

        self._task_queues[period_key] = task_queue
        self._result_queues[period_key] = result_queue
        self._procs[period_key] = proc

        return task_queue, result_queue, proc

    def cleanup(self, period_key: str, terminate: bool = False) -> None:
        """Stop and remove the persistent worker for *period_key*."""
        task_queue = self._task_queues.pop(period_key, None)
        result_queue = self._result_queues.pop(period_key, None)
        proc = self._procs.pop(period_key, None)

        if task_queue is not None:
            try:
                if not terminate:
                    task_queue.put(None)
            except Exception:
                logger.debug("Could not send shutdown task to load worker", exc_info=True)

        if proc is not None:
            try:
                if terminate and proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=0)

                    if proc.is_alive():
                        proc.kill()
                        proc.join(timeout=0)
                else:
                    proc.join(timeout=0)
            except Exception:
                logger.debug("Failed cleaning up load worker", exc_info=True)

        for q in (task_queue, result_queue):
            if q is None:
                continue
            try:
                q.cancel_join_thread()
            except Exception:
                logger.warning(
                    "Could not cancel join thread on load-worker queue",
                    exc_info=True,
                )
            try:
                q.close()
            except Exception:
                logger.warning(
                    "Could not close load-worker queue",
                    exc_info=True,
                )

    def shutdown_all(self) -> None:
        """Terminate all active workers and drop the atexit hook."""
        for period_key in list(self._procs):
            self.cleanup(period_key, terminate=True)

        # Once explicitly shut down there is nothing left to clean up at exit.
        hook = getattr(self, "_atexit_hook", None)
        if hook is not None:
            atexit.unregister(hook)
