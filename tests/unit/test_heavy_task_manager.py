from src.controller import DesktopController
from src.domain.heavy_task_manager import HeavyTaskManager, HeavyTaskToken


def test_starting_first_heavy_task_succeeds():
    manager = HeavyTaskManager()

    token = manager.begin("generation")

    assert token is not None
    assert token.kind == "generation"
    assert manager.active_kind == "generation"
    assert manager.is_active() is True


def test_starting_second_heavy_task_fails():
    manager = HeavyTaskManager()

    first = manager.begin("loading")
    second = manager.begin("ranking")

    assert first is not None
    assert second is None
    assert manager.active_kind == "loading"


def test_wrong_owner_token_does_not_release_active_task():
    manager = HeavyTaskManager()
    token = manager.begin("ranking")
    wrong_token = HeavyTaskToken(kind="ranking")

    assert token is not None
    assert manager.end(wrong_token) is False
    assert manager.active_kind == "ranking"
    assert manager.end(token) is True
    assert manager.active_kind is None


def test_controller_heavy_task_wrappers_delegate_to_manager():
    controller = DesktopController()

    assert controller.begin_heavy_task("loading") is True
    assert controller.begin_heavy_task("loading") is False
    assert controller.begin_heavy_task("ranking") is False
    assert controller.heavy_task_kind == "loading"

    assert controller.end_heavy_task("ranking") is False
    assert controller.heavy_task_kind == "loading"
    assert controller.end_heavy_task("loading") is True
    assert controller.heavy_task_kind is None
