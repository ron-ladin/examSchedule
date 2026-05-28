"""
Design Tokens for Syncademic UI
--------------------------------
Based on Niv's Organic Noir Palette.
Provides centralized colors, spacing, and application-wide constants.
"""
from typing import Tuple

# ── 1. Brand States & Theme Colors (Derived from Niv's style.py) ───────────
COLOR_BACKGROUND = "#0b1326"       # Main window dark background
COLOR_SIDEBAR    = "#060e20"       # Deep panel / sidebar background
COLOR_CARD_BG    = "#131b2e"       # Secondary panels / group boxes
COLOR_HOVER      = "#1e2b45"       # Hover / selected state
COLOR_PRIMARY    = "#adc6ff"       # Crystal Blue (primary text, accents)
COLOR_SECONDARY  = "#d0bcff"       # Lavender (secondary accents, tabs)

# ── 2. Exam Calendar Indicators (From DateEditorWidget) ─────────────────────
COLOR_CAL_ACTIVE_BG   = "#dbeafe"  # Active days background
COLOR_CAL_ACTIVE_FG   = "#1d4ed8"  # Active days text
COLOR_CAL_EXCLUDED_BG = "#fee2e2"  # Excluded days background
COLOR_CAL_EXCLUDED_FG = "#dc2626"  # Excluded days text

# ── 3. Layout Spacing Tokens ────────────────────────────────────────────────
SPACING_PANEL_GAP = 12             # Layout margin / spacing gap
CALENDAR_CELL_SIZE = 30            # Fixed size for day buttons

# ── 4. Programme Slots Colors (Strict Readonly Tuple - Max 5) ───────────────
# Fixed set of 5 distinct colors that complement the Organic Noir theme.
# Used for color-coding courses and schedule grids by major/programme.
PROGRAMME_COLOURS: Tuple[str, str, str, str, str] = (
    "#d0bcff",  # Slot 1: Lavender accent
    "#adc6ff",  # Slot 2: Crystal Blue accent
    "#34d399",  # Slot 3: Mint Green (Success/Valid)
    "#fbbf24",  # Slot 4: Amber/Warning
    "#f87171",  # Slot 5: Coral/Danger
)