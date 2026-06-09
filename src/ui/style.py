from pathlib import Path
from src.ui import tokens

_QSS_PATH = Path(__file__).parent / "stylesheet.qss"

_REPLACEMENTS = {
    "@COLOR_BACKGROUND@": tokens.COLOR_BACKGROUND,
    "@COLOR_SIDEBAR@":    tokens.COLOR_SIDEBAR,
    "@COLOR_CARD_BG@":    tokens.COLOR_CARD_BG,
    "@COLOR_HOVER@":      tokens.COLOR_HOVER,
    "@COLOR_PRIMARY@":    tokens.COLOR_PRIMARY,
    "@COLOR_SECONDARY@":  tokens.COLOR_SECONDARY,
}


def get_application_style() -> str:
    raw = _QSS_PATH.read_text(encoding="utf-8")
    for placeholder, value in _REPLACEMENTS.items():
        raw = raw.replace(placeholder, value)
    return raw


_qss_cache: str | None = None


def QSS() -> str:
    global _qss_cache
    if _qss_cache is None:
        _qss_cache = get_application_style()
    return _qss_cache
