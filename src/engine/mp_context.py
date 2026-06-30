"""Shared multiprocessing context for compute workers.

The compute workers (generation, load-more, ranking) are Qt-free, but the main
desktop process is not. Direct ``fork`` after Qt/Cocoa has started is unsafe on
macOS, while ``spawn`` can make the window server treat each worker as a fresh
application. ``forkserver`` is preferred when available because workers fork
from a clean server process instead of the live GUI process.

Start-method preferences are platform-aware:

* Windows uses ``spawn``.
* macOS prefers ``forkserver`` and falls back to ``spawn``; it never uses direct
  ``fork``.
* Linux/other Unix prefers ``forkserver``, then ``spawn``, and keeps direct
  ``fork`` only as a last-resort fallback.

All worker ``Process`` and ``Queue`` objects MUST be created from the same
context, so every spawn site goes through :func:`worker_context`.
"""

from __future__ import annotations

import multiprocessing
import sys
from multiprocessing.context import BaseContext

_context: BaseContext | None = None


def _preferred_methods() -> tuple[str, ...]:
    """Return safe multiprocessing start methods in preferred order."""
    if sys.platform == "win32":
        return ("spawn",)

    if sys.platform == "darwin":
        # Never use direct fork on macOS after Qt/Cocoa has started.
        return ("forkserver", "spawn")

    # On Linux/Unix, forkserver is preferred. Spawn is safer than direct fork
    # for GUI apps. Direct fork is kept only as a last-resort fallback.
    return ("forkserver", "spawn", "fork")


def worker_context() -> BaseContext:
    """Return the shared multiprocessing context for compute workers.

    All worker Process and Queue objects must be created from this same context.
    """
    global _context
    if _context is not None:
        return _context

    available = set(multiprocessing.get_all_start_methods())
    for method in _preferred_methods():
        if method in available:
            _context = multiprocessing.get_context(method)
            return _context

    # Should never happen: get_all_start_methods always returns at least one.
    _context = multiprocessing.get_context()
    return _context
