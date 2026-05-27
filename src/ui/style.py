"""
Organic Noir QSS Theme
-----------------------
Primary palette:
    #0b1326  — main background
    #060e20  — sidebar / deep panels
    #131b2e  — secondary panels / group boxes
    #1e2b45  — hover / selected state
    #adc6ff  — Crystal Blue  (primary text, accents, borders)
    #d0bcff  — Lavender      (secondary accents, tab-selected)
    rgba(255,255,255,0.1) — borders
"""

QSS = """
/* ── Base ─────────────────────────────────────────────────────────── */
QMainWindow, QDialog, QWidget {
    background-color: #0b1326;
    color: #adc6ff;
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 12px;
}

/* ── Sidebar ─────────────────────────────────────────────────────── */
QWidget#sidebar {
    background-color: #060e20;
    border-right: 1px solid rgba(255, 255, 255, 0.1);
}

/* ── Group boxes ─────────────────────────────────────────────────── */
QGroupBox {
    background-color: #131b2e;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    color: #adc6ff;
    font-weight: bold;
    font-size: 11px;
    padding: 0 4px;
}

/* ── Buttons ─────────────────────────────────────────────────────── */
QPushButton {
    background-color: #131b2e;
    color: #adc6ff;
    border: 1px solid rgba(173, 198, 255, 0.35);
    border-radius: 4px;
    padding: 5px 10px;
}
QPushButton:hover {
    background-color: #1e2b45;
    border-color: #adc6ff;
}
QPushButton:pressed {
    background-color: #0f1a30;
}
QPushButton:disabled {
    color: #3a4560;
    border-color: rgba(255, 255, 255, 0.06);
    background-color: #0d1525;
}
QPushButton#generateBtn {
    background-color: #1e2b45;
    color: #adc6ff;
    border: 1px solid #adc6ff;
    border-radius: 5px;
    font-size: 13px;
    font-weight: bold;
    padding: 8px;
}
QPushButton#generateBtn:hover {
    background-color: #2a3d60;
}
QPushButton#generateBtn:disabled {
    color: #3a4560;
    border-color: rgba(173, 198, 255, 0.15);
    background-color: #0d1525;
}

/* ── Radio buttons ───────────────────────────────────────────────── */
QRadioButton {
    color: #adc6ff;
    spacing: 5px;
}
QRadioButton::indicator {
    width: 13px;
    height: 13px;
    border: 1px solid rgba(173, 198, 255, 0.5);
    border-radius: 7px;
    background-color: #060e20;
}
QRadioButton::indicator:checked {
    background-color: #adc6ff;
    border-color: #adc6ff;
}

/* ── Labels ──────────────────────────────────────────────────────── */
QLabel {
    color: #adc6ff;
    background: transparent;
}

/* ── List widget ─────────────────────────────────────────────────── */
QListWidget {
    background-color: #060e20;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 4px;
    outline: none;
}
QListWidget::item {
    padding: 4px 6px;
    border-radius: 3px;
}
QListWidget::item:hover {
    background-color: #131b2e;
}
QListWidget::item:selected {
    background-color: #1e2b45;
    color: #d0bcff;
}

/* ── Table ───────────────────────────────────────────────────────── */
QTableWidget {
    background-color: #060e20;
    alternate-background-color: #131b2e;
    gridline-color: rgba(255, 255, 255, 0.05);
    border: none;
    outline: none;
}
QTableWidget::item {
    padding: 5px 6px;
    color: #adc6ff;
}
QTableWidget::item:selected {
    background-color: #1e2b45;
    color: #d0bcff;
}
QHeaderView {
    background-color: #131b2e;
}
QHeaderView::section {
    background-color: #131b2e;
    color: #adc6ff;
    font-weight: bold;
    font-size: 11px;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.15);
    padding: 6px 6px;
}
QHeaderView::section:hover {
    background-color: #1e2b45;
}

/* ── Tab widget ──────────────────────────────────────────────────── */
QTabWidget::pane {
    border: 1px solid rgba(255, 255, 255, 0.1);
    background-color: #0b1326;
    border-radius: 0 4px 4px 4px;
}
QTabBar {
    background: transparent;
}
QTabBar::tab {
    background-color: #060e20;
    color: #7a92bf;
    padding: 7px 18px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #0b1326;
    color: #d0bcff;
    font-weight: bold;
    border-bottom: 2px solid #adc6ff;
}
QTabBar::tab:hover:!selected {
    background-color: #131b2e;
    color: #adc6ff;
}

/* ── Scroll bars ─────────────────────────────────────────────────── */
QScrollBar:vertical {
    background: #060e20;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: rgba(173, 198, 255, 0.25);
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(173, 198, 255, 0.45);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #060e20;
    height: 8px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: rgba(173, 198, 255, 0.25);
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background: rgba(173, 198, 255, 0.45);
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Splitter ────────────────────────────────────────────────────── */
QSplitter::handle {
    background-color: rgba(255, 255, 255, 0.08);
}
QSplitter::handle:hover {
    background-color: rgba(173, 198, 255, 0.25);
}

/* ── Date edit ───────────────────────────────────────────────────── */
QDateEdit {
    background-color: #131b2e;
    color: #adc6ff;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 4px;
    padding: 3px 6px;
}
QDateEdit::drop-down {
    border: none;
    width: 16px;
}
QCalendarWidget {
    background-color: #131b2e;
    color: #adc6ff;
}

/* ── Scroll area ─────────────────────────────────────────────────── */
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollArea > QWidget > QWidget {
    background-color: transparent;
}

/* ── Message boxes ───────────────────────────────────────────────── */
QMessageBox {
    background-color: #131b2e;
    color: #adc6ff;
}
"""
