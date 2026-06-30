"""Shared multiprocessing context for compute workers.

On macOS the default start method is ``spawn``, which launches a brand-new
Python interpreter for every worker. Because the app binary is linked against
Qt/Cocoa, the macOS window server treats each spawned process as a separate GUI
application activating, momentarily stealing focus and dropping the user to the
desktop until the worker exits.

The compute workers (generation, load-more, ranking) are Qt-free, so we run
them under a ``forkserver`` context instead. The forkserver is a single clean
process started once; workers are forked from it without re-exec-ing the
Cocoa-linked binary, so the window server never sees a new application and never
steals focus. Windows has no fork support, so it falls back to ``spawn`` there.

All worker ``Process`` and ``Queue`` objects MUST be created from the same
context, so every spawn site goes through :func:`worker_context`.
"""

from __future__ import annotations

import multiprocessing
from multiprocessing.context import BaseContext

_PREFERRED_METHODS = ("forkserver", "fork", "spawn")

_context: BaseContext | None = None


def worker_context() -> BaseContext:
    """Return the shared multiprocessing context for compute workers.

    Prefers ``forkserver`` (avoids macOS focus theft and the fork-after-Cocoa
    hazard), then ``fork``, then ``spawn`` as a last resort on platforms that
    support nothing else. The result is cached so all workers and queues share
    one context.
    """
    global _context
    if _context is not None:
        return _context

    available = set(multiprocessing.get_all_start_methods())
    for method in _PREFERRED_METHODS:
        if method in available:
            _context = multiprocessing.get_context(method)
            return _context

    # Should never happen: get_all_start_methods always returns at least one.
    _context = multiprocessing.get_context()
    return _context
