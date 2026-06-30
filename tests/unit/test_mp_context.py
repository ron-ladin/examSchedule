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


def test_worker_context_falls_back_when_preferred_context_raises_value_error(
    monkeypatch,
):
    _reset_cache()
    calls = []

    class FakeContext:
        def __init__(self, method: str) -> None:
            self.method = method

        def get_start_method(self) -> str:
            return self.method

    monkeypatch.setattr(
        mp_context,
        "_preferred_methods",
        lambda: ("forkserver", "spawn"),
    )
    monkeypatch.setattr(
        mp_context.multiprocessing,
        "get_all_start_methods",
        lambda: ["forkserver", "spawn"],
    )

    def fake_get_context(method=None):
        calls.append(method)
        if method == "forkserver":
            raise ValueError("forkserver unavailable in this environment")
        return FakeContext(method or "default")

    monkeypatch.setattr(mp_context.multiprocessing, "get_context", fake_get_context)

    try:
        ctx = mp_context.worker_context()

        assert ctx.get_start_method() == "spawn"
        assert calls == ["forkserver", "spawn"]
    finally:
        _reset_cache()


def test_worker_context_logs_selected_start_method(monkeypatch, caplog):
    _reset_cache()

    class FakeContext:
        def __init__(self, method: str) -> None:
            self.method = method

        def get_start_method(self) -> str:
            return self.method

    monkeypatch.setattr(mp_context, "_preferred_methods", lambda: ("forkserver",))
    monkeypatch.setattr(
        mp_context.multiprocessing,
        "get_all_start_methods",
        lambda: ["forkserver"],
    )
    monkeypatch.setattr(
        mp_context.multiprocessing,
        "get_context",
        lambda method=None: FakeContext(method or "default"),
    )
    caplog.set_level("INFO", logger=mp_context.__name__)

    try:
        ctx = mp_context.worker_context()

        assert ctx.get_start_method() == "forkserver"
        assert "Using multiprocessing start method: forkserver" in caplog.text
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
