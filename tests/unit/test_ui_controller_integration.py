"""
Integration Tests: UI ↔ Controller
----------------------------------
These tests run in offscreen mode and avoid heavy UI automation.
"""

import os
import sys
from datetime import date, time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtCore = pytest.importorskip(
    "PyQt6.QtCore",
    reason="PyQt6 native GUI libraries are not available in this environment.",
    exc_type=ImportError,
)
QtWidgets = pytest.importorskip(
    "PyQt6.QtWidgets",
    reason="PyQt6 native GUI libraries are not available in this environment.",
    exc_type=ImportError,
)

Qt = QtCore.Qt
QApplication = QtWidgets.QApplication
QFileDialog = QtWidgets.QFileDialog
QMessageBox = QtWidgets.QMessageBox

from src.controller import DesktopController
from src.domain.classroom import Classroom
from src.domain.course import Course
from src.domain.course_offering import CourseOffering
from src.domain.exam_period import ExamPeriod
from src.domain.proctor import ProctorConfig
from src.domain.schedule import Schedule
from src.domain.time_slot import TimeSlot
from src.ui.config_screen import ConfigScreen
from src.ui.input_screen import InputScreen


def _get_qapp() -> QApplication:
    """Return an existing QApplication or create one for UI integration tests."""
    app = QApplication.instance()

    if app is None:
        app = QApplication(sys.argv)

    return app


def _write_courses_base(path: Path) -> None:
    path.write_text(
        """Calculus
11111
Dr. Cohen
83101, 1, FALL, Obligatory
Exam
$$$$
Algorithms
22222
Dr. Levi
83102, 1, FALL, Obligatory
Exam
""",
        encoding="utf-8",
    )


def _write_courses_one(path: Path) -> None:
    path.write_text(
        """Calculus
11111
Dr. Cohen
83101, 1, FALL, Obligatory
Exam
""",
        encoding="utf-8",
    )


def _write_courses_replacement(path: Path) -> None:
    path.write_text(
        """Physics
33333
Dr. Bar
83108, 1, FALL, Obligatory
Exam
""",
        encoding="utf-8",
    )


def _write_courses_update(path: Path) -> None:
    path.write_text(
        """Calculus
11111
Dr. Cohen
83108, 1, FALL, Elective
Exam
$$$$
Algorithms
22222
Dr. Levi
83101, 1, FALL, Obligatory
Exam
""",
        encoding="utf-8",
    )


def _write_periods_one(path: Path) -> None:
    path.write_text(
        """FALL, Aleph
05-01-2026, 09-01-2026
""",
        encoding="utf-8",
    )


def _write_periods_short(path: Path) -> None:
    path.write_text(
        """FALL, Aleph
05-01-2026, 06-01-2026
""",
        encoding="utf-8",
    )


def _write_periods_replacement(path: Path) -> None:
    path.write_text(
        """SPRI, Bet
01-03-2026, 05-03-2026
""",
        encoding="utf-8",
    )


def _write_periods_update(path: Path) -> None:
    path.write_text(
        """FALL, Aleph
12-01-2026, 16-01-2026
""",
        encoding="utf-8",
    )


def _set_load_mode(screen: ConfigScreen, mode_text: str) -> None:
    """Select Replace or Update in the ConfigScreen load-mode radio group."""
    for button in screen._mode_group.buttons():
        if button.text() == mode_text:
            button.setChecked(True)
            return

    raise AssertionError(f"Load mode not found: {mode_text}")


def _patch_file_dialog(monkeypatch, paths: list[Path]) -> None:
    """Patch QFileDialog.getOpenFileName so UI load actions receive test files."""
    selected_paths = [str(path) for path in paths]

    def fake_get_open_file_name(*_args, **_kwargs):
        return selected_paths.pop(0), "Text files (*.txt)"

    monkeypatch.setattr(QFileDialog, "getOpenFileName", fake_get_open_file_name)


def _find_programme_row(screen: ConfigScreen, programme_id: str):
    """Find a _ProgrammeRow by programme id."""
    row = screen._prog_rows.get(programme_id)
    if row is None:
        raise AssertionError(f"Programme row not found: {programme_id}")
    return row


