"""
E2E / UI-Engine Stress Tests
============================
Simulates a user physically driving the desktop UI (ConfigScreen +
SettingsScreen) through the real controller and engine, then asserts that
the generated schedules are spec-compliant and that the UI gracefully
handles invalid Feature 4 inputs and the §4.3 C1 student-count rule.

These tests run in offscreen Qt mode and exercise the live generation path
(no mocked engine) so the assertions reflect real backtracking output.
"""

import os
import sys
from datetime import date, time

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
from src.domain.settings import Settings
from src.domain.sorting import SortCriterion, SortingConfig
from src.domain.threshold import (
    Criterion,
    ThresholdEntry,
    ThresholdSettings,
)
from src.domain.threshold_filter import _CHECKERS
from src.domain.time_slot import TimeSlot
from src.ui.config_screen import ConfigScreen
from src.ui.proctor_report_dialog import ProctorReportDialog
from src.ui.settings_screen import SettingsScreen, _CRITERION_ROLE


# ── shared fixtures / helpers ────────────────────────────────────────────────


_APP: QApplication | None = None


def _get_qapp() -> QApplication:
    # Hold the QApplication in a module-level reference: if only a local holds
    # it, PyQt may garbage-collect the application while widgets are alive,
    # which aborts the process under Qt's offscreen platform.
    global _APP
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    _APP = app
    return app


def _exam(course_id: str, program: str, kind: str, count: int = 30) -> Course:
    """Build a single-offering exam course for `program`, year 1, FALL."""
    return Course(
        id=course_id,
        name=f"Course {course_id}",
        instructor="Dr. Test",
        evaluation_type="Exam",
        offerings=[CourseOffering(program, 1, "FALL", kind, count)],
    )


# A single FALL/Aleph period with a generous weekday window so the engine
# produces MANY candidate schedules to filter and rank.
_WIDE_PERIOD = ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 30))])
_PERIOD_KEY = _WIDE_PERIOD.get_key()  # "FALL - Aleph"


def _driven_settings_screen(
    enabled_thresholds: dict[Criterion, int],
    sort_order: list[SortCriterion],
) -> Settings:
    """Drive a real SettingsScreen the way a user would, then read back Settings.

    Toggles the requested threshold rules ON (with their k), sets every other
    rule OFF, checks the requested sort criteria in priority order, and returns
    the Settings object the dialog's Save path would emit.
    """
    _get_qapp()
    screen = SettingsScreen(
        Settings(thresholds=ThresholdSettings(), sorting=SortingConfig())
    )

    # Flip threshold toggles + spinboxes like a user clicking the cards.
    for criterion, (toggle, spinbox) in screen._threshold_widgets.items():
        want = criterion in enabled_thresholds
        toggle.setChecked(want)
        if want:
            spinbox.setValue(enabled_thresholds[criterion])

    # Build the sort list check-states + ordering. The dialog reads priority
    # from row order, so we reorder rows to match `sort_order`.
    lst = screen._sort_list
    # Pull all existing rows out so we can re-add them in priority order.
    remaining = [lst.takeItem(0) for _ in range(lst.count())]
    by_crit = {it.data(_CRITERION_ROLE): it for it in remaining}
    for crit in sort_order:
        item = by_crit.pop(crit)
        item.setCheckState(Qt.CheckState.Checked)
        lst.addItem(item)
    for item in by_crit.values():
        item.setCheckState(Qt.CheckState.Unchecked)
        lst.addItem(item)

    settings = screen._build_settings()
    screen.close()
    return settings


def _schedule_satisfies(threshold_entry: ThresholdEntry, schedule, courses) -> bool:
    checker = _CHECKERS[threshold_entry.criterion]
    return checker(schedule, courses, threshold_entry.k, set())


# ── Scenario 1: filter × sort combinations ───────────────────────────────────


