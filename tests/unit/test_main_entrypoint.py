import inspect
import multiprocessing

import pytest

import main


def _prepare_main(monkeypatch, argv: list[str]) -> list[str]:
    calls: list[str] = []

    monkeypatch.setattr(main.sys, "argv", argv)
    monkeypatch.setattr(multiprocessing, "freeze_support", lambda: calls.append("freeze"))
    monkeypatch.setattr(multiprocessing, "parent_process", lambda: None)
    return calls


def test_freeze_support_runs_before_multiprocessing_child_guard():
    source = inspect.getsource(main._main)

    assert "multiprocessing.freeze_support()" in source
    assert "_is_multiprocessing_child_process()" in source
    assert source.index("multiprocessing.freeze_support()") < source.index(
        "_is_multiprocessing_child_process()"
    )


def test_main_normal_execution_reaches_gui(monkeypatch):
    calls = _prepare_main(monkeypatch, ["main.py"])

    monkeypatch.setattr(main, "_run_gui", lambda: calls.append("gui"))
    monkeypatch.setattr(
        main,
        "_run_cli_safely",
        lambda _argv: pytest.fail("CLI should not run for normal GUI startup"),
    )

    main._main()

    assert calls == ["freeze", "gui"]


def test_main_cli_flag_reaches_cli_without_gui(monkeypatch):
    calls = _prepare_main(monkeypatch, ["main.py", "--cli", "--programs", "p.txt"])

    monkeypatch.setattr(main, "_run_gui", lambda: pytest.fail("GUI should not run"))
    monkeypatch.setattr(
        main,
        "_run_cli_safely",
        lambda argv: calls.append(f"cli:{argv!r}"),
    )

    main._main()

    assert calls == ["freeze", "cli:['--programs', 'p.txt']"]


def test_main_legacy_args_reach_cli_without_gui(monkeypatch):
    calls = _prepare_main(monkeypatch, ["main.py", "--programs", "p.txt"])

    monkeypatch.setattr(main, "_run_gui", lambda: pytest.fail("GUI should not run"))
    monkeypatch.setattr(
        main,
        "_run_cli_safely",
        lambda argv: calls.append(f"cli:{argv!r}"),
    )

    main._main()

    assert calls == ["freeze", "cli:['--programs', 'p.txt']"]


def test_multiprocessing_child_detection_uses_parent_process(monkeypatch):
    monkeypatch.setattr(multiprocessing, "parent_process", lambda: object())
    monkeypatch.setattr(main.sys, "argv", ["main.py"])

    assert main._is_multiprocessing_child_process() is True


def test_multiprocessing_child_detection_uses_fork_arg(monkeypatch):
    monkeypatch.setattr(multiprocessing, "parent_process", lambda: None)
    monkeypatch.setattr(main.sys, "argv", ["main.py", "--multiprocessing-fork"])

    assert main._is_multiprocessing_child_process() is True


def test_multiprocessing_child_exits_without_launching_gui(monkeypatch):
    calls = _prepare_main(monkeypatch, ["main.py"])
    monkeypatch.setattr(multiprocessing, "parent_process", lambda: object())
    monkeypatch.setattr(main, "_run_gui", lambda: pytest.fail("GUI should not run"))
    monkeypatch.setattr(
        main,
        "_run_cli_safely",
        lambda _argv: pytest.fail("CLI should not run"),
    )

    with pytest.raises(SystemExit) as exc_info:
        main._main()

    assert exc_info.value.code == 0
    assert calls == ["freeze"]


def test_multiprocessing_fork_arg_exits_without_launching_gui(monkeypatch):
    calls = _prepare_main(monkeypatch, ["main.py", "--multiprocessing-fork=123"])
    monkeypatch.setattr(main, "_run_gui", lambda: pytest.fail("GUI should not run"))
    monkeypatch.setattr(
        main,
        "_run_cli_safely",
        lambda _argv: pytest.fail("CLI should not run"),
    )

    with pytest.raises(SystemExit) as exc_info:
        main._main()

    assert exc_info.value.code == 0
    assert calls == ["freeze"]
