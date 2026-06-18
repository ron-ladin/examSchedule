"""ProgrammeRow — one selectable programme entry in the ConfigScreen list."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QWidget

_VIEW_BTN_STYLE = (
    "QPushButton { background:rgba(0,67,148,0.07);"
    " border:1px solid rgba(0,67,148,0.2); border-radius:6px;"
    " padding:0px 10px; font-size:11px; font-weight:600; color:#004394; }"
    "QPushButton:hover:enabled { background:rgba(0,67,148,0.13); border-color:#004394; }"
    "QPushButton:disabled { color:#94A3B8; border-color:rgba(194,198,214,0.4);"
    " background:transparent; }"
)


class ProgrammeRow(QWidget):
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

        self._label = QLabel(f"‎{pid}  —  {name}")
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

    def _on_state_changed(self, state: int) -> None:
        checked = state == Qt.CheckState.Checked.value
        self._view_btn.setEnabled(checked)
        self.toggled.emit(self._pid, checked)
