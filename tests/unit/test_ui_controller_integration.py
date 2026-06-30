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

from src.controller import LOAD_BATCH_SIZE, DesktopController
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


def _wait_for_qt_timers(ms: int) -> None:
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _generation_ready_config_screen() -> tuple[
    QApplication,
    DesktopController,
    ConfigScreen,
]:
    app = _get_qapp()
    controller = DesktopController()
    controller._courses = [
        Course(
            id="11111",
            name="Calculus",
            instructor="Dr. Cohen",
            evaluation_type="Exam",
            offerings=[CourseOffering("83101", 1, "FALL", "Obligatory")],
        )
    ]
    controller._exam_periods = [
        ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 9))])
    ]
    screen = ConfigScreen(controller)
    screen._refresh_programme_list()
    _find_programme_row(screen, "83101").set_checked(True)
    screen._refresh_periods_card()
    screen._update_gen_btn()
    return app, controller, screen


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
    for button in screen._mode_card.button_group.buttons():
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
    """Slots/proctor are now QLineEdit text fields (spec §2.3.5, §2.4.4).
    Classrooms still uses Browse; toggle can be enabled once all three are valid."""
    app = _get_qapp()
    controller = DesktopController()
    screen = ConfigScreen(controller)
    classrooms = _write_classrooms_file(tmp_path)
    _patch_file_dialog(monkeypatch, [classrooms])

    # Load classrooms via Browse — still file-based per spec §4.1.
    screen._feature4_card._load_classrooms()
    assert controller.feature4_active is False
    assert "2 room(s)" in screen._feature4_card._classrooms_label.text()

    # Enter time slots via the new text field (spec §2.3.5).
    screen._feature4_card._slots_edit.setText("09:00, 13:00, 19:00")
    screen._feature4_card._commit_slots_text()
    assert controller.feature4_active is False
    assert "3 slot(s)" in screen._feature4_card._slots_label.text()

    # Enter proctor ratio via the new text field (spec §2.4.4).
    screen._feature4_card._proctors_edit.setText("1:20")
    screen._feature4_card._commit_proctors_text()
    assert controller.proctor_config is not None
    assert controller.proctor_config.students_per_proctor == 20

    # All inputs are valid; turning ON the toggle activates Feature 4.
    screen._feature4_card._on_toggled(True)
    assert controller.feature4_enabled is True
    app.processEvents()

    assert controller.feature4_active is True
    assert screen._feature4_card._status_lbl.text() == "ACTIVE"
    screen.close()


def test_invalid_feature4_slots_text_shows_error_and_deactivates(
    tmp_path,
    monkeypatch,
):
    """Entering slots < 4h apart in the text field must show an inline error
    and keep Feature 4 inactive (spec §2.3.4 / §2.3.7)."""
    app = _get_qapp()
    controller = DesktopController()
    screen = ConfigScreen(controller)
    classrooms = _write_classrooms_file(tmp_path)
    _patch_file_dialog(monkeypatch, [classrooms])

    # Bring Feature 4 to ACTIVE state with valid inputs.
    screen._feature4_card._load_classrooms()
    screen._feature4_card._slots_edit.setText("09:00, 13:00, 19:00")
    screen._feature4_card._commit_slots_text()
    screen._feature4_card._proctors_edit.setText("1:20")
    screen._feature4_card._commit_proctors_text()
    screen._feature4_card._on_toggled(True)
    assert controller.feature4_active is True

    # Enter slots only 2h apart — violates the >=4h rule (spec §2.3.4).
    screen._feature4_card._slots_edit.setText("09:00, 11:00")
    screen._feature4_card._commit_slots_text()
    app.processEvents()

    assert controller.feature4_active is False
    assert controller.time_slots == []
    assert "Invalid" in screen._feature4_card._slots_label.text()
    assert screen._feature4_card._status_lbl.text().startswith("INCOMPLETE")
    screen.close()


# ── Feature 4: Browse button gating (spec §4.1, M1 fix) ──────────────────────

def test_feature4_browse_button_disabled_when_toggle_off():
    """Classrooms Browse button must be disabled when Feature 4 toggle is OFF."""
    app = _get_qapp()
    controller = DesktopController()
    screen = ConfigScreen(controller)

    screen._feature4_card._toggle.setChecked(False)
    assert screen._feature4_card._load_classrooms_btn.isEnabled() is False

    screen._feature4_card._toggle.setChecked(True)
    assert screen._feature4_card._load_classrooms_btn.isEnabled() is True

    app.processEvents()
    screen.close()


# ── Feature 4: debounce timer path (M2 fix) ───────────────────────────────────

def test_feature4_slots_debounce_timer_fires_and_updates_state():
    """True signal-chain test: typing into the QLineEdit starts the debounce
    timer (not fired yet), and only the timeout commits the value to state."""
    app = _get_qapp()
    controller = DesktopController()
    screen = ConfigScreen(controller)

    card = screen._feature4_card

    # Typing starts the debounce timer but must NOT commit immediately.
    card._slots_edit.setText("09:00, 13:00, 19:00")
    assert card._slots_timer.isActive() is True
    assert controller.time_slots == []

    # Firing the timeout signal runs the real slot through the signal chain.
    card._slots_timer.timeout.emit()
    assert "slot" in card._slots_label.text().lower()
    assert len(controller.time_slots) == 3

    app.processEvents()
    screen.close()


def test_feature4_proctors_debounce_timer_fires_and_updates_state():
    """True signal-chain test for the Proctor Ratio QLineEdit: typing starts the
    debounce timer, and only the timeout commits the parsed ratio to state."""
    app = _get_qapp()
    controller = DesktopController()
    screen = ConfigScreen(controller)

    card = screen._feature4_card

    # Typing starts the debounce timer but must NOT commit immediately.
    card._proctors_edit.setText("1:20")
    assert card._proctors_timer.isActive() is True
    assert controller.proctor_config is None

    # Firing the timeout signal runs the real ratio through the signal chain.
    card._proctors_timer.timeout.emit()
    assert "1:20" in card._proctors_label.text()
    assert controller.proctor_config is not None
    assert controller.proctor_config.students_per_proctor == 20

    app.processEvents()
    screen.close()


def test_feature4_empty_classrooms_file_shows_no_valid_rooms_badge(
    tmp_path, monkeypatch
):
    """Spec §2.2.6: an empty classrooms file yields 0 rooms and the card shows
    the dedicated 'No valid rooms in file' badge with the invalid style."""
    app = _get_qapp()
    controller = DesktopController()
    screen = ConfigScreen(controller)

    empty = tmp_path / "empty_classrooms.txt"
    empty.write_text("", encoding="utf-8")
    _patch_file_dialog(monkeypatch, [empty])

    screen._feature4_card._load_classrooms()
    app.processEvents()

    assert screen._feature4_card._classrooms_label.text() == "No valid rooms in file"
    assert "FEE2E2" in screen._feature4_card._classrooms_label.styleSheet()  # invalid style
    assert controller.classrooms == []

    screen.close()


# ── Spec §4.3: file-load abort when StudentCount missing (H1 fix) ─────────────

def test_spec_4_3_file_load_aborted_when_student_count_missing(
    tmp_path, monkeypatch
):
    """When Feature 4 is ON and the loaded courses file has Exam courses without
    StudentCount, the load must be rejected: prior courses restored, error dialog
    shown, and the label reflects the abort (spec §4.3)."""
    app = _get_qapp()

    prior_courses_file = tmp_path / "prior.txt"
    prior_courses_file.write_text(
        "Calculus\n11111\nDr. Cohen\n83101, 1, FALL, Obligatory, 30\nExam\n",
        encoding="utf-8",
    )
    controller = DesktopController()
    controller.load_courses(prior_courses_file)
    prior_count = len(controller._courses)
    assert prior_count == 1

    controller._feature4_enabled = True

    bad_courses_file = tmp_path / "bad.txt"
    bad_courses_file.write_text(
        "Physics\n22222\nDr. Levi\n83102, 1, FALL, Obligatory\nExam\n",
        encoding="utf-8",
    )

    screen = ConfigScreen(controller)
    _patch_file_dialog(monkeypatch, [bad_courses_file])

    errors_shown = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: errors_shown.append(args),
    )

    screen._load_courses()
    app.processEvents()

    assert len(controller._courses) == prior_count, "Prior courses not restored"
    assert errors_shown, "No error dialog was shown"
    label_text = screen._files_card.courses_label.text()
    assert any(
        kw in label_text for kw in ("Missing", "aborted", "StudentCount")
    ), f"Label did not reflect abort: {label_text!r}"

    screen.close()