def _write_classrooms_file(tmp_path: Path) -> Path:
    classrooms = tmp_path / "classrooms.txt"
    classrooms.write_text("$$$$\nRoom 101\n40\n$$$$\nRoom 202\n60\n", encoding="utf-8")
    return classrooms


def _write_slots_file(
    tmp_path: Path,
    text: str = "09:00, 13:00, 19:00",
    filename: str = "slots.txt",
) -> Path:
    slots = tmp_path / filename
    slots.write_text(f"$$$$\n{text}\n$$$$\n", encoding="utf-8")
    return slots


def _write_proctors_file(tmp_path: Path) -> Path:
    proctors = tmp_path / "proctors.txt"
    proctors.write_text("1:20\n", encoding="utf-8")
    return proctors


def test_feature4_activates_only_after_toggle_and_all_three_valid_inputs(
    tmp_path, monkeypatch
):
    app = _get_qapp()
    controller = DesktopController()
    screen = ConfigScreen(controller)
    classrooms = _write_classrooms_file(tmp_path)
    slots = _write_slots_file(tmp_path)
    proctors = _write_proctors_file(tmp_path)
    _patch_file_dialog(monkeypatch, [classrooms, slots, proctors])

    screen._on_feature4_toggled(True)
    assert controller.feature4_enabled is True

    screen._load_classrooms()
    assert controller.feature4_active is False
    assert "2 room(s)" in screen._classrooms_label.text()

    screen._load_time_slots()
    assert controller.feature4_active is False
    assert "3 slot(s)" in screen._slots_label.text()

    screen._load_proctor_config()
    app.processEvents()

    assert controller.feature4_active is True
    assert controller.proctor_config.students_per_proctor == 20
    assert screen._feature4_status.text() == "ACTIVE"
    screen.close()


def test_invalid_feature4_file_shows_error_and_deactivates(
    tmp_path,
    monkeypatch,
):
    app = _get_qapp()
    controller = DesktopController()
    screen = ConfigScreen(controller)
    classrooms = _write_classrooms_file(tmp_path)
    slots = _write_slots_file(tmp_path)
    proctors = _write_proctors_file(tmp_path)
    invalid_slots = _write_slots_file(
        tmp_path, "09:00, 11:00", "invalid_slots.txt"
    )
    _patch_file_dialog(monkeypatch, [classrooms, slots, proctors, invalid_slots])
    shown_errors = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda _parent, title, text: shown_errors.append((title, text)),
    )

    screen._on_feature4_toggled(True)
    screen._load_classrooms()
    screen._load_time_slots()
    screen._load_proctor_config()
    assert controller.feature4_active is True

    # Slots only 2h apart violate the >=4h rule (spec 2.3.4) -> cleared.
    screen._load_time_slots()
    app.processEvents()

    assert controller.feature4_active is False
    assert controller.time_slots == []
    assert "Invalid file" in screen._slots_label.text()
    assert screen._feature4_status.text().startswith("INCOMPLETE")
    assert shown_errors
    assert shown_errors[0][0] == "Invalid Feature 4 File"
    assert "at least 4 hours apart" in shown_errors[0][1]
    screen.close()


def test_capacity_warning_cancel_prevents_generation(monkeypatch):
    app = _get_qapp()
    controller = DesktopController()
    controller._feature4_enabled = True
    controller._classrooms = [Classroom("Room 1", 20)]
    controller._time_slots = [TimeSlot(time(9, 0))]
    controller._proctor_config = ProctorConfig(20)
    controller._selected_programs = ["83101"]
    controller._exam_periods = [
        ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 9))])
    ]
    controller._courses = [
        Course(
            "11111",
            "Calculus",
            "Dr. Cohen",
            "Exam",
            [CourseOffering("83101", 1, "FALL", "Obligatory", 50)],
        )
    ]
    screen = ConfigScreen(controller)
    started = []
    screen.generation_started.connect(started.append)

    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )

    screen._on_generate()
    app.processEvents()

    assert started == []
    assert screen._gen_process is None
    screen.close()


