"""Readable visual editor for schedule filtering and ranking settings."""

import logging

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSpinBox,
    QStyle,
    QStyleOptionSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.domain.settings import Settings
from src.domain.sorting import SortCriterion, SortRule, SortingConfig
from src.domain.threshold import (
    CRITERION_MIN_K,
    Criterion,
    ThresholdEntry,
    ThresholdSettings,
)

_log = logging.getLogger(__name__)

_THRESHOLD_DETAILS: dict[Criterion, tuple[str, str, str]] = {
    Criterion.MIN_DAYS_BETWEEN_MANDATORY_EXAMS: (
        "Space mandatory exams apart",
        "Minimum gap between mandatory exams for the same programme and year.",
        "days minimum",
    ),
    Criterion.MIN_DAYS_BETWEEN_ANY_EXAMS: (
        "Space all exams apart",
        "Minimum gap between any two exams for the same programme and year.",
        "days minimum",
    ),
    Criterion.MAX_ELECTIVE_COLLISIONS: (
        "Limit elective collisions",
        "Maximum number of elective exam pairs allowed on the same day.",
        "collisions maximum",
    ),
    Criterion.MIN_DAYS_EXAM_PERIOD_SPREAD: (
        "Spread the exam period",
        "Minimum days from the first mandatory exam to the last one.",
        "days minimum",
    ),
    Criterion.MAX_EXAMS_PER_DAY: (
        "Limit exams per day",
        "Maximum number of exams that may be scheduled on one day.",
        "exams maximum",
    ),
}

_SORT_LABELS: dict[SortCriterion, str] = {
    SortCriterion.SORT_MIN_DAYS_MANDATORY: "More space between mandatory exams",
    SortCriterion.SORT_AVG_DAYS_ANY: "More average space between all exams",
    SortCriterion.SORT_ELECTIVE_COLLISIONS: "More elective collisions",
    SortCriterion.SORT_EXAM_PERIOD_SPREAD: "Longer exam-period spread",
    SortCriterion.SORT_MAX_EXAMS_PER_DAY: "More exams on the busiest day",
}

_CRITERION_ROLE = Qt.ItemDataRole.UserRole


