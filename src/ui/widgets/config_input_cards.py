"""Input cards for ConfigScreen: load-mode selector and file loaders."""

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from src.ui.assets.icons import BookIcon, CalendarIcon


def _section_lbl(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "font-size:10px; font-weight:700; color:#72778c;"
        " letter-spacing:0.6px; background:transparent;"
    )
    return lbl


def _card_style(frame: QFrame) -> None:
    frame.setStyleSheet(
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
    frame.setGraphicsEffect(eff)


class LoadModeCard(QFrame):
    """Replace/Update radio selector. Exposes the QButtonGroup as ``button_group``."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        _card_style(self)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(20, 18, 20, 18)
        vl.setSpacing(10)
        vl.addWidget(_section_lbl("LOAD MODE"))

        self.button_group = QButtonGroup(self)
        self._btn_frame_pairs: list[tuple[QRadioButton, QFrame]] = []

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

            rb_row = QFrame()
            rb_row.setStyleSheet("background:transparent;")

            rl = QHBoxLayout(rb_row)
            rl.setContentsMargins(14, 12, 14, 4)
            rl.setSpacing(10)

            rb = QRadioButton(label)
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            rb.setStyleSheet(radio_style)

            self.button_group.addButton(rb)

            rl.addWidget(rb)
            rl.addStretch()

            hint = QLabel(hint_text)
            hint.setContentsMargins(42, 0, 14, 10)
            hint.setStyleSheet(
                "font-size:12px; color:#42474e; background:transparent;"
            )

            fl.addWidget(rb_row)
            fl.addWidget(hint)

            rb.toggled.connect(lambda _: self._update_styles())
            option_frame.mousePressEvent = lambda event, _rb=rb: _rb.setChecked(True)
            self._btn_frame_pairs.append((rb, option_frame))
            vl.addWidget(option_frame)

        self.button_group.buttons()[0].setChecked(True)
        self._update_styles()

        vl.addStretch()

    def selected_mode(self) -> str:
        return self.button_group.checkedButton().text().lower()

    def _update_styles(self) -> None:
        checked = self.button_group.checkedButton()
        for btn, frame in self._btn_frame_pairs:
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


class FilesCard(QFrame):
    """Courses / Exam-Periods file loader rows.

    Exposes ``courses_btn``, ``periods_btn``, ``courses_label``, ``dates_label``.
    """

    def __init__(
        self,
        on_load_courses: Callable[[], None],
        on_load_periods: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        _card_style(self)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(20, 18, 20, 18)
        vl.setSpacing(10)
        vl.addWidget(_section_lbl("FILES"))

        file_btn_style = (
            "QPushButton { background:rgba(222,227,235,0.9);"
            " border:1px solid rgba(194,198,214,0.5); border-radius:8px;"
            " padding:5px 12px; font-size:12px; font-weight:600; color:#171c20; }"
            "QPushButton:hover { background:rgba(0,67,148,0.08);"
            " border-color:#004394; color:#004394; }"
        )

        specs = [
            (BookIcon(14, "#004394"), "Courses", "Load Courses", on_load_courses),
            (CalendarIcon(14, "#004394"), "Exam Periods", "Load Periods",
             on_load_periods),
        ]
        labels: list[QLabel] = []
        buttons: list[QPushButton] = []

        for icon, title, btn_text, slot in specs:
            btn = QPushButton(btn_text)
            btn.setFixedWidth(110)
            btn.setStyleSheet(file_btn_style)
            btn.clicked.connect(slot)

            lbl = QLabel("No file loaded")
            lbl.setStyleSheet(
                "font-size:11px; color:#72778c; background:transparent;"
            )

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
            labels.append(lbl)
            buttons.append(btn)

        self.courses_btn, self.periods_btn = buttons
        self.courses_label, self.dates_label = labels
