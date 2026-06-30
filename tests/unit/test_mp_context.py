"""Regression tests for the shared worker multiprocessing context."""

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


def test_macos_preferred_methods_never_include_direct_fork(monkeypatch):
    monkeypatch.setattr(mp_context.sys, "platform", "darwin")

    assert mp_context._preferred_methods() == ("forkserver", "spawn")
    assert "fork" not in mp_context._preferred_methods()


def test_windows_preferred_methods_use_spawn(monkeypatch):
    monkeypatch.setattr(mp_context.sys, "platform", "win32")

    assert mp_context._preferred_methods() == ("spawn",)


def test_linux_preferred_methods_keep_fork_as_last_resort(monkeypatch):
    monkeypatch.setattr(mp_context.sys, "platform", "linux")

    assert mp_context._preferred_methods() == ("forkserver", "spawn", "fork")


def test_worker_context_uses_platform_preferred_available_method(monkeypatch):
    _reset_cache()
    try:
        monkeypatch.setattr(mp_context.sys, "platform", "linux")
        method = worker_context().get_start_method()
        available = set(multiprocessing.get_all_start_methods())
        expected = next(
            preferred
            for preferred in ("forkserver", "spawn", "fork")
            if preferred in available
        )

        assert method == expected
    finally:
        _reset_cache()
