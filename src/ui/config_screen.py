"""
Widget: ConfigScreen — Full-screen entry / configuration (Screen 0).

Layout
------
  Brand header   (fixed 64 px)
  Scroll area    (expands to fill window)
    └─ centred content (max 780 px wide)
         ├─ Steps pill
         ├─ Row: [Load Mode card] [Files card]
         └─ Study Programmes card
  Bottom footer  (fixed 76 px — Generate button ALWAYS visible here)

Signals
-------
generation_started(object)  → (selected_ids, prog_color_map)  IMMEDIATE on click
schedule_generated(object)  → full result tuple  when async subprocess finishes
generation_failed(str)      → error message
courses_changed(list[str])  → after courses or programme selection changes
periods_changed()           → after exam periods are (re)loaded
"""

import logging
import multiprocessing
import time
from datetime import date, timedelta
from pathlib import Path
from queue import Empty as _QueueEmpty

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.controller import DesktopController, RESULT_BATCH_SIZE, _run_generation_process
from src.domain.settings import Settings
from src.ui.settings_screen import SettingsScreen
from src.ui.assets.icons import BookIcon, CalendarIcon
from src.ui.period_utils import (
    STANDARD_PERIOD_ORDER as _STANDARD_PERIOD_ORDER,
    build_display_periods as _build_display_periods,
)
from src.ui.results_panel import _display_period_key
from src.ui.tokens import PROGRAMME_COLOURS, PROGRAM_NAMES_MAPPING

logger = logging.getLogger(__name__)

_LOGO_PNG = str(Path(__file__).parent / "assets" / "logo.png")

_MAX_PROGS = 5
_MAX_GEN_SECS = 180


def _section_lbl(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "font-size:10px; font-weight:700; color:#72778c;"
        " letter-spacing:0.6px; background:transparent;"
    )
    return lbl


def _card() -> QFrame:
    f = QFrame()
    f.setStyleSheet(
        "QFrame {"
        " background: rgba(255, 255, 255, 0.75);"
        " border: 1px solid rgba(255, 255, 255, 0.9);"
        " border-radius: 12px;"
        "}"
    )
    eff = QGraphicsDropShadowEffect()
    eff.setBlurRadius(18)
    eff.setColor(QColor(0, 67, 148, 13))
    eff.setOffset(0, 4)
    f.setGraphicsEffect(eff)
    return f


_VIEW_BTN_STYLE = (
    "QPushButton { background:rgba(0,67,148,0.07);"
    " border:1px solid rgba(0,67,148,0.2); border-radius:6px;"
    " padding:0px 10px; font-size:11px; font-weight:600; color:#004394; }"
    "QPushButton:hover:enabled { background:rgba(0,67,148,0.13); border-color:#004394; }"
    "QPushButton:disabled { color:#94A3B8; border-color:rgba(194,198,214,0.4);"
    " background:transparent; }"
)


class _ProgrammeRow(QWidget):
    """One programme row: checkbox · label · View Courses button."""

    toggled = pyqtSignal(str, bool)           # pid, is_checked
    view_courses_clicked = pyqtSignal(str)    # pid

    def __init__(self, pid: str, name: str, parent=None) -> None:
        super().__init__(parent)
        self._pid = pid

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        self._checkbox = QCheckBox()
        self._checkbox.setFixedSize(22, 22)
        self._checkbox.setStyleSheet(
            "QCheckBox::indicator { width:18px; height:18px; border-radius:5px;"
            " border:2px solid rgba(194,198,214,0.9); background:white; }"
            "QCheckBox::indicator:hover { border-color:#004394; }"
            "QCheckBox::indicator:checked { background:#004394; border-color:#004394; }"
        )
        layout.addWidget(self._checkbox)

        self._label = QLabel(f"\u200e{pid}  —  {name}")
        self._label.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._label.setStyleSheet(
            "font-size:13px; color:#171c20; font-weight:500; background:transparent;"
        )

        layout.addWidget(self._label)
        layout.addStretch(1)

        self._view_btn = QPushButton("View Courses ▶")

        self._view_btn.setEnabled(False)
        self._view_btn.setFixedHeight(26)
        self._view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._view_btn.setStyleSheet(_VIEW_BTN_STYLE)
        self._view_btn.clicked.connect(lambda: self.view_courses_clicked.emit(self._pid))
        layout.addWidget(self._view_btn)

        self._checkbox.stateChanged.connect(self._on_state_changed)

    def is_checked(self) -> bool:
        return self._checkbox.isChecked()

    def set_checked(self, checked: bool) -> None:
        self._checkbox.blockSignals(True)
        self._checkbox.setChecked(checked)
        self._checkbox.blockSignals(False)
        self._view_btn.setEnabled(checked)

    def set_label_color(self, color: str) -> None:
        self._label.setStyleSheet(
            f"font-size:13px; color:{color}; font-weight:500; background:transparent;"
        )

    def set_view_btn_enabled(self, has_courses: bool) -> None:
        self._view_btn.setEnabled(self._checkbox.isChecked() and has_courses)

    def _on_state_changed(self, state: int) -> None:
        checked = state == Qt.CheckState.Checked.value
        self._view_btn.setEnabled(checked)
        self.toggled.emit(self._pid, checked)