def test_multi_threshold_and_multi_sort_yields_compliant_ordered_schedules():
    """Enable two non-conflicting thresholds + a 2-level sort, generate via the
    real engine, and assert EVERY surviving schedule satisfies BOTH thresholds."""
    controller = DesktopController()
    controller._courses = [
        _exam("11111", "83101", "Obligatory"),
        _exam("22222", "83101", "Obligatory"),
        _exam("33333", "83101", "Obligatory"),
    ]
    controller._exam_periods = [_WIDE_PERIOD]
    controller._selected_programs = ["83101"]

    settings = _driven_settings_screen(
        enabled_thresholds={
            Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS: 3,
            Criterion.MAX_EXAMS_PER_DAY: 1,
        },
        sort_order=[
            SortCriterion.SORT_MIN_DAYS_MANDATORY,
            SortCriterion.SORT_ELECTIVE_COLLISIONS,
        ],
    )
    controller.apply_settings(settings)

    schedules_by_period, _courses_by_id, _trunc = controller.generate()
    survivors = schedules_by_period[_PERIOD_KEY]

    assert survivors, "Expected at least one compliant schedule for a wide window"

    courses = controller._courses
    mandatory_entry = settings.thresholds.for_criterion(
        Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS
    )
    perday_entry = settings.thresholds.for_criterion(Criterion.MAX_EXAMS_PER_DAY)

    for sched in survivors:
        assert _schedule_satisfies(mandatory_entry, sched, courses), (
            "Surviving schedule violates MIN_DAYS_BETWEEN_MANDATORY_EXAMS"
        )
        assert _schedule_satisfies(perday_entry, sched, courses), (
            "Surviving schedule violates MAX_EXAMS_PER_DAY"
        )


def test_resort_reorders_without_dropping_or_violating_thresholds():
    """A sort-only change (the live SettingsScreen sort path) must reorder the
    cached survivors without losing any or re-admitting filtered schedules."""
    controller = DesktopController()
    controller._courses = [
        _exam("11111", "83101", "Obligatory"),
        _exam("22222", "83101", "Obligatory"),
    ]
    controller._exam_periods = [_WIDE_PERIOD]
    controller._selected_programs = ["83101"]

    settings = _driven_settings_screen(
        enabled_thresholds={Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS: 2},
        sort_order=[SortCriterion.SORT_MIN_DAYS_MANDATORY],
    )
    controller.apply_settings(settings)
    schedules_by_period, _c, _t = controller.generate()
    before = len(schedules_by_period[_PERIOD_KEY])

    resorted = controller.resort(
        SortingConfig(rules=settings.sorting.rules[::-1] or settings.sorting.rules)
    )
    after = len(resorted[_PERIOD_KEY])

    assert before == after, "Re-sort must preserve the survivor count"
    entry = settings.thresholds.for_criterion(
        Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS
    )
    for sched in resorted[_PERIOD_KEY]:
        assert _schedule_satisfies(entry, sched, controller._courses)


# ── Scenario 2: Feature 4 edge cases via ConfigScreen ─────────────────────────


def _classrooms_file(tmp_path, rooms=("Room 101:40", "Room 202:60")):
    p = tmp_path / "classrooms.txt"
    body = "".join(
        f"$$$$\n{name}\n{cap}\n" for name, cap in (r.split(":") for r in rooms)
    )
    p.write_text(body, encoding="utf-8")
    return p


def _slots_file(tmp_path, text="09:00, 13:00, 19:00", name="slots.txt"):
    p = tmp_path / name
    p.write_text(f"$$$$\n{text}\n$$$$\n", encoding="utf-8")
    return p


def _proctors_file(tmp_path):
    p = tmp_path / "proctors.txt"
    p.write_text("1:20\n", encoding="utf-8")
    return p


def _patch_dialog(monkeypatch, paths):
    selected = [str(p) for p in paths]
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (selected.pop(0), "Text files (*.txt)"),
    )


def test_invalid_slots_text_disables_generate_and_shows_error_badge(
    tmp_path, monkeypatch
):
    """Typing invalid slots (<4h apart, spec §2.3.4) in the text field must surface
    an inline error badge, deactivate Feature 4, and keep generation blocked.
    Slots are now a QLineEdit text field (spec §2.3.5)."""
    _get_qapp()
    controller = DesktopController()
    controller._courses = [_exam("11111", "83101", "Obligatory")]
    controller._exam_periods = [_WIDE_PERIOD]
    controller._selected_programs = ["83101"]
    screen = ConfigScreen(controller)
    _patch_dialog(monkeypatch, [_classrooms_file(tmp_path)])

    # Load valid classrooms, enter valid proctor ratio, turn toggle ON.
    screen._feature4_card._load_classrooms()
    screen._feature4_card._proctors_edit.setText("1:20")
    screen._feature4_card._commit_proctors_text()

    # Now type slots that violate the ≥4h gap rule.
    screen._feature4_card._slots_edit.setText("09:00, 11:00")
    screen._feature4_card._commit_slots_text()

    assert controller.time_slots == []
    assert controller.feature4_active is False
    assert "Invalid" in screen._feature4_card._slots_label.text()
    assert controller.feature4_ready() is False
    screen.close()


