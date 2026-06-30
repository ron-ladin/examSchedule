"""Top-level layout construction for the results panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.ui.active_limits_panel import ActiveLimitsPanel
from src.ui.assets.animated_widgets import AnimatedPlaceholder
from src.ui.results_shortlist_controller import _SHORTLIST_ADD_BUTTON_STYLE
from src.ui.tokens import (
    COLOR_PANEL_BLUE,
    COLOR_PRIMARY_ACTION,
    COLOR_SURFACE_SOFT,
    COLOR_TEXT_DARK,
    COLOR_VIOLET,
    COLOR_VIOLET_BORDER,
    PERIOD_TAB_STYLE,
)
from src.ui.widgets.period_card_builder import _light_hover_bubble

if TYPE_CHECKING:
    from src.ui.results_panel import _ResultsPanel


class ResultsLayoutController:
    """Build static widgets and layout for the results panel."""

    def __init__(self, panel: "_ResultsPanel", *, ranking_button_text: str) -> None:
        self._panel = panel
        self._ranking_button_text = ranking_button_text

    def setup_ui(self) -> None:
        panel = self._panel
        panel.setStyleSheet(
            """
            _ResultsPanel { background: transparent; }
            """
        )

        root = QVBoxLayout(panel)
        root.setContentsMargins(12, 12, 12, 12)

        panel._placeholder = AnimatedPlaceholder(
            "No schedules generated yet.\n\n"
            "Load files, select a programme, then click  ▶  Generate Schedule."
        )
        root.addWidget(panel._placeholder)

        panel._content = QWidget()
        panel._content.setStyleSheet("background: transparent;")
        panel._content.setVisible(False)

        content_layout = QVBoxLayout(panel._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        action_row = QHBoxLayout()

        panel._summary_lbl = QLabel("")
        panel._summary_lbl.setStyleSheet(
            "color: #059669; font-weight: 600; font-size: 12px;"
        )
        action_row.addWidget(panel._summary_lbl)
        action_row.addStretch()

        panel._ranking_btn = QPushButton(self._ranking_button_text)
        panel._ranking_btn.setStyleSheet(
            "QPushButton {"
            " background: #2563EB; color: #FFFFFF; font-weight: 700;"
            " border: none; border-radius: 8px; padding: 7px 18px; }"
            "QPushButton:hover { background: #1D4ED8; }"
            "QPushButton:disabled { background: #C7D2DE; color: #FFFFFF; }"
        )
        panel._ranking_btn.clicked.connect(panel._on_result_ranking)
        action_row.addWidget(panel._ranking_btn)

        panel._save_favorite_btn = QPushButton("Add to Shortlist")
        panel._save_favorite_btn.setStyleSheet(_SHORTLIST_ADD_BUTTON_STYLE)
        panel._save_favorite_btn.clicked.connect(panel._toggle_visible_favorite)
        action_row.addWidget(panel._save_favorite_btn)

        panel._favorites_btn = QPushButton("Shortlist (0)")
        panel._favorites_btn.setStyleSheet(
            "QPushButton { background: #F5F3FF; color: #5B21B6;"
            f" border: 1px solid {COLOR_VIOLET_BORDER}; border-radius: 8px;"
            " padding: 7px 16px; font-weight: 700; }"
            "QPushButton:hover { background: #EDE9FE; }"
            "QPushButton:disabled { background: #F1F5F9; color: #94A3B8;"
            " border-color: #CBD5E1; }"
        )
        panel._favorites_btn.clicked.connect(panel._show_favorites_dialog)
        action_row.addWidget(panel._favorites_btn)

        panel._save_btn = QPushButton("⬇  Export Shortlist")
        panel._save_btn.clicked.connect(panel._on_save)
        action_row.addWidget(panel._save_btn)

        panel._proctor_btn = QPushButton("🧑‍🏫  Proctor Report")
        panel._proctor_btn.clicked.connect(panel._on_proctor_report)
        action_row.addWidget(panel._proctor_btn)

        content_layout.addLayout(action_row)

        panel._limits_panel = ActiveLimitsPanel(panel)
        panel._limits_toggle = panel._limits_panel.toggle
        panel._limits_details = panel._limits_panel.details

        content_layout.addWidget(panel._limits_panel)

        panel._stale_banner = QLabel(
            "⚠  Exam period dates were changed after generation. "
            "The displayed schedules may contain now-excluded dates. "
            "Click  ▶  Generate again to update."
        )
        panel._stale_banner.setWordWrap(True)
        panel._stale_banner.setStyleSheet(
            "background: #FEF3C7; color: #92400E;"
            " border: 1px solid #F59E0B; border-radius: 8px;"
            " padding: 8px 14px; font-size: 12px; font-weight: 500;"
        )
        panel._stale_banner.setVisible(False)

        content_layout.addWidget(panel._stale_banner)

        panel._period_selector = QWidget()
        panel._period_selector.setStyleSheet(
            "QWidget { background: #FFFFFF; border: 1px solid #DCE5F0;"
            " border-radius: 8px; }"
        )
        selector_layout = QHBoxLayout(panel._period_selector)
        selector_layout.setContentsMargins(12, 10, 12, 10)
        selector_layout.setSpacing(10)

        selector_title = QLabel("View period")
        selector_title.setStyleSheet(
            f"background: transparent; border: none; color: {COLOR_PRIMARY_ACTION};"
            " font-size: 13px; font-weight: 800;"
        )
        selector_layout.addWidget(selector_title)

        panel._period_tip_btn = QToolButton()
        panel._period_tip_btn.setText("!")
        panel._period_tip_btn.setCursor(Qt.CursorShape.WhatsThisCursor)
        panel._period_tip_btn.setFixedSize(24, 24)
        panel._period_tip_btn.setStyleSheet(
            f"QToolButton {{ background: {COLOR_PANEL_BLUE}; color: {COLOR_PRIMARY_ACTION};"
            " border: 1px solid #93C5FD; border-radius: 12px;"
            " font-size: 13px; font-weight: 900; }"
            f"QToolButton:hover {{ background: #F5F3FF; color: {COLOR_VIOLET};"
            f" border-color: {COLOR_VIOLET_BORDER}; }}"
        )
        panel._period_tip_btn.installEventFilter(panel)
        selector_layout.addWidget(panel._period_tip_btn)

        panel._period_tip_bubble = _light_hover_bubble()
        panel._period_tip_bubble.setText(
            "Click on any scheduled exam date to view full details."
        )

        semester_label = QLabel("Semester")
        semester_label.setStyleSheet(
            "background: transparent; border: none; color: #64748B;"
            " font-size: 11px; font-weight: 700;"
        )
        selector_layout.addWidget(semester_label)

        combo_style = (
            f"QComboBox {{ background: {COLOR_SURFACE_SOFT}; color: {COLOR_TEXT_DARK};"
            " border: 1px solid #CBD5E1; border-radius: 8px;"
            " padding: 6px 32px 6px 10px; font-size: 12px; font-weight: 700;"
            " min-width: 140px; }"
            f"QComboBox:hover {{ border-color: {COLOR_VIOLET}; }}"
            f"QComboBox:focus {{ border-color: {COLOR_PRIMARY_ACTION}; }}"
            "QComboBox::drop-down { border: none; width: 26px; }"
        )
        panel._semester_combo = QComboBox()
        panel._semester_combo.setStyleSheet(combo_style)
        panel._semester_combo.currentIndexChanged.connect(
            panel._on_period_semester_changed
        )
        selector_layout.addWidget(panel._semester_combo)

        moed_label = QLabel("Moed")
        moed_label.setStyleSheet(
            "background: transparent; border: none; color: #64748B;"
            " font-size: 11px; font-weight: 700;"
        )
        selector_layout.addWidget(moed_label)

        panel._moed_combo = QComboBox()
        panel._moed_combo.setStyleSheet(combo_style)
        panel._moed_combo.currentIndexChanged.connect(panel._on_period_moed_changed)
        selector_layout.addWidget(panel._moed_combo)
        selector_layout.addStretch()
        panel._period_selector.setVisible(False)

        content_layout.addWidget(panel._period_selector)

        panel._period_tabs = QTabWidget()
        panel._period_tabs.setStyleSheet(PERIOD_TAB_STYLE)
        panel._period_tabs.tabBar().hide()
        panel._period_tabs.currentChanged.connect(panel._on_period_tab_changed)
        content_layout.addWidget(panel._period_tabs)

        root.addWidget(panel._content)

    def show_period_tip(self) -> None:
        """Show a styled light popover instead of the native black tooltip."""
        panel = self._panel
        if not panel._period_tip_btn.isVisible():
            return

        panel._period_tip_bubble.adjustSize()
        pos = panel._period_tip_btn.mapToGlobal(
            QPoint(0, panel._period_tip_btn.height() + 8)
        )
        panel._period_tip_bubble.move(pos)
        panel._period_tip_bubble.show()
        panel._period_tip_bubble.raise_()