# NOTE: the capacity-warning *cancel* path (warning -> No -> generation blocked)
# is covered end-to-end by tests/e2e/test_ui_engine_stress.py
# ::test_capacity_shortfall_warns_before_generation, which also asserts the
# shortfall tuple. The proceed path (message content + Yes) is kept below.


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
    assert "Total usable classroom capacity: 15" in shown[0][1]
    assert "Largest exam: 50 students" in shown[0][1]
    assert "Shortfall: 35" in shown[0][1]
    app.processEvents()
    screen.close()


# ── Spec §4.3: update-mode load with bad StudentCount leaves state unchanged ──

def test_update_mode_bad_student_count_leaves_controller_state_unchanged(
    tmp_path, monkeypatch
):
    """Regression: loading a bad courses file via Update mode when Feature 4 is ON
    must leave self._courses byte-for-byte unchanged (spec §4.3 pre-merge guard).

    Prior state: 1 course (id=11111) with a valid StudentCount of 30.
    Action:      Update-mode load of a file that introduces a new offering for
                 11111 without a StudentCount — triggering MissingStudentCountError.
    Expected:    controller._courses still has exactly the original 1 offering;
                 an error dialog is shown; the courses label reflects the abort.
    """
    app = _get_qapp()

    prior_file = tmp_path / "prior.txt"
    prior_file.write_text(
        "Calculus\n11111\nDr. Cohen\n83101, 1, FALL, Obligatory, 30\nExam\n",
        encoding="utf-8",
    )
    bad_update_file = tmp_path / "bad_update.txt"
    bad_update_file.write_text(
        "Calculus\n11111\nDr. Cohen\n83102, 1, FALL, Elective\nExam\n",
        encoding="utf-8",
    )

    controller = DesktopController()
    controller.load_courses(prior_file)
    snapshot_ids = [c.id for c in controller._courses]
    snapshot_offerings = {
        (o.program_id, o.year, o.semester, o.requirement, o.student_count)
        for c in controller._courses
        for o in c.offerings
    }
    assert len(controller._courses) == 1

    controller._feature4_enabled = True
    screen = ConfigScreen(controller)

    errors_shown = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: errors_shown.append(args),
    )

    _patch_file_dialog(monkeypatch, [bad_update_file])
    _set_load_mode(screen, "Update")
    screen._load_courses()
    app.processEvents()

    # State must be completely unchanged.
    after_ids = [c.id for c in controller._courses]
    after_offerings = {
        (o.program_id, o.year, o.semester, o.requirement, o.student_count)
        for c in controller._courses
        for o in c.offerings
    }
    assert after_ids == snapshot_ids, "Course IDs changed after rejected update-mode load"
    assert after_offerings == snapshot_offerings, "Offerings changed after rejected load"

    # Error dialog must have been shown.
    assert errors_shown, "No error dialog shown for MissingStudentCountError"

    # Label must reflect the abort, not a success count.
    label_text = screen._files_card.courses_label.text()
    assert any(
        kw in label_text for kw in ("StudentCount", "aborted", "Missing")
    ), f"Courses label did not reflect abort: {label_text!r}"

    screen.close()


# ── File loading modes update controller state ─────────────────────

def test_config_screen_course_load_replace_then_update(tmp_path, monkeypatch):
    """ConfigScreen course loading drives both load modes end-to-end:

    Replace clears prior state, a second Replace swaps it out entirely, and
    Update merges new offerings into existing courses while refreshing the
    programme list and the courses label. Consolidates the former separate
    replace/update course-load tests.
    """
    app = _get_qapp()

    first = tmp_path / "courses_first.txt"
    second = tmp_path / "courses_second.txt"
    update = tmp_path / "courses_update.txt"
    _write_courses_one(first)
    _write_courses_replacement(second)
    _write_courses_update(update)

    controller = DesktopController()
    screen = ConfigScreen(controller)
    screen.show()
    app.processEvents()

    _patch_file_dialog(monkeypatch, [first, second, update])

    # First Replace load.
    _set_load_mode(screen, "Replace")
    screen._load_courses()
    assert [course.id for course in controller.courses] == ["11111"]
    assert controller.get_programme_ids() == ["83101"]
    assert len(screen._prog_rows) == 1
    assert "courses_first.txt" in screen._files_card.courses_label.text()

    # Second Replace swaps the whole course set out.
    screen._load_courses()
    assert [course.id for course in controller.courses] == ["33333"]
    assert controller.get_programme_ids() == ["83108"]
    assert len(screen._prog_rows) == 1
    assert "courses_second.txt" in screen._files_card.courses_label.text()

    # Reset to a known base, then Update merges offerings into existing courses.
    _patch_file_dialog(monkeypatch, [first, update])
    _set_load_mode(screen, "Replace")
    screen._load_courses()
    assert [course.id for course in controller.courses] == ["11111"]

    _set_load_mode(screen, "Update")
    screen._load_courses()
    assert [course.id for course in controller.courses] == ["11111", "22222"]

    calculus = next(course for course in controller.courses if course.id == "11111")
    offering_keys = {
        (offering.program_id, offering.year, offering.semester, offering.requirement)
        for offering in calculus.offerings
    }
    assert ("83101", 1, "FALL", "Obligatory") in offering_keys
    assert ("83108", 1, "FALL", "Elective") in offering_keys
    assert set(controller.get_programme_ids()) == {"83101", "83108"}
    assert len(screen._prog_rows) == 2
    assert "courses_update.txt" in screen._files_card.courses_label.text()

    screen.close()