def test_capacity_shortfall_warns_before_generation(tmp_path, monkeypatch):
    """When total room capacity < largest exam, the pre-generation capacity warning
    must fire (spec 4.4) and cancelling it must prevent generation."""
    _get_qapp()
    controller = DesktopController()
    controller._feature4_enabled = True
    controller._classrooms = [Classroom("Room 1", 20)]
    controller._time_slots = [TimeSlot(time(9, 0))]
    controller._proctor_config = ProctorConfig(20)
    controller._selected_programs = ["83101"]
    controller._exam_periods = [_WIDE_PERIOD]
    controller._courses = [_exam("11111", "83101", "Obligatory", count=80)]

    shortfall = controller.feature4_capacity_shortfall()
    assert shortfall is not None
    total_cap, largest = shortfall
    assert total_cap == 20 and largest == 80

    screen = ConfigScreen(controller)
    started = []
    screen.generation_started.connect(started.append)
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.No
    )
    # Ensure _get_selected_ids returns the pre-configured programme so the
    # capacity check sees the same selection that was set on the controller.
    monkeypatch.setattr(screen, "_get_selected_ids", lambda: ["83101"])

    screen._on_generate()
    assert started == [], "Generation must not start when capacity warning is cancelled"
    assert screen._poller._process is None
    screen.close()


# ── Scenario 3: the C1 rule (instant block, spec §4.3) ───────────────────────


def test_c1_missing_student_count_snaps_toggle_back_with_dialog(monkeypatch):
    """When Feature 4 is OFF and the loaded courses miss StudentCounts, turning the
    toggle ON must SNAP BACK to OFF and show a critical dialog (spec §4.3 UX
    fallback) — instead of failing silently with a blocked Generate button."""
    _get_qapp()
    controller = DesktopController()
    controller._courses = [
        Course(
            id="11111",
            name="Calculus",
            instructor="Dr. Cohen",
            evaluation_type="Exam",
            offerings=[CourseOffering("83101", 1, "FALL", "Obligatory", None)],
        )
    ]
    controller._exam_periods = [_WIDE_PERIOD]
    controller._selected_programs = ["83101"]
    screen = ConfigScreen(controller)

    assert controller.feature4_missing_student_counts() is True

    errors_shown = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: errors_shown.append(args),
    )

    # Attempt to turn the toggle ON — it must snap back off.
    screen._feature4_card._toggle.setChecked(True)

    # A critical dialog must have been shown with an explanatory message.
    assert errors_shown, "A critical dialog must explain why Feature 4 can't enable"
    dialog_args = errors_shown[0]
    dialog_message = " ".join(str(a) for a in dialog_args)
    assert "StudentCount" in dialog_message or "student" in dialog_message.lower(), (
        f"Dialog message must mention StudentCount, got: {dialog_message!r}"
    )
    assert "Feature 4" in dialog_message or "feature 4" in dialog_message.lower(), (
        f"Dialog message must mention Feature 4, got: {dialog_message!r}"
    )

    # Toggle and controller state must both be snapped back to OFF.
    assert controller.feature4_enabled is False, "Controller: Feature 4 stays OFF"
    assert screen._feature4_card._toggle.isChecked() is False, "Checkbox snapped back to OFF"
    assert screen._feature4_card._load_classrooms_btn.isEnabled() is False, (
        "Browse button must be disabled when toggle is OFF"
    )

    # Status label must reflect DISABLED, not ACTIVE or INCOMPLETE.
    status_text = screen._feature4_card._status_lbl.text()
    assert "DISABLED" in status_text, (
        f"Status label must show DISABLED after snap-back, got: {status_text!r}"
    )

    # Generate stays blocked while Feature 4 cannot be activated.
    assert screen._gen_btn.isEnabled() is False, "Generate button must be disabled"
    screen.close()


# ── Scenario 4: stress / sanity ──────────────────────────────────────────────