class _AnimatedToggle(QWidget):
    """Compact ON/OFF switch with a smooth red-to-green sliding transition."""

    toggled = pyqtSignal(bool)

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checked = checked
        self._offset = 1.0 if checked else 0.0
        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.setFixedSize(76, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        checked = bool(checked)
        if checked == self._checked:
            return
        self._checked = checked
        self._animate_to(1.0 if checked else 0.0)
        self.toggled.emit(checked)

    def click(self) -> None:
        self.setChecked(not self._checked)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.click()
        super().mouseReleaseEvent(event)

    def _animate_to(self, target: float) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(target)
        self._animation.start()

    def get_offset(self) -> float:
        return self._offset

    def set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = pyqtProperty(float, get_offset, set_offset)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.isEnabled():
            red = QColor("#FCA5A5")
            green = QColor("#6EE7B7")
            track = QColor(
                round(red.red() + (green.red() - red.red()) * self._offset),
                round(red.green() + (green.green() - red.green()) * self._offset),
                round(red.blue() + (green.blue() - red.blue()) * self._offset),
            )
        else:
            track = QColor("#CBD5E1")

        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(rect, 15, 15)

        knob_size = 26
        knob_x = 4 + (self.width() - knob_size - 8) * self._offset
        knob_y = (self.height() - knob_size) / 2
        painter.setPen(QPen(QColor("#CBD5E1"), 1))
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(round(knob_x), round(knob_y), knob_size, knob_size)

        painter.setPen(QColor("#047857") if self._checked else QColor("#B42318"))
        painter.drawText(
            rect,
            (
                Qt.AlignmentFlag.AlignLeft
                if self._checked
                else Qt.AlignmentFlag.AlignRight
            )
            | Qt.AlignmentFlag.AlignVCenter,
            "  ON" if self._checked else "OFF  ",
        )


class _EditableNumberInput(QSpinBox):
    """Number input designed for direct keyboard entry."""

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.lineEdit().selectAll()

    def mousePressEvent(self, event) -> None:
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        control = self.style().hitTestComplexControl(
            QStyle.ComplexControl.CC_SpinBox,
            option,
            event.position().toPoint(),
            self,
        )
        if control == QStyle.SubControl.SC_SpinBoxUp:
            self.stepUp()
            event.accept()
            return
        if control == QStyle.SubControl.SC_SpinBoxDown:
            self.stepDown()
            event.accept()
            return
        super().mousePressEvent(event)


class SettingsScreen(QDialog):
    """Modeless visual editor for thresholds and result ranking."""

    settings_changed = pyqtSignal(Settings)
    sort_order_changed = pyqtSignal(SortingConfig)

    def __init__(
        self,
        current: Settings,
        is_generating: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Scheduling Settings")
        self.setMinimumSize(760, 650)
        self._current = current
        self._threshold_widgets: dict[Criterion, tuple[_AnimatedToggle, QSpinBox]] = {}
        self._sort_list: QListWidget | None = None
        self._build_ui()
        if is_generating:
            self.set_generation_state(True)

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background: #F4F7FB; }
            QTabWidget::pane {
                background: #FFFFFF; border: 1px solid #DCE5F0;
                border-radius: 10px; top: -1px;
            }
            QTabBar::tab {
                background: #EAF0F7; color: #64748B; padding: 10px 22px;
                border: 1px solid #DCE5F0; font-weight: 600;
            }
            QTabBar::tab:selected { background: #FFFFFF; color: #0755B5; }
            QSpinBox {
                background: #FFFFFF; color: #172033; border: 1px solid #C8D5E5;
                border-radius: 7px; padding: 6px 26px 6px 8px; font-size: 13px;
            }
            QSpinBox::up-button {
                subcontrol-origin: border; subcontrol-position: top right;
                width: 22px; border-left: 1px solid #DCE5F0;
                border-bottom: 1px solid #DCE5F0; border-top-right-radius: 6px;
                background: #EFF6FF;
            }
            QSpinBox::down-button {
                subcontrol-origin: border; subcontrol-position: bottom right;
                width: 22px; border-left: 1px solid #DCE5F0;
                border-bottom-right-radius: 6px; background: #EFF6FF;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: #DBEAFE;
            }
            QListWidget {
                background: #FFFFFF; color: #172033; border: 1px solid #DCE5F0;
                border-radius: 9px; padding: 6px; font-size: 13px;
            }
            QListWidget::item { padding: 10px; margin: 2px; border-radius: 6px; }
            QListWidget::item:selected { background: #DBEAFE; color: #0755B5; }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Schedule preferences")
        title.setStyleSheet(
            "font-size:20px; font-weight:800; color:#172033; background:transparent;"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "Turn rules on or off, then choose their numeric limit. "
            "All rules can be used together. Click a number and type a new value."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            "font-size:12px; color:#64748B; background:transparent;"
        )
        layout.addWidget(subtitle)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_threshold_tab(), "Rules & limits")
        self._tabs.addTab(self._build_sort_tab(), "Result ranking")
        layout.addWidget(self._tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_threshold_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)

        compatibility_note = QLabel(
            "All rules below are compatible and may be turned ON together."
        )
        compatibility_note.setWordWrap(True)
        compatibility_note.setStyleSheet(
            "font-size:11px; font-weight:600; color:#047857; background:#ECFDF5;"
            " border:1px solid #A7F3D0; border-radius:8px; padding:8px 10px;"
        )
        layout.addWidget(compatibility_note)

        for criterion in Criterion:
            entry = self._current.thresholds.for_criterion(criterion)
            enabled = entry.enabled if entry else False
            k_value = entry.k if entry else CRITERION_MIN_K[criterion]
            title_text, description_text, unit_text = _THRESHOLD_DETAILS[criterion]

            card = QFrame()
            card.setStyleSheet(
                "QFrame { background:#FFFFFF; border:1px solid #DCE5F0;"
                " border-radius:10px; }"
            )
            row = QHBoxLayout(card)
            row.setContentsMargins(14, 11, 14, 11)
            row.setSpacing(12)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            title = QLabel(title_text)
            title.setStyleSheet(
                "font-size:13px; font-weight:700; color:#172033; border:none;"
            )
            description = QLabel(description_text)
            description.setWordWrap(True)
            description.setStyleSheet(
                "font-size:11px; color:#64748B; border:none;"
            )
            text_col.addWidget(title)
            text_col.addWidget(description)
            row.addLayout(text_col, 1)

            toggle = _AnimatedToggle(enabled)
            row.addWidget(toggle)

            spinbox = _EditableNumberInput()
            spinbox.setMinimum(CRITERION_MIN_K[criterion])
            spinbox.setMaximum(365)
            spinbox.setValue(k_value)
            spinbox.setFixedWidth(96)
            spinbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
            spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
            spinbox.setKeyboardTracking(False)
            spinbox.setToolTip(
                f"{description_text}\nClick the number and type a new value."
            )
            spinbox.lineEdit().setPlaceholderText("Type value")
            spinbox.setEnabled(enabled)
            row.addWidget(spinbox)

            unit = QLabel(unit_text)
            unit.setMinimumWidth(112)
            unit.setStyleSheet(
                "font-size:11px; font-weight:600; color:#475569; border:none;"
            )
            row.addWidget(unit)

            toggle.toggled.connect(
                lambda checked, s=spinbox: s.setEnabled(checked)
            )
            self._threshold_widgets[criterion] = (toggle, spinbox)
            layout.addWidget(card)

        layout.addStretch()
        return widget

    def _build_sort_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)

        explanation = QLabel(
            "Choose which rules rank generated schedules. Drag enabled rows to "
            "reorder them; the first enabled rule has the highest priority. "
            "All ranking rules can be combined."
        )
        explanation.setWordWrap(True)
        explanation.setStyleSheet(
            "font-size:12px; color:#475569; background:#EFF6FF;"
            " border:1px solid #BFDBFE; border-radius:8px; padding:10px;"
        )
        layout.addWidget(explanation)

        self._sort_list = QListWidget()
        self._sort_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._sort_list.blockSignals(True)
        seen: set[SortCriterion] = set()
        for rule in sorted(self._current.sorting.rules, key=lambda r: r.priority):
            self._add_sort_item(rule.criterion, checked=True)
            seen.add(rule.criterion)
        for criterion in SortCriterion:
            if criterion not in seen:
                self._add_sort_item(criterion, checked=False)
        self._sort_list.blockSignals(False)
        self._sort_list.itemChanged.connect(self._on_sort_list_changed)
        self._sort_list.model().rowsMoved.connect(self._on_sort_list_changed)
        layout.addWidget(self._sort_list)
        return widget

    def _add_sort_item(self, criterion: SortCriterion, *, checked: bool) -> None:
        item = QListWidgetItem(_SORT_LABELS[criterion])
        item.setData(_CRITERION_ROLE, criterion)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._sort_list.addItem(item)

    def set_generation_state(self, is_running: bool) -> None:
        for toggle, spinbox in self._threshold_widgets.values():
            toggle.setEnabled(not is_running)
            spinbox.setEnabled(not is_running and toggle.isChecked())

    def _on_sort_list_changed(self, *_args) -> None:
        self.sort_order_changed.emit(self._build_sorting_config())

    def _on_accept(self) -> None:
        try:
            new_settings = self._build_settings()
        except ValueError as exc:
            _log.warning("SettingsScreen validation error: %s", exc)
            QMessageBox.warning(self, "Invalid Settings", str(exc))
            return
        self.settings_changed.emit(new_settings)
        self.accept()

    def _build_settings(self) -> Settings:
        return Settings(
            thresholds=self._build_threshold_settings(),
            sorting=self._build_sorting_config(),
        )

    def _build_threshold_settings(self) -> ThresholdSettings:
        entries: list[ThresholdEntry] = []
        for criterion, (toggle, spinbox) in self._threshold_widgets.items():
            enabled = toggle.isChecked()
            k = spinbox.value()
            minimum = CRITERION_MIN_K[criterion]
            if enabled and k < minimum:
                raise ValueError(
                    f"{criterion.value}: value must be at least {minimum}, got {k}"
                )
            entries.append(ThresholdEntry(criterion=criterion, enabled=enabled, k=k))
        return ThresholdSettings(entries=tuple(entries))

    def _build_sorting_config(self) -> SortingConfig:
        if self._sort_list is None:
            raise RuntimeError("_sort_list was not initialized")
        rules: list[SortRule] = []
        priority = 1
        for i in range(self._sort_list.count()):
            item = self._sort_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                criterion: SortCriterion = item.data(_CRITERION_ROLE)
                rules.append(SortRule(priority=priority, criterion=criterion))
                priority += 1
        return SortingConfig(rules=tuple(rules))