def test_config_screen_period_load_replace_then_update(tmp_path, monkeypatch):
    """ConfigScreen period loading drives both load modes end-to-end:

    Replace swaps the period set, a second Replace replaces it with a different
    semester/moed, and Update updates the matching period key in place.
    Consolidates the former separate replace/update period-load tests.
    """
    app = _get_qapp()

    first = tmp_path / "periods_first.txt"
    second = tmp_path / "periods_second.txt"
    update = tmp_path / "periods_update.txt"
    _write_periods_one(first)
    _write_periods_replacement(second)
    _write_periods_update(update)

    controller = DesktopController()
    screen = ConfigScreen(controller)
    screen.show()
    app.processEvents()

    _patch_file_dialog(monkeypatch, [first, second])

    # First Replace load.
    _set_load_mode(screen, "Replace")
    screen._load_dates()
    assert [p.get_key() for p in controller.get_exam_periods()] == ["FALL - Aleph"]
    assert "periods_first.txt" in screen._files_card.dates_label.text()
    assert "1 exam period(s) loaded" in screen._status_label.text()

    # Second Replace swaps to a different semester/moed.
    screen._load_dates()
    assert [p.get_key() for p in controller.get_exam_periods()] == ["SPRI - Bet"]
    assert "periods_second.txt" in screen._files_card.dates_label.text()

    # Reset to the base FALL period, then Update the matching key in place.
    _patch_file_dialog(monkeypatch, [first, update])
    _set_load_mode(screen, "Replace")
    screen._load_dates()
    original = controller.get_exam_periods()[0]
    assert original.get_key() == "FALL - Aleph"
    assert original.date_ranges[0][0].day == 5

    _set_load_mode(screen, "Update")
    screen._load_dates()
    updated = controller.get_exam_periods()
    assert len(updated) == 1
    assert updated[0].get_key() == "FALL - Aleph"
    assert updated[0].date_ranges[0][0].day == 12
    assert updated[0].date_ranges[0][1].day == 16
    assert "periods_update.txt" in screen._files_card.dates_label.text()

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


def test_generate_emits_loading_state_before_poller_starts(monkeypatch):
    app, controller, screen = _generation_ready_config_screen()
    events: list[str] = []
    emitted_payloads: list[tuple] = []
    poller_start_calls: list[tuple] = []

    def record_generation_started(payload):
        events.append("generation_started")
        emitted_payloads.append(payload)

    def fake_start(selected, color_map, allow_unassigned):
        events.append("poller_start")
        poller_start_calls.append((selected, color_map, allow_unassigned))

    screen.generation_started.connect(record_generation_started)
    monkeypatch.setattr(screen._poller, "start", fake_start)

    screen._on_generate()

    assert events == ["generation_started"]
    assert len(emitted_payloads) == 1
    emitted_selected, emitted_color_map = emitted_payloads[0]
    assert emitted_selected == ["83101"]
    assert set(emitted_color_map) == {"83101"}
    assert poller_start_calls == []
    assert controller.heavy_task_kind == "generation"
    assert "Starting generation" in screen._status_label.text()

    _wait_for_qt_timers(80)

    assert events == ["generation_started", "poller_start"]
    assert poller_start_calls == [
        (emitted_selected, emitted_color_map, False)
    ]

    screen.close()
    app.processEvents()


