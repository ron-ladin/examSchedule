"""Regression tests for the shared worker multiprocessing context.

Guards the macOS focus-steal fix: compute workers must never run under the
default ``spawn`` start method when a fork-based method is available, because
spawning a Qt/Cocoa-linked interpreter makes macOS steal window focus.
"""

import multiprocessing

import src.engine.mp_context as mp_context
from src.engine.mp_context import worker_context


def _reset_cache():
    mp_context._context = None


def test_worker_context_is_cached():
    _reset_cache()
    try:
        assert worker_context() is worker_context()
    finally:
        _reset_cache()


def test_prefers_fork_based_method_when_available():
    _reset_cache()
    try:
        method = worker_context().get_start_method()
        available = set(multiprocessing.get_all_start_methods())
        if {"forkserver", "fork"} & available:
            assert method in {"forkserver", "fork"}
            assert method != "spawn"
        else:  # Windows: only spawn exists
            assert method == "spawn"
    finally:
        _reset_cache()