def test_capacity_warning_proceed_returns_true(monkeypatch):
    app = _get_qapp()
    controller = DesktopController()
    controller._feature4_enabled = True
    controller._classrooms = [Classroom("Room 1", 20)]
    controller._time_slots = [TimeSlot(time(9, 0))]
    controller._proctor_config = ProctorConfig(20)
    controller._selected_programs = ["83101"]
    controller._exam_periods = [
        ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 9))])
    ]
    controller._courses = [
        Course(
            "11111",
            "Calculus",
            "Dr. Cohen",
            "Exam",
            [CourseOffering("83101", 1, "FALL", "Obligatory", 50)],
        )
    ]
    screen = ConfigScreen(controller)
    shown = []

    def answer_yes(_parent, title, text, _buttons, _default):
        shown.append((title, text))
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "warning", answer_yes)

    assert screen._confirm_capacity_warning() is True
    assert shown
    assert "Total classroom capacity: 20" in shown[0][1]
    assert "Largest exam: 50 students" in shown[0][1]
    assert "Shortfall: 30" in shown[0][1]
    app.processEvents()
    screen.close()


# ── File loading modes update controller state ─────────────────────

def test_config_screen_replace_courses_updates_controller_state(tmp_path, monkeypatch):
    """
    Loading courses through ConfigScreen in Replace mode should replace the
    controller course state and refresh the programme list.
    """
    app = _get_qapp()

    first = tmp_path / "courses_first.txt"
    second = tmp_path / "courses_second.txt"
    _write_courses_one(first)
    _write_courses_replacement(second)

    controller = DesktopController()
    screen = ConfigScreen(controller)
    screen.show()
    app.processEvents()

    _patch_file_dialog(monkeypatch, [first, second])

    _set_load_mode(screen, "Replace")
    screen._load_courses()

    assert [course.id for course in controller.courses] == ["11111"]
    assert controller.get_programme_ids() == ["83101"]
    assert len(screen._prog_rows) == 1
    assert "courses_first.txt" in screen._courses_label.text()

    screen._load_courses()

    assert [course.id for course in controller.courses] == ["33333"]
    assert controller.get_programme_ids() == ["83108"]
    assert len(screen._prog_rows) == 1
    assert "courses_second.txt" in screen._courses_label.text()

    screen.close()


def test_config_screen_update_courses_merges_into_controller_state(
    tmp_path,
    monkeypatch,
):
    """
    Loading courses through ConfigScreen in Update mode should merge new course
    data into the controller instead of clearing unrelated existing data.
    """
    app = _get_qapp()

    first = tmp_path / "courses_first.txt"
    update = tmp_path / "courses_update.txt"
    _write_courses_one(first)
    _write_courses_update(update)

    controller = DesktopController()
    screen = ConfigScreen(controller)
    screen.show()
    app.processEvents()

    _patch_file_dialog(monkeypatch, [first, update])

    _set_load_mode(screen, "Replace")
    screen._load_courses()

    assert [course.id for course in controller.courses] == ["11111"]

    _set_load_mode(screen, "Update")
    screen._load_courses()

    course_ids = [course.id for course in controller.courses]
    assert course_ids == ["11111", "22222"]

    calculus = next(course for course in controller.courses if course.id == "11111")
    offering_keys = {
        (offering.program_id, offering.year, offering.semester, offering.requirement)
        for offering in calculus.offerings
    }

    assert ("83101", 1, "FALL", "Obligatory") in offering_keys
    assert ("83108", 1, "FALL", "Elective") in offering_keys

    assert set(controller.get_programme_ids()) == {"83101", "83108"}
    assert len(screen._prog_rows) == 2
    assert "courses_update.txt" in screen._courses_label.text()

    screen.close()


def test_config_screen_replace_periods_updates_controller_state(
    tmp_path,
    monkeypatch,
):
    """
    Loading exam periods through ConfigScreen in Replace mode should replace
    the controller exam-period state.
    """
    app = _get_qapp()

    first = tmp_path / "periods_first.txt"
    second = tmp_path / "periods_second.txt"
    _write_periods_one(first)
    _write_periods_replacement(second)

    controller = DesktopController()
    screen = ConfigScreen(controller)
    screen.show()
    app.processEvents()

    _patch_file_dialog(monkeypatch, [first, second])

    _set_load_mode(screen, "Replace")
    screen._load_dates()

    assert [period.get_key() for period in controller.get_exam_periods()] == [
        "FALL - Aleph"
    ]
    assert "periods_first.txt" in screen._dates_label.text()

    screen._load_dates()

    assert [period.get_key() for period in controller.get_exam_periods()] == [
        "SPRI - Bet"
    ]
    assert "periods_second.txt" in screen._dates_label.text()

    screen.close()