def test_delayed_generation_start_failure_cleans_heavy_task(monkeypatch):
    app, controller, screen = _generation_ready_config_screen()
    settings_states: list[bool] = []
    heavy_events: list[tuple[str, bool]] = []

    def fail_start(_selected, _color_map, _allow_unassigned):
        raise RuntimeError("poller start failed")

    monkeypatch.setattr(screen._poller, "start", fail_start)
    monkeypatch.setattr(
        screen,
        "_notify_settings_state",
        lambda is_running: settings_states.append(is_running),
    )
    screen.heavy_task_state_changed.connect(
        lambda kind, active: heavy_events.append((kind, active))
    )

    assert controller.begin_heavy_task("generation") is True
    controller.performance_metrics.start_generation(LOAD_BATCH_SIZE)
    screen._gen_btn.setEnabled(False)

    with pytest.raises(RuntimeError, match="poller start failed"):
        screen._start_generation_polling(
            ["83101"],
            {"83101": "#2563EB"},
            False,
        )

    assert controller.heavy_task_kind is None
    assert heavy_events == [("generation", False)]
    assert settings_states == [False]
    assert screen._gen_btn.isEnabled() is True

    screen.close()
    app.processEvents()


def test_first_period_ready_appends_before_hiding_loading(monkeypatch):
    app = _get_qapp()
    controller = DesktopController()
    screen = InputScreen(controller)
    screen.show()
    app.processEvents()

    screen._config.generation_started.emit((["83101"], {"83101": "#2563EB"}))
    app.processEvents()
    assert screen._results._content_stack.currentIndex() == 0
    assert screen._results._spin_timer.isActive() is True

    events: list[tuple[str, int]] = []
    appended_batches: list[dict[str, list[Schedule]]] = []
    original_hide_loading = screen._results.hide_loading

    def fake_append_period(
        schedules_by_period,
        _courses_by_id,
        _prog_color_map,
        _truncated_periods,
    ):
        events.append(("append", screen._results._content_stack.currentIndex()))
        appended_batches.append(schedules_by_period)
        screen._results._workspace.setCurrentIndex(2)
        screen._results._results_loaded = True

    def record_hide_loading():
        events.append(("hide", screen._results._content_stack.currentIndex()))
        original_hide_loading()

    monkeypatch.setattr(screen._results, "append_period", fake_append_period)
    monkeypatch.setattr(screen._results, "hide_loading", record_hide_loading)

    schedules_by_period = {"FALL - Aleph": []}
    screen._config.period_ready.emit(
        (
            ["83101"],
            schedules_by_period,
            {},
            {"83101": "#2563EB"},
            set(),
        )
    )
    app.processEvents()

    assert events == [("append", 0), ("hide", 0)]
    assert appended_batches == [schedules_by_period]
    assert screen._results._content_stack.currentIndex() == 1
    assert screen._results._spin_timer.isActive() is False
    assert screen._stacked.currentIndex() == 1
    assert screen._results._results_loaded is True

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


def test_capacity_warning_uses_newly_selected_programmes_not_stale_ones(monkeypatch):
    """Regression: capacity warning must fire based on the *current* UI selection.

    Old flow: _confirm_capacity_warning() ran before set_selected_programs(),
    so the warning was calculated using stale selected_programs.

    New flow: set_selected_programs(selected) runs first, then the warning.
    This test verifies: switching from programme A to B in the UI, where only B
    has a capacity shortfall, causes the warning to appear.
    """
    app = _get_qapp()

    PROG_A = "83101"
    PROG_B = "83102"

    course = Course(
        "99999",
        "Big Exam",
        "Dr. Test",
        "Exam",
        [
            CourseOffering(PROG_A, 1, "FALL", "Obligatory", 5),    # fits in room
            CourseOffering(PROG_B, 1, "FALL", "Obligatory", 999),  # shortfall
        ],
    )

    controller = DesktopController()
    controller._feature4_enabled = True
    controller._classrooms = [Classroom("Room 1", 50)]
    controller._time_slots = [TimeSlot(time(9, 0))]
    controller._proctor_config = ProctorConfig(20)
    controller._courses = [course]
    controller._exam_periods = [
        ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 9))])
    ]
    controller._selected_programs = [PROG_A]  # stale — no shortfall for A

    screen = ConfigScreen(controller)
    # Simulate user switching UI selection to PROG_B before clicking Generate.
    monkeypatch.setattr(screen, "_get_selected_ids", lambda: [PROG_B])

    shown_warnings: list[tuple] = []

    def capture_warning(_parent, title, text, buttons, default):
        shown_warnings.append((title, text))
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "warning", capture_warning)

    screen._on_generate()
    app.processEvents()

    assert shown_warnings, "Capacity warning must fire for the newly selected PROG_B"
    assert "Insufficient Classroom Capacity" in shown_warnings[0][0]
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