class ExamPeriodsEditorDialog(QDialog):
    """Modal dialog for editing exam period dates before generation (SRS §2.4)."""

    def __init__(self, controller: "DesktopController", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Exam Periods")
        self.setModal(True)
        self.setMinimumSize(950, 560)

        self._controller = controller
        self._editors: dict[str, object] = {}
        self._existing_period_keys: set[str] = {
            period.get_key()
            for period in self._controller.get_exam_periods()
        }
        self._activated_synthetic_period_keys: set[str] = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        tabs = QTabWidget()
        tabs.setUsesScrollButtons(True)
        tabs.setMovable(False)

        # Important:
        # The tabs already exist, but inactive tab text was almost white.
        # This stylesheet makes all semester/moed tabs readable.
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background: transparent;
            }

            QTabBar::tab {
                background: transparent;
                color: #374151;
                padding: 8px 18px;
                margin-right: 4px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
                min-width: 110px;
            }

            QTabBar::tab:hover {
                background: rgba(0, 90, 194, 0.08);
                color: #005ac2;
            }

            QTabBar::tab:selected {
                background: #9CA3AF;
                color: #FFFFFF;
                font-weight: 700;
            }

            QTabBar::tab:disabled {
                color: #9CA3AF;
            }
        """)

        from src.ui.date_editor import DateEditorWidget

        self._tabs = tabs

        for period in _build_display_periods(self._controller):
            key = period.get_key()

            if not period.date_ranges:
                tabs.addTab(
                    self._build_missing_period_tab(period),
                    _display_period_key(key),
                )
                continue

            editor = DateEditorWidget(period)
            editor.period_changed.connect(lambda k=key: self._sync(k))

            self._editors[key] = editor
            tabs.addTab(editor, _display_period_key(key))

        root.addWidget(tabs)

        close_row = QHBoxLayout()
        close_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setFixedSize(110, 36)
        close_btn.clicked.connect(self.accept)

        close_row.addWidget(close_btn)
        root.addLayout(close_row)

    def _build_missing_period_tab(self, period: "ExamPeriod") -> QWidget:
        """Create a tab for a missing exam period with an activation button."""
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        missing_lbl = QLabel(
            "No exam period dates are defined for this semester/moed."
        )
        missing_lbl.setWordWrap(True)
        missing_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        missing_lbl.setStyleSheet(
            "background: #FEF3C7;"
            "color: #92400E;"
            "border: 1px solid #F59E0B;"
            "border-radius: 8px;"
            "padding: 10px 14px;"
            "font-size: 12px;"
            "font-weight: 600;"
        )

        create_btn = QPushButton("＋ Define exam period dates")
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.setFixedHeight(36)
        create_btn.setStyleSheet(
            "QPushButton {"
            " background: #005ac2;"
            " color: white;"
            " border: none;"
            " border-radius: 8px;"
            " padding: 8px 16px;"
            " font-size: 12px;"
            " font-weight: 700;"
            "}"
            "QPushButton:hover {"
            " background: #004494;"
            "}"
        )
        create_btn.clicked.connect(
            lambda _=False, p=period: self._activate_missing_period(p)
        )

        layout.addWidget(missing_lbl)
        layout.addWidget(create_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

        return wrapper

    def _activate_missing_period(self, period: "ExamPeriod") -> None:
        """Convert a missing display-only period into a real editable period."""
        from src.domain.exam_period import ExamPeriod
        from src.ui.date_editor import DateEditorWidget

        key = period.get_key()
        start = date.today()
        end = start + timedelta(days=13)

        new_period = ExamPeriod(
            semester=period.semester,
            moed=period.moed,
            date_ranges=[(start, end)],
            excluded_dates=set(),
        )

        self._activated_synthetic_period_keys.add(key)

        editor = DateEditorWidget(new_period)
        editor.period_changed.connect(lambda k=key: self._sync(k))
        self._editors[key] = editor

        tab_label = _display_period_key(key)
        tab_index = -1

        for i in range(self._tabs.count()):
            if self._tabs.tabText(i) == tab_label:
                tab_index = i
                break

        if tab_index == -1:
            self._tabs.addTab(editor, tab_label)
            self._tabs.setCurrentWidget(editor)
        else:
            self._tabs.removeTab(tab_index)
            self._tabs.insertTab(tab_index, editor, tab_label)
            self._tabs.setCurrentIndex(tab_index)

        self._sync(key)

    def _sync(self, changed_key: str | None = None) -> None:
        """
        Sync editor changes back to the controller.

        Existing periods are always updated.
        Synthetic standard periods are added only after the user edits that
        specific synthetic tab.
        """
        if changed_key and changed_key not in self._existing_period_keys:
            self._activated_synthetic_period_keys.add(changed_key)

        edited_by_key = {
            key: editor.get_exam_period()
            for key, editor in self._editors.items()
        }

        updated = []

        for period in self._controller.get_exam_periods():
            key = period.get_key()
            updated.append(edited_by_key.get(key, period))

        existing_updated_keys = {period.get_key() for period in updated}

        for semester, moed in _STANDARD_PERIOD_ORDER:
            key = f"{semester} - {moed}"

            if (
                key in self._activated_synthetic_period_keys
                and key in edited_by_key
                and key not in existing_updated_keys
            ):
                updated.append(edited_by_key[key])
                existing_updated_keys.add(key)

        deduped = []
        seen_keys = set()

        for period in updated:
            key = period.get_key()

            if key in seen_keys:
                continue

            deduped.append(period)
            seen_keys.add(key)

        self._controller.update_exam_periods(deduped)


class ConfigScreen(QWidget):
    """Full-screen configuration (Screen 0)."""

    generation_started = pyqtSignal(object)
    schedule_generated = pyqtSignal(object)
    generation_failed = pyqtSignal(str)
    courses_changed = pyqtSignal(list)
    periods_changed = pyqtSignal()

    def __init__(self, controller: DesktopController, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._gen_process: multiprocessing.Process | None = None
        self._poll_timer: QTimer | None = None
        self._result_queue: multiprocessing.Queue | None = None
        self._pending_selected: list[str] = []
        self._pending_color_map: dict[str, str] = {}
        self._gen_start_time: float = 0.0
        self._dead_ticks: int = 0
        self._settings_dialog: SettingsScreen | None = None
        self._allow_unassigned_generation = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self._build_scroll_area(), 1)
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setObjectName("appHeader")
        hdr.setFixedHeight(80)

        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)
        hl.setSpacing(12)

        logo = QLabel()
        logo.setStyleSheet("background: transparent; border: none;")
        logo.setFixedSize(32, 32)

        pix = QPixmap(_LOGO_PNG)
        if not pix.isNull():
            logo.setPixmap(
                pix.scaled(
                    32,
                    32,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        hl.addWidget(logo)

        brand = QLabel("Syncacademic")
        brand.setStyleSheet(
            "font-size: 22px; font-weight: 800; color: #005ac2;"
            " letter-spacing: -0.5px; background: transparent;"
        )

        tagline = QLabel("Academic Command Center")
        tagline.setStyleSheet(
            "font-size: 12px; color: #42474e; font-weight: 500; background: transparent;"
        )

        hl.addWidget(brand)
        hl.addWidget(tagline)
        hl.addStretch()

        settings_btn = QPushButton("⚙  Settings")
        settings_btn.setObjectName("settingsBtn")
        settings_btn.setFixedHeight(32)
        settings_btn.setStyleSheet(
            "QPushButton#settingsBtn {"
            " background: rgba(0,90,194,0.08); border: 1px solid rgba(0,90,194,0.25);"
            " border-radius: 6px; padding: 0 14px;"
            " font-size: 13px; font-weight: 600; color: #005ac2;"
            "}"
            "QPushButton#settingsBtn:hover { background: rgba(0,90,194,0.15); }"
            "QPushButton#settingsBtn:pressed { background: rgba(0,90,194,0.25); }"
        )
        settings_btn.clicked.connect(self._on_open_settings)
        hl.addWidget(settings_btn)

        return hdr

    def _build_scroll_area(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")

        outer = QWidget()
        outer.setObjectName("configScrollOuter")
        outer.setStyleSheet("QWidget#configScrollOuter { background:transparent; }")

        ol = QHBoxLayout(outer)
        ol.setContentsMargins(32, 32, 32, 32)

        content = QWidget()
        content.setMaximumWidth(900)
        content.setObjectName("configScrollContent")
        content.setStyleSheet("QWidget#configScrollContent { background:transparent; }")

        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(20)

        steps_row = QWidget()
        steps_row.setObjectName("configStepsRow")
        steps_row.setStyleSheet("QWidget#configStepsRow { background:transparent; }")

        sl = QHBoxLayout(steps_row)
        sl.setContentsMargins(0, 4, 0, 4)
        sl.setSpacing(0)
        sl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for i, (icon, text, active) in enumerate([
            ("①", "Load files", True),
            ("②", "Select programmes", False),
            ("③", "Generate", False),
        ]):
            if i > 0:
                div = QLabel("  ——  ")
                div.setStyleSheet(
                    "color: rgba(194, 198, 214, 0.9);"
                    " background: transparent; font-size: 11px;"
                )
                sl.addWidget(div)

            step = QLabel(f"{icon}  {text}")
            step.setStyleSheet(
                f"font-size: 13px; font-weight: {'700' if active else '500'};"
                f" color: {'#004394' if active else '#42474e'};"
                " background: transparent;"
            )
            sl.addWidget(step)

        cl.addWidget(steps_row)

        top = QHBoxLayout()
        top.setSpacing(16)
        top.addWidget(self._build_mode_card(), 1)
        top.addWidget(self._build_files_card(), 1)

        cl.addLayout(top)
        cl.addWidget(self._build_prog_card())
        cl.addWidget(self._build_periods_card())
        cl.addWidget(self._build_feature4_card())

        self._gen_btn = QPushButton("▶  Generate Schedule")
        self._gen_btn.setObjectName("generateBtn")
        self._gen_btn.setEnabled(False)
        self._gen_btn.setFixedHeight(44)
        self._gen_btn.setFixedWidth(220)
        self._gen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gen_btn.clicked.connect(self._on_generate)

        cl.addWidget(self._gen_btn, 0, Qt.AlignmentFlag.AlignRight)
        cl.addStretch(1)

        ol.addStretch(1)
        ol.addWidget(content, 0)
        ol.addStretch(1)

        scroll.setWidget(outer)
        return scroll

    def _build_mode_card(self) -> QFrame:
        c = _card()

        vl = QVBoxLayout(c)
        vl.setContentsMargins(20, 18, 20, 18)
        vl.setSpacing(10)
        vl.addWidget(_section_lbl("LOAD MODE"))

        self._mode_group = QButtonGroup(self)
        self._mode_btn_frame_pairs: list[tuple[QRadioButton, QFrame]] = []

        radio_style = (
            "QRadioButton { font-size:14px; font-weight:600; color:#171c20;"
            " spacing:10px; background:transparent; }"
            "QRadioButton::indicator { width:18px; height:18px; border-radius:9px;"
            " border:2px solid rgba(194,198,214,0.9); background:white; }"
            "QRadioButton::indicator:hover { border-color:#004394; }"
            "QRadioButton::indicator:checked { border:5px solid #004394;"
            " background:white; border-radius:9px; }"
        )

        for label, hint_text in (
            ("Replace", "Clear all existing data"),
            ("Update", "Merge with existing data"),
        ):
            option_frame = QFrame()
            option_frame.setCursor(Qt.CursorShape.PointingHandCursor)

            fl = QVBoxLayout(option_frame)
            fl.setContentsMargins(0, 0, 0, 0)
            fl.setSpacing(0)

            rb_row = QWidget()
            rb_row.setStyleSheet("background:transparent;")

            rl = QHBoxLayout(rb_row)
            rl.setContentsMargins(14, 12, 14, 4)
            rl.setSpacing(10)

            rb = QRadioButton(label)
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            rb.setStyleSheet(radio_style)

            self._mode_group.addButton(rb)

            rl.addWidget(rb)
            rl.addStretch()

            hint = QLabel(hint_text)
            hint.setContentsMargins(42, 0, 14, 10)
            hint.setStyleSheet(
                "font-size:12px; color:#42474e; background:transparent;"
            )

            fl.addWidget(rb_row)
            fl.addWidget(hint)

            rb.toggled.connect(lambda _: self._update_mode_card_styles())
            option_frame.mousePressEvent = lambda event, _rb=rb: _rb.setChecked(True)
            self._mode_btn_frame_pairs.append((rb, option_frame))
            vl.addWidget(option_frame)

        self._mode_group.buttons()[0].setChecked(True)
        self._update_mode_card_styles()

        vl.addStretch()
        return c

    def _update_mode_card_styles(self) -> None:
        checked = self._mode_group.checkedButton()

        for btn, frame in self._mode_btn_frame_pairs:
            if btn is checked:
                frame.setStyleSheet(
                    "QFrame { background:rgba(0,67,148,0.08);"
                    " border:1px solid rgba(194,198,214,0.5); border-radius:10px; }"
                )
            else:
                frame.setStyleSheet(
                    "QFrame { background:rgba(255,255,255,0.6);"
                    " border:1px solid rgba(194,198,214,0.5); border-radius:10px; }"
                )

    def _build_files_card(self) -> QFrame:
        c = _card()

        vl = QVBoxLayout(c)
        vl.setContentsMargins(20, 18, 20, 18)
        vl.setSpacing(10)
        vl.addWidget(_section_lbl("FILES"))

        specs = [
            (
                BookIcon(14, "#004394"),
                "Courses",
                "Load Courses",
                "_load_courses_btn",
                "_courses_label",
                self._load_courses,
            ),
            (
                CalendarIcon(14, "#004394"),
                "Exam Periods",
                "Load Periods",
                "_load_periods_btn",
                "_dates_label",
                self._load_dates,
            ),
        ]

        file_btn_style = (
            "QPushButton { background:rgba(222,227,235,0.9);"
            " border:1px solid rgba(194,198,214,0.5); border-radius:8px;"
            " padding:5px 12px; font-size:12px; font-weight:600; color:#171c20; }"
            "QPushButton:hover { background:rgba(0,67,148,0.08);"
            " border-color:#004394; color:#004394; }"
        )

        for icon, title, btn_text, btn_attr, lbl_attr, slot in specs:
            btn = QPushButton(btn_text)
            btn.setFixedWidth(110)
            btn.setStyleSheet(file_btn_style)
            btn.clicked.connect(slot)

            lbl = QLabel("No file loaded")
            lbl.setStyleSheet(
                "font-size:11px; color:#72778c; background:transparent;"
            )

            setattr(self, btn_attr, btn)
            setattr(self, lbl_attr, lbl)

            row = QFrame()
            row.setStyleSheet(
                "QFrame { background:transparent; border-radius:8px; border:none; }"
                "QFrame:hover { background:rgba(0,67,148,0.04); }"
            )

            hl = QHBoxLayout(row)
            hl.setContentsMargins(10, 8, 10, 8)
            hl.setSpacing(10)

            hl.addWidget(icon)

            title_lbl = QLabel(title)
            title_lbl.setStyleSheet(
                "font-size:14px; font-weight:600; color:#171c20; background:transparent;"
            )

            hl.addWidget(title_lbl)
            hl.addStretch()
            hl.addWidget(btn)
            hl.addWidget(lbl)

            vl.addWidget(row)

        return c

    def _build_prog_card(self) -> QFrame:
        c = _card()

        vl = QVBoxLayout(c)
        vl.setContentsMargins(20, 18, 20, 18)
        vl.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.addWidget(_section_lbl("STUDY PROGRAMMES  (max 5)"))
        hdr.addStretch()

        self._prog_count_lbl = QLabel("0 / 5 selected")
        self._prog_count_lbl.setStyleSheet(
            "font-size:11px; color:#64748B; background:transparent;"
        )

        hdr.addWidget(self._prog_count_lbl)
        vl.addLayout(hdr)

        self._prog_placeholder = QLabel(
            "Load a courses file to see programmes here."
        )
        self._prog_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._prog_placeholder.setStyleSheet(
            "font-size:11px; color:#94A3B8; padding:16px 8px; background:transparent;"
        )
        vl.addWidget(self._prog_placeholder)

        self._prog_rows: dict[str, _ProgrammeRow] = {}

        self._prog_rows_container = QWidget()
        self._prog_rows_container.setStyleSheet("background: transparent;")
        self._prog_rows_layout = QVBoxLayout(self._prog_rows_container)
        self._prog_rows_layout.setContentsMargins(4, 4, 4, 4)
        self._prog_rows_layout.setSpacing(2)
        self._prog_rows_layout.addStretch()

        prog_scroll = QScrollArea()
        prog_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        prog_scroll.setWidgetResizable(True)
        prog_scroll.setFixedHeight(160)
        prog_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        prog_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        prog_scroll.setWidget(self._prog_rows_container)
        prog_scroll.setStyleSheet(
            "QScrollArea { border:1px solid rgba(194,198,214,0.4); border-radius:10px;"
            " background:rgba(255,255,255,0.75); }"
        )
        prog_scroll.setVisible(False)
        self._prog_scroll = prog_scroll

        vl.addWidget(self._prog_scroll)

        return c

    def _build_periods_card(self) -> QFrame:
        c = _card()

        vl = QVBoxLayout(c)
        vl.setContentsMargins(20, 18, 20, 18)
        vl.setSpacing(10)
        vl.addWidget(_section_lbl("EXAM PERIODS"))

        self._periods_summary_lbl = QLabel("No periods loaded")
        self._periods_summary_lbl.setStyleSheet(
            "font-size:12px; color:#42474e; background:transparent;"
        )
        vl.addWidget(self._periods_summary_lbl)

        self._edit_periods_btn = QPushButton("Edit Exam Periods ▶")
        self._edit_periods_btn.setEnabled(False)
        self._edit_periods_btn.setFixedHeight(32)
        self._edit_periods_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_periods_btn.setStyleSheet(
            "QPushButton { color:#004394; border:1px solid #004394;"
            " border-radius:6px; padding:0 14px; font-size:12px; font-weight:600;"
            " background:rgba(0,67,148,0.06); }"
            "QPushButton:hover:enabled { background:rgba(0,67,148,0.12); }"
            "QPushButton:disabled { color:#aaa; border-color:#ccc; }"
        )
        self._edit_periods_btn.clicked.connect(self._on_edit_periods)

        vl.addWidget(self._edit_periods_btn)

        return c

    def _refresh_periods_card(self) -> None:
        periods = self._controller.get_exam_periods()

        if not periods:
            self._periods_summary_lbl.setText("No periods loaded")
            self._edit_periods_btn.setEnabled(False)
            return

        display_names = [
            "FALL — Aleph",
            "FALL — Bet",
            "SPRING — Aleph",
            "SPRING — Bet",
            "SUMMER — Aleph",
            "SUMMER — Bet",
        ]

        self._periods_summary_lbl.setText(
            "Editable exam periods:\n" + ", ".join(display_names)
        )
        self._edit_periods_btn.setEnabled(True)

    def _build_feature4_card(self) -> QFrame:
        """Build the optional classroom-assignment input card."""
        c = _card()
        self._feature4_card = c

        vl = QVBoxLayout(c)
        vl.setContentsMargins(20, 18, 20, 18)
        vl.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(_section_lbl("FEATURE 4 - CLASSROOM ASSIGNMENT"))
        header.addStretch()

        self._feature4_status = QLabel()
        self._feature4_status.setFixedHeight(24)
        header.addWidget(self._feature4_status)
        vl.addLayout(header)

        description = QLabel(
            "Optional. Load all three valid files to assign classrooms, time slots, "
            "and recommended proctor counts."
        )
        description.setWordWrap(True)
        description.setStyleSheet(
            "font-size:11px; color:#64748B; background:transparent;"
        )
        vl.addWidget(description)

        file_specs = [
            (
                "Classrooms",
                "Load Classrooms",
                "_load_classrooms_btn",
                "_classrooms_label",
                self._load_classrooms,
            ),
            (
                "Time Slots",
                "Load Slots",
                "_load_slots_btn",
                "_slots_label",
                self._load_slots,
            ),
            (
                "Proctor Config",
                "Load Proctors",
                "_load_proctors_btn",
                "_proctors_label",
                self._load_proctors,
            ),
        ]

        for title, btn_text, btn_attr, lbl_attr, handler in file_specs:
            row = QHBoxLayout()
            title_lbl = QLabel(title)
            title_lbl.setMinimumWidth(105)
            title_lbl.setStyleSheet(
                "font-size:12px; font-weight:600; color:#171c20; background:transparent;"
            )

            btn = QPushButton(btn_text)
            btn.setFixedWidth(120)
            btn.clicked.connect(handler)

            status = QLabel("Missing")
            status.setWordWrap(True)
            status.setStyleSheet(self._feature4_input_style("missing"))

            setattr(self, btn_attr, btn)
            setattr(self, lbl_attr, status)

            row.addWidget(title_lbl)
            row.addWidget(btn)
            row.addWidget(status, 1)
            vl.addLayout(row)

        self._refresh_feature4_status()
        return c

    @staticmethod
    def _feature4_input_style(state: str) -> str:
        colors = {
            "missing": ("#92400E", "#FEF3C7"),
            "valid": ("#047857", "#D1FAE5"),
            "invalid": ("#B91C1C", "#FEE2E2"),
        }
        foreground, background = colors[state]
        return (
            f"font-size:11px; color:{foreground}; background:{background};"
            " border-radius:4px; padding:3px 7px;"
        )

    def _refresh_feature4_status(self) -> None:
        if self._controller.feature4_active:
            self._feature4_status.setText("ACTIVE")
            self._feature4_status.setStyleSheet(
                "font-size:11px; font-weight:800; color:#047857; background:#D1FAE5;"
                " border:1px solid #6EE7B7; border-radius:12px; padding:2px 10px;"
            )
            self._feature4_card.setStyleSheet(
                "QFrame { background:rgba(236,253,245,0.85);"
                " border:1px solid #6EE7B7; border-radius:12px; }"
            )
        else:
            self._feature4_status.setText("INACTIVE - optional inputs incomplete")
            self._feature4_status.setStyleSheet(
                "font-size:11px; font-weight:700; color:#64748B; background:#F1F5F9;"
                " border:1px solid #CBD5E1; border-radius:12px; padding:2px 10px;"
            )
            self._feature4_card.setStyleSheet(
                "QFrame { background:rgba(255,255,255,0.75);"
                " border:1px dashed #CBD5E1; border-radius:12px; }"
            )

    def _load_feature4_file(
        self,
        title: str,
        label: QLabel,
        loader,
        clearer,
        success_text,
    ) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {title} File",
            "",
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return

        try:
            result = loader(Path(path))
            label.setText(f"{Path(path).name} - {success_text(result)}")
            label.setStyleSheet(self._feature4_input_style("valid"))
        except Exception as exc:
            clearer()
            label.setText(f"{Path(path).name} - Invalid file")
            label.setStyleSheet(self._feature4_input_style("invalid"))
            logger.warning("Invalid Feature 4 %s file: %s", title, exc)
            QMessageBox.critical(
                self,
                "Invalid Feature 4 File",
                f"The selected {title.lower()} file is invalid.\n\n"
                f"File: {Path(path).name}\n"
                f"Reason: {exc}",
            )

        self._refresh_feature4_status()

    def _load_classrooms(self) -> None:
        self._load_feature4_file(
            "Classrooms",
            self._classrooms_label,
            self._controller.load_classrooms,
            self._controller.clear_classrooms,
            lambda count: f"{count} room(s)",
        )

    def _load_slots(self) -> None:
        self._load_feature4_file(
            "Time Slots",
            self._slots_label,
            self._controller.load_time_slots,
            self._controller.clear_time_slots,
            lambda count: f"{count} slot(s)",
        )

    def _load_proctors(self) -> None:
        self._load_feature4_file(
            "Proctor Config",
            self._proctors_label,
            self._controller.load_proctor_config,
            self._controller.clear_proctor_config,
            lambda config: f"1:{config.students_per_proctor}",
        )

    def _on_edit_periods(self) -> None:
        dlg = ExamPeriodsEditorDialog(self._controller, parent=self)
        dlg.exec()
        self._refresh_periods_card()
        self.periods_changed.emit()

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("configFooter")
        footer.setFixedHeight(44)
        footer.setStyleSheet(
            "QWidget#configFooter {"
            " background: rgba(255, 255, 255, 0.85);"
            " border-top: 1px solid rgba(194, 198, 214, 0.6);"
            "}"
        )

        vl = QVBoxLayout(footer)
        vl.setContentsMargins(32, 6, 32, 6)
        vl.setSpacing(2)

        self._progress_bar = QProgressBar()
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(3)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setStyleSheet(
            "QProgressBar { background:transparent; border:none; border-radius:2px; }"
            "QProgressBar::chunk { background:transparent; }"
        )
        vl.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(False)
        self._status_label.setStyleSheet(
            "font-size:11px; color:#64748B; background:transparent;"
        )
        vl.addWidget(self._status_label)

        return footer

    def _load_courses(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Courses File",
            "",
            "Text files (*.txt);;All files (*)",
        )

        if not path:
            return

        checked_btn = self._mode_group.checkedButton()
        mode = checked_btn.text().lower()

        try:
            count = self._controller.load_courses(Path(path), mode=mode)
            self._courses_label.setText(f"{Path(path).name}  ({count})")
            self._courses_label.setStyleSheet(
                "font-size:11px; color:#059669; background:rgba(16,185,129,0.1);"
                " border-radius:4px; padding:2px 7px;"
            )

            self._refresh_programme_list()
            self._set_status(f"✓  {count} courses loaded.")
            self._update_gen_btn()

        except Exception:
            QMessageBox.critical(
                self,
                "Load Error",
                "Could not load the courses file. Please check the file format and try again.",
            )
            logger.exception("Error loading courses")

    def _load_dates(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Exam Periods File",
            "",
            "Text files (*.txt);;All files (*)",
        )

        if not path:
            return

        mode = self._mode_group.checkedButton().text().lower()

        try:
            count = self._controller.load_periods(Path(path), mode=mode)
            self._dates_label.setText(f"{Path(path).name}  ({count})")
            self._dates_label.setStyleSheet(
                "font-size:11px; color:#059669; background:rgba(16,185,129,0.1);"
                " border-radius:4px; padding:2px 7px;"
            )

            self._set_status(f"✓  {count} exam period(s) loaded.")
            self._update_gen_btn()
            self._refresh_periods_card()
            self.periods_changed.emit()

        except Exception:
            QMessageBox.critical(
                self,
                "Load Error",
                "Could not load the exam periods file. Please check the file format and try again.",
            )
            logger.exception("Error loading exam periods")

    def _refresh_programme_list(self) -> None:
        # Clear old rows
        while self._prog_rows_layout.count() > 1:  # keep trailing stretch
            item = self._prog_rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._prog_rows.clear()

        for pid in self._controller.get_programme_ids():
            name = PROGRAM_NAMES_MAPPING.get(pid, "Unknown Program")
            row = _ProgrammeRow(pid, name, parent=self._prog_rows_container)
            row.toggled.connect(self._on_programme_toggled)
            row.view_courses_clicked.connect(self._on_view_courses_for)
            self._prog_rows[pid] = row
            self._prog_rows_layout.insertWidget(self._prog_rows_layout.count() - 1, row)

        has = bool(self._prog_rows)
        self._prog_placeholder.setVisible(not has)
        self._prog_scroll.setVisible(has)

        self._update_prog_label()
        self.courses_changed.emit(self._get_selected_ids())

    def _on_programme_toggled(self, pid: str, checked: bool) -> None:
        if checked and self._count_checked() > _MAX_PROGS:
            self._prog_rows[pid].set_checked(False)
            QMessageBox.information(
                self,
                "Limit Reached",
                f"You can select at most {_MAX_PROGS} programmes.",
            )
            return

        self._update_programme_colours()
        self._update_prog_label()
        self._update_gen_btn()
        self.courses_changed.emit(self._get_selected_ids())

    def _on_view_courses_for(self, pid: str) -> None:
        from src.ui.programme_courses_dialog import ProgrammeCoursesDialog

        dlg = ProgrammeCoursesDialog(pid, self._controller, parent=self)
        dlg.exec()

    def _update_programme_colours(self) -> None:
        slot = 0
        for pid, row in self._prog_rows.items():
            if row.is_checked():
                row.set_label_color(PROGRAMME_COLOURS[slot % len(PROGRAMME_COLOURS)])
                slot += 1
            else:
                row.set_label_color("#64748B")

    def _count_checked(self) -> int:
        return sum(1 for row in self._prog_rows.values() if row.is_checked())

    def _get_selected_ids(self) -> list[str]:
        return [pid for pid, row in self._prog_rows.items() if row.is_checked()]

    def _update_prog_label(self) -> None:
        self._prog_count_lbl.setText(f"{self._count_checked()} / {_MAX_PROGS} selected")

    def _on_open_settings(self) -> None:
        """Open (or raise) the modeless SettingsScreen dialog."""
        is_running = (
            self._gen_process is not None and self._gen_process.is_alive()
        )
        if self._settings_dialog is None:
            self._settings_dialog = SettingsScreen(
                self._controller.settings,
                parent=self,
            )
            self._settings_dialog.settings_changed.connect(self._on_settings_changed)
            self._settings_dialog.sort_order_changed.connect(self._controller.apply_sort)

        self._settings_dialog.set_generation_state(is_running)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _on_settings_changed(self, new_settings: Settings) -> None:
        """Persist the full settings (thresholds + sort) from the dialog OK path."""
        self._controller.apply_settings(new_settings)
        logger.info("Settings updated via SettingsScreen.")

    def _notify_settings_state(self, is_running: bool) -> None:
        """Propagate generation state to the settings dialog if it is open."""
        if self._settings_dialog is not None and self._settings_dialog.isVisible():
            self._settings_dialog.set_generation_state(is_running)

    def _on_generate(self) -> None:
        if not self._confirm_capacity_warning():
            return

        selected = self._get_selected_ids()

        self._controller.set_selected_programs(selected)
        self._controller.set_allow_unassigned_classrooms(
            self._allow_unassigned_generation
        )
        self._pending_selected = selected
        self._pending_color_map = {
            pid: PROGRAMME_COLOURS[i % len(PROGRAMME_COLOURS)]
            for i, pid in enumerate(selected)
        }

        self.generation_started.emit((selected, self._pending_color_map))

        self._gen_btn.setEnabled(False)
        self._notify_settings_state(True)
        self._set_status("Generating schedules…")
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setStyleSheet(
            "QProgressBar { background:#E2E8F0; border:none; border-radius:2px; }"
            "QProgressBar::chunk { background:#2563EB; }"
        )

        if self._gen_process is not None and self._gen_process.is_alive():
            self._gen_process.kill()

        if self._poll_timer is not None:
            self._poll_timer.stop()

        if self._result_queue is not None:
            self._result_queue.cancel_join_thread()
            self._result_queue.close()

        self._gen_start_time = time.monotonic()
        self._dead_ticks = 0
        self._result_queue = multiprocessing.Queue()

        self._gen_process = multiprocessing.Process(
            target=_run_generation_process,
            args=(
                self._result_queue,
                self._controller.courses,
                self._controller.get_exam_periods(),
                selected,
            ),
            kwargs={
                "settings": self._controller.settings,
                "cap": RESULT_BATCH_SIZE,
                "classrooms": self._controller.classrooms,
                "time_slots": self._controller.time_slots,
                "proctor_config": self._controller.proctor_config,
                "allow_unassigned_classrooms": self._allow_unassigned_generation,
            },
            daemon=True,
        )

        self._gen_process.start()

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_result)
        self._poll_timer.start(150)

    def _confirm_capacity_warning(self) -> bool:
        """Show the optional Feature 4 capacity warning before generation."""
        shortfall = self._controller.feature4_capacity_shortfall()
        if shortfall is None:
            self._allow_unassigned_generation = False
            return True

        total_capacity, total_students = shortfall
        response = QMessageBox.warning(
            self,
            "Insufficient Classroom Capacity",
            "The total classroom capacity is lower than the total number of "
            "students.\n\n"
            f"Usable classroom capacity (75%): {total_capacity:,}\n"
            f"Students: {total_students:,}\n"
            f"Missing seats: {total_students - total_capacity:,}\n\n"
            "Generation may reject schedules that cannot be assigned to rooms. "
            "Do you want to proceed anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        self._allow_unassigned_generation = response == QMessageBox.StandardButton.Yes
        return self._allow_unassigned_generation


    def _poll_result(self) -> None:
        elapsed = int(time.monotonic() - self._gen_start_time)

        if elapsed > _MAX_GEN_SECS:
            if self._poll_timer:
                self._poll_timer.stop()

            if self._gen_process:
                self._gen_process.kill()

            self._fail(f"Generation timed out after {_MAX_GEN_SECS}s.")
            return

        try:
            result = self._result_queue.get_nowait()
        except (_QueueEmpty, OSError):
            if self._gen_process is not None and not self._gen_process.is_alive():
                self._dead_ticks += 1

                if self._dead_ticks >= 5:
                    self._dead_ticks = 0

                    if self._poll_timer:
                        self._poll_timer.stop()

                    self._fail("Generation process exited unexpectedly.")
            else:
                self._dead_ticks = 0

            return

        self._dead_ticks = 0

        if self._poll_timer:
            self._poll_timer.stop()

        self._reset_progress()

        if (
            isinstance(result, tuple)
            and len(result) == 4
            and result[0] is True
            and isinstance(result[1], dict)
            and isinstance(result[2], dict)
            and isinstance(result[3], set)
        ):
            _, schedules_by_period, courses_by_id, truncated_periods = result

            self._controller.on_generation_succeeded(truncated_periods)
            schedules_by_period = self._controller.cache_generated_results(
                schedules_by_period
            )

            self._notify_settings_state(False)
            self._gen_btn.setEnabled(True)
            self._set_status("✓  Schedule generated.", ok=True)

            self.schedule_generated.emit(
                (
                    self._pending_selected,
                    schedules_by_period,
                    courses_by_id,
                    self._pending_color_map,
                    truncated_periods,
                )
            )
        else:
            logger.error("Generation failed or returned invalid result: %s", result)
            self._fail("Generation failed. Please check the input files and try again.")


    def _fail(self, msg: str) -> None:
        self._reset_progress()
        self._notify_settings_state(False)

        if self._poll_timer:
            self._poll_timer.stop()

        logger.error("Generation failed: %s", msg)

        self._update_gen_btn()
        self.generation_failed.emit(msg)

    def _reset_progress(self) -> None:
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setStyleSheet(
            "QProgressBar { background:transparent; border:none; border-radius:2px; }"
            "QProgressBar::chunk { background:transparent; }"
        )

    def _set_status(self, text: str, ok: bool = False) -> None:
        color = "#059669" if ok else "#64748B"
        self._status_label.setStyleSheet(
            f"font-size:11px; color:{color}; background:transparent;"
        )
        self._status_label.setText(text)

    def _update_gen_btn(self) -> None:
        running = self._gen_process is not None and self._gen_process.is_alive()

        self._gen_btn.setEnabled(
            not running
            and self._controller.has_courses
            and self._controller.has_periods
            and self._count_checked() >= 1
        )