def test_config_screen_update_periods_replaces_matching_period_by_key(
    tmp_path,
    monkeypatch,
):
    """
    Loading exam periods through ConfigScreen in Update mode should update the
    matching period key inside the controller state.
    """
    app = _get_qapp()

    first = tmp_path / "periods_first.txt"
    update = tmp_path / "periods_update.txt"
    _write_periods_one(first)
    _write_periods_update(update)

    controller = DesktopController()
    screen = ConfigScreen(controller)
    screen.show()
    app.processEvents()

    _patch_file_dialog(monkeypatch, [first, update])

    _set_load_mode(screen, "Replace")
    screen._load_dates()

    original_period = controller.get_exam_periods()[0]
    assert original_period.get_key() == "FALL - Aleph"
    assert original_period.date_ranges[0][0].day == 5

    _set_load_mode(screen, "Update")
    screen._load_dates()

    updated_periods = controller.get_exam_periods()

    assert len(updated_periods) == 1
    assert updated_periods[0].get_key() == "FALL - Aleph"
    assert updated_periods[0].date_ranges[0][0].day == 12
    assert updated_periods[0].date_ranges[0][1].day == 16
    assert "periods_update.txt" in screen._dates_label.text()

    screen.close()


# ── Programme selection filters visible course rows ────────────────

def test_programme_selection_signal_updates_visible_course_table(tmp_path):
    """
    Selecting programmes in ConfigScreen should emit courses_changed and update
    the Course Details table in ResultsScreen through InputScreen wiring.
    """
    app = _get_qapp()

    courses_path = tmp_path / "courses.txt"
    _write_courses_base(courses_path)

    controller = DesktopController()
    controller.load_courses(courses_path)

    screen = InputScreen(controller)
    screen.show()
    app.processEvents()

    screen._config._refresh_programme_list()
    app.processEvents()

    row_83101 = _find_programme_row(screen._config, "83101")
    row_83101._checkbox.setChecked(True)
    app.processEvents()

    assert screen._results._course_table.rowCount() == 1
    assert screen._results._course_table.item(0, 1).text() == "11111"
    assert "Calculus" in screen._results._course_table.item(0, 0).text()

    row_83102 = _find_programme_row(screen._config, "83102")
    row_83101._checkbox.setChecked(False)
    row_83102._checkbox.setChecked(True)
    app.processEvents()

    assert screen._results._course_table.rowCount() == 1
    assert screen._results._course_table.item(0, 1).text() == "22222"
    assert "Algorithms" in screen._results._course_table.item(0, 0).text()

    screen.close()


# ── Results Exam Periods are read-only ─────────────────────────────

def test_results_exam_periods_are_read_only_and_do_not_update_controller(tmp_path):
    """
    The ResultsScreen Exam Periods tab is view-only.

    Date changes are allowed only from the home/config screen. After generation,
    the Exam Periods tab should display the periods but must not allow changing
    exclusions or date ranges through DateEditorWidget.
    """
    app = _get_qapp()

    courses_path = tmp_path / "courses.txt"
    periods_path = tmp_path / "periods.txt"
    _write_courses_one(courses_path)
    _write_periods_short(periods_path)

    controller = DesktopController()
    controller.load_courses(courses_path)
    controller.load_periods(periods_path)
    controller.set_selected_programs(["83101"])

    screen = InputScreen(controller)
    screen.show()
    app.processEvents()

    screen._results.refresh_periods()
    app.processEvents()

    editor = screen._results._date_editors["FALL - Aleph"]
    excluded = date(2026, 1, 5)

    editor._on_day_toggled(excluded)
    app.processEvents()

    updated_period = controller.get_exam_periods()[0]
    assert excluded not in updated_period.excluded_dates

    screen.close()


# ── ConfigScreen signals drive InputScreen transitions ─────────────

