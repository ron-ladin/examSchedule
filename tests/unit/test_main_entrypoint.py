from pathlib import Path


def _main_guard_source() -> str:
    text = Path("main.py").read_text(encoding="utf-8")
    marker = 'if __name__ == "__main__":'
    assert marker in text
    return text.split(marker, 1)[1]


def test_freeze_support_is_called_under_main_guard():
    guard = _main_guard_source()

    assert "import multiprocessing" in guard
    assert "multiprocessing.freeze_support()" in guard
    assert guard.index("multiprocessing.freeze_support()") < guard.index(
        "argv = sys.argv[1:]"
    )


def test_main_guard_preserves_gui_and_cli_routing():
    guard = _main_guard_source()

    assert 'if argv and argv[0] == "--cli":' in guard
    assert "_run_cli_safely(argv[1:])" in guard
    assert "elif argv:" in guard
    assert "_run_cli_safely(argv)" in guard
    assert "else:" in guard
    assert "_run_gui()" in guard