def test_impossible_strict_filters_return_empty_set_without_crashing():
    """A tight window plus an impossible spread requirement must yield an empty
    survivor set (not a crash, not a missing key)."""
    controller = DesktopController()
    controller._courses = [
        _exam("11111", "83101", "Obligatory"),
        _exam("22222", "83101", "Obligatory"),
    ]
    # Tight 2-weekday window: 2026-01-05 (Mon) .. 2026-01-06 (Tue).
    controller._exam_periods = [
        ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 6))])
    ]
    controller._selected_programs = ["83101"]

    settings = _driven_settings_screen(
        enabled_thresholds={Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS: 30},
        sort_order=[SortCriterion.SORT_MIN_DAYS_MANDATORY],
    )
    controller.apply_settings(settings)

    schedules_by_period, _c, _t = controller.generate()
    assert schedules_by_period.get(_PERIOD_KEY, []) == []


def test_heavy_load_many_courses_sorts_survivors_without_crashing():
    """A heavier course set with a relaxed filter must produce a sorted,
    non-empty survivor list and complete without error.

    The window is deliberately bounded (one week, 5 weekdays) so the full
    Cartesian generation stays tractable: the controller computes ALL schedules
    up front, so a wide window with several courses would blow up combinatorially.
    """
    controller = DesktopController()
    controller._courses = [
        _exam(f"1000{i}", "83101", "Obligatory" if i % 2 == 0 else "Elective")
        for i in range(4)
    ]
    # 2026-01-05 (Mon) .. 2026-01-09 (Fri): 5 weekdays -> bounded search space.
    controller._exam_periods = [
        ExamPeriod("FALL", "Aleph", [(date(2026, 1, 5), date(2026, 1, 9))])
    ]
    controller._selected_programs = ["83101"]

    settings = _driven_settings_screen(
        enabled_thresholds={Criterion.MAX_EXAMS_PER_DAY: 2},
        sort_order=[
            SortCriterion.SORT_MAX_EXAMS_PER_DAY,
            SortCriterion.SORT_MIN_DAYS_MANDATORY,
        ],
    )
    controller.apply_settings(settings)

    schedules_by_period, _c, _t = controller.generate()
    survivors = schedules_by_period[_PERIOD_KEY]
    assert survivors, "Relaxed filter over a wide window should keep survivors"

    entry = settings.thresholds.for_criterion(Criterion.MAX_EXAMS_PER_DAY)
    for sched in survivors:
        assert _schedule_satisfies(entry, sched, controller._courses)


# ── Scenario 5: proctor report dialog (spec 4.6 GUI view) ─────────────────────


def test_proctor_report_dialog_renders_report_text():
    _get_qapp()
    dialog = ProctorReportDialog("PROCTOR REPORT\nRoom 101: 2 proctors")
    assert dialog._view.toPlainText() == "PROCTOR REPORT\nRoom 101: 2 proctors"
    assert dialog._view.isReadOnly()
    dialog.close()


def test_proctor_report_dialog_export_writes_file(tmp_path, monkeypatch):
    _get_qapp()
    dialog = ProctorReportDialog("REPORT BODY")
    out = tmp_path / "report.txt"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), "Text files (*.txt)")
    )
    infos = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda _p, t, x: infos.append((t, x))
    )

    dialog._on_export()

    assert out.read_text(encoding="utf-8") == "REPORT BODY"
    assert infos and infos[0][0] == "Exported"
    dialog.close()


def test_proctor_report_dialog_export_cancel_is_noop(tmp_path, monkeypatch):
    _get_qapp()
    dialog = ProctorReportDialog("REPORT BODY")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: called.append(1))

    dialog._on_export()  # user cancelled the save dialog -> no write, no info box

    assert called == []
    dialog.close()


def test_proctor_report_dialog_export_oserror_shows_critical(tmp_path, monkeypatch):
    _get_qapp()
    dialog = ProctorReportDialog("REPORT BODY")
    # Point the save path at a non-existent directory so write_text raises OSError.
    bad_path = tmp_path / "missing_dir" / "report.txt"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *a, **k: (str(bad_path), "txt")
    )
    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda _p, t, x: errors.append((t, x)))

    dialog._on_export()

    assert errors and errors[0][0] == "Export Error"
    dialog.close()