def test_generation_started_signal_switches_to_results_loading_screen():
    """
    generation_started should switch InputScreen from ConfigScreen to
    ResultsScreen and show the loading pane.
    """
    app = _get_qapp()

    controller = DesktopController()
    screen = InputScreen(controller)
    screen.show()
    app.processEvents()

    assert screen._stacked.currentIndex() == 0

    screen._config.generation_started.emit((["83101"], {"83101": "#2563EB"}))
    app.processEvents()

    assert screen._stacked.currentIndex() == 1
    assert screen._results._content_stack.currentIndex() == 0
    assert screen._results._spin_timer.isActive() is True

    screen._results.hide_loading()
    screen.close()


def test_schedule_generated_signal_loads_results_and_hides_spinner():
    """
    schedule_generated should load result data into ResultsScreen and hide the
    loading spinner.
    """
    app = _get_qapp()

    controller = DesktopController()
    screen = InputScreen(controller)
    screen.show()
    app.processEvents()

    period = ExamPeriod(
        semester="FALL",
        moed="Aleph",
        date_ranges=[(date(2026, 1, 5), date(2026, 1, 6))],
    )
    course = Course(
        id="11111",
        name="Calculus",
        instructor="Dr. Cohen",
        evaluation_type="Exam",
    )
    schedule = Schedule(
        period=period,
        assignments={"11111": date(2026, 1, 5)},
    )

    screen._config.generation_started.emit((["83101"], {"83101": "#2563EB"}))
    app.processEvents()

    screen._config.schedule_generated.emit(
        (
            ["83101"],
            {"FALL - Aleph": [schedule]},
            {"11111": course},
            {"83101": "#2563EB"},
            set(),
        )
    )
    app.processEvents()

    assert screen._stacked.currentIndex() == 1
    assert screen._results._content_stack.currentIndex() == 1
    assert screen._results._spin_timer.isActive() is False
    assert screen._results._workspace.currentIndex() == 2
    assert screen._results._results_loaded is True

    screen.close()


def test_generation_failed_signal_returns_to_config_screen(monkeypatch):
    """
    generation_failed should hide loading, return to ConfigScreen, and show a
    user-facing error dialog.
    """
    app = _get_qapp()

    shown_messages: list[tuple[str, str]] = []

    def fake_critical(_parent, title, message):
        shown_messages.append((title, message))

    monkeypatch.setattr(QMessageBox, "critical", fake_critical)

    controller = DesktopController()
    screen = InputScreen(controller)
    screen.show()
    app.processEvents()

    screen._config.generation_started.emit((["83101"], {"83101": "#2563EB"}))
    app.processEvents()

    assert screen._stacked.currentIndex() == 1
    assert screen._results._content_stack.currentIndex() == 0

    screen._config.generation_failed.emit("Generation failed for test.")
    app.processEvents()

    assert screen._stacked.currentIndex() == 0
    assert screen._results._content_stack.currentIndex() == 1
    assert screen._results._spin_timer.isActive() is False
    assert shown_messages == [
        ("Generation Error", "Generation failed for test.")
    ]

    screen.close()


def test_view_courses_button_opens_correct_programme(
    tmp_path,
    monkeypatch,
):
    """
    Each programme row has its own View Courses button.
    Clicking a row's button opens the dialog for that specific programme.
    """
    app = _get_qapp()

    courses_path = tmp_path / "courses.txt"
    _write_courses_base(courses_path)

    controller = DesktopController()
    controller.load_courses(courses_path)

    screen = ConfigScreen(controller)
    screen.show()
    app.processEvents()

    screen._refresh_programme_list()
    app.processEvents()

    row_83101 = _find_programme_row(screen, "83101")
    row_83102 = _find_programme_row(screen, "83102")

    row_83101.set_checked(True)
    row_83102.set_checked(False)
    app.processEvents()

    opened_programmes: list[str] = []

    class FakeProgrammeCoursesDialog:
        def __init__(self, programme_id, controller, parent=None):
            opened_programmes.append(programme_id)

        def exec(self):
            return None

    monkeypatch.setattr(
        "src.ui.programme_courses_dialog.ProgrammeCoursesDialog",
        FakeProgrammeCoursesDialog,
    )

    screen._on_view_courses_for("83101")
    assert opened_programmes == ["83101"]

    screen._on_view_courses_for("83102")
    assert opened_programmes == ["83101", "83102"]

    screen.close()
