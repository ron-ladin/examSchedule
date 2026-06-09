"""
Design Tokens — Syncacademic Portal (Light Theme)
"""

# ── 1. Brand / Theme Colors ──────────────────────────────────────────────────
COLOR_BACKGROUND = "#f6faff"                   # Soft blue-white base
COLOR_SIDEBAR    = "rgba(255, 255, 255, 0.85)" # Glass header / footer
COLOR_CARD_BG    = "#FFFFFF"                   # White cards
COLOR_HOVER      = "rgba(0, 90, 194, 0.06)"   # Subtle primary hover
COLOR_PRIMARY    = "#005ac2"                   # Brand blue (design system)
COLOR_SECONDARY  = "#004494"                   # Darker brand blue

# ── 2. Exam Calendar Indicators ──────────────────────────────────────────────
COLOR_CAL_ACTIVE_BG   = "#DBEAFE"  # Blue-100 active days
COLOR_CAL_ACTIVE_FG   = "#1D4ED8"  # Blue-700 active day text
COLOR_CAL_EXCLUDED_BG = "#FEE2E2"  # Red-100 excluded days
COLOR_CAL_EXCLUDED_FG = "#DC2626"  # Red-600 excluded day text

# ── 3. Shared Period Tab QSS ─────────────────────────────────────────────────
PERIOD_TAB_STYLE: str = """
    QTabWidget::pane { border: none; background: transparent; }
    QTabBar::tab {
        background: transparent; color: #42474e;
        border: none; border-bottom: 2px solid transparent;
        padding: 8px 18px; font-size: 12px; font-weight: 500;
    }
    QTabBar::tab:selected {
        color: #005ac2; border-bottom: 2px solid #005ac2; font-weight: 700;
    }
    QTabBar::tab:hover { background: rgba(0,90,194,0.04); color: #005ac2; }
"""

# ── 4. Layout Spacing Tokens ─────────────────────────────────────────────────
SPACING_PANEL_GAP  = 12
CALENDAR_CELL_SIZE = 30

# ── 4. Programme Slot Colors (max 5) ─────────────────────────────────────────
PROGRAMME_COLOURS: tuple[str, str, str, str, str] = (
    "#7C3AED",  # Violet-700
    "#2563EB",  # Blue-600
    "#059669",  # Emerald-600
    "#D97706",  # Amber-600
    "#DC2626",  # Red-600
)

# ── 5. Program ID → Official Hebrew Name Mapping ─────────────────────────────
PROGRAM_NAMES_MAPPING: dict[str, str] = {
    "83101": "הנדסת מחשבים",
    "83102": "הנדסת חשמל",
    "83103": "הנדסת חשמל – מגמת נוירו הנדסה",
    "83104": "הנדסת תעשיה ומערכות מידע",
    "83105": "הנדסת מחשבים – מגמת חומרת מחשבים",
    "83107": "הנדסת נתונים",
    "83108": "הנדסת תוכנה",
    "83109": "הנדסת חומרים",
    "83115": "הנדסת חשמל – מגמת הנדסה ביו-רפואית",
    "83182": "הנדסת חשמל – מגמת הנדסה קוונטית",
}
