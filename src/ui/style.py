"""
Style Subsystem Engine
-----------------------
This file reads the clean visual design rules from 'stylesheet.qss',
injects our central design tokens, and prepares the final look of the app.
"""
from src.ui import tokens

def get_application_style() -> str:
    """
    Step-by-step function to load and build the application's visual theme.
    """
    
    # ── STEP 1: Define exactly where the visual stylesheet file is located ──
    # We point directly to our clean design file in the same folder
    stylesheet_file_path = "src/ui/stylesheet.qss"
    
    # ── STEP 2: Open the file and read all the raw design text inside it ──
    with open(stylesheet_file_path, "r", encoding="utf-8") as file:
        raw_design_text = file.read()
        
    # ── STEP 3: Replace the empty text placeholders with your real colors ──
    # We take the placeholders from the file and inject the variables from tokens.py
    final_style = raw_design_text
    final_style = final_style.replace("@COLOR_BACKGROUND@", tokens.COLOR_BACKGROUND)
    final_style = final_style.replace("@COLOR_SIDEBAR@", tokens.COLOR_SIDEBAR)
    final_style = final_style.replace("@COLOR_CARD_BG@", tokens.COLOR_CARD_BG)
    final_style = final_style.replace("@COLOR_HOVER@", tokens.COLOR_HOVER)
    final_style = final_style.replace("@COLOR_PRIMARY@", tokens.COLOR_PRIMARY)
    final_style = final_style.replace("@COLOR_SECONDARY@", tokens.COLOR_SECONDARY)
    
    # ── STEP 4: Return the fully customized design back to the application ──
    return final_style


# This is the final variable that the application looks for to dress up the UI
QSS: str = get_application_style()
