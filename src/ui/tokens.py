"""
Design Tokens — Syncacademic Portal (Light Theme)
"""

# ── 1. Brand / Theme Colors ──────────────────────────────────────────────────
COLOR_BACKGROUND = "#F1F5F9"       # Slate-100 page background
COLOR_SIDEBAR    = "#FFFFFF"       # White sidebar
COLOR_CARD_BG    = "#FFFFFF"       # White cards / containers
COLOR_HOVER      = "#EFF6FF"       # Blue-50 hover state
COLOR_PRIMARY    = "#2563EB"       # Blue-600 primary accent
COLOR_SECONDARY  = "#1D4ED8"       # Blue-700 active / selected

# ── 2. Exam Calendar Indicators ──────────────────────────────────────────────
COLOR_CAL_ACTIVE_BG   = "#DBEAFE"  # Blue-100 active days
COLOR_CAL_ACTIVE_FG   = "#1D4ED8"  # Blue-700 active day text
COLOR_CAL_EXCLUDED_BG = "#FEE2E2"  # Red-100 excluded days
COLOR_CAL_EXCLUDED_FG = "#DC2626"  # Red-600 excluded day text

# ── 3. Layout Spacing Tokens ─────────────────────────────────────────────────
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
