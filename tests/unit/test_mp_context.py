"""Regression tests for the shared worker multiprocessing context."""

import multiprocessing
from pathlib import Path

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


def test_worker_target_modules_do_not_import_ui_code():
    worker_targets = [
        Path("src/engine/generation_workers.py"),
        Path("src/engine/ranking_worker.py"),
        Path("src/engine/load_worker_pool.py"),
    ]
    forbidden_import_prefixes = (
        "from PyQt6",
        "import PyQt6",
        "from src.ui",
        "import src.ui",
    )

    for path in worker_targets:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            assert not stripped.startswith(forbidden_import_prefixes), (
                f"{path} imports UI code in worker context: {line}"
            )
        assert "QApplication" not in text
        assert "ExamSchedulerApp" not in text


def test_worker_startup_paths_use_shared_context_for_processes_and_queues():
    startup_sources = {
        Path("src/ui/generation_poller.py"): "worker_context()",
        Path("src/engine/load_worker_pool.py"): "worker_context()",
        Path("src/ui/result_ranking_controller.py"): "_worker_context_provider()",
    }

    for path, context_call in startup_sources.items():
        text = path.read_text(encoding="utf-8")
        assert context_call in text
        assert "ctx.Queue(" in text
        assert "ctx.Process(" in text
        assert "multiprocessing.Queue(" not in text
        assert "multiprocessing.Process(" not in text
        assert "from multiprocessing import Queue" not in text
        assert "from multiprocessing import Process" not in text

    results_panel = Path("src/ui/results_panel.py").read_text(encoding="utf-8")
    assert "worker_context_provider=lambda: worker_context()" in results_panel
