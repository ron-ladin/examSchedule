"""
Domain Utility: Settings
-------------------------
Aggregate of the full parsed settings.txt.

Composes the two cohesive halves of the file, defined in their own modules:
    - ThresholdSettings  (see threshold.py) — the THRESHOLD block (sections 2.1-2.5)
    - SortingConfig      (see sorting.py)   — the SORT block (sections 3.1-3.5)

Notes:
    - Pure data container. No file I/O here.
    - Built by the reader (SettingsFileReader).
"""

from dataclasses import dataclass

from src.domain.sorting import SortingConfig
from src.domain.threshold import ThresholdSettings


@dataclass(frozen=True)
class Settings:
    """The full parsed settings.txt: threshold criteria plus sorting rules."""

    thresholds: ThresholdSettings
    sorting: SortingConfig
