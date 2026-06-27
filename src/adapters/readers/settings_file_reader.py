"""
Reader: SettingsFileReader
---------------------------
Reads the settings file and converts it into a Settings object holding
the parsed THRESHOLD and SORT blocks.

Responsible only for:
    - Reading settings.txt
    - Locating the THRESHOLD and SORT blocks (delimited by header keywords)
    - Parsing each threshold and sort line
    - Validating criterion names, ON/OFF tokens, k values, and priorities
    - Creating Settings (ThresholdSettings + SortingConfig)

File format:
    THRESHOLD
    CRITERION_NAME, ON/OFF, k
    ...
    SORT
    priority, CRITERION_NAME
    ...

The THRESHOLD block is required; the SORT block is optional (an absent or
empty SORT block yields an empty SortingConfig).
"""

from pathlib import Path
from typing import Dict, List, Optional, Set

from src.domain.settings import Settings
from src.domain.sorting import (
    SortCriterion,
    SortingConfig,
    SortRule,
    normalize_sort_criterion,
)
from src.domain.threshold import (
    CRITERION_MIN_K,
    Criterion,
    ThresholdEntry,
    ThresholdSettings,
    normalize_criterion,
)


class SettingsFileReader:
    THRESHOLD_HEADER = "THRESHOLD"
    SORT_HEADER = "SORT"

    VALID_TOGGLE: Dict[str, bool] = {
        "on": True,
        "off": False,
    }

    THRESHOLD_FIELD_COUNT = 3
    SORT_FIELD_COUNT = 2

    def __init__(self, settings_path: Path):
        self.settings_path = Path(settings_path)

    def read(self) -> Settings:
        blocks = self._read_blocks()

        if self.THRESHOLD_HEADER not in blocks:
            raise ValueError(
                f"No THRESHOLD block found in file: {self.settings_path}"
            )

        thresholds = self._parse_threshold_block(blocks[self.THRESHOLD_HEADER])
        sorting = self._parse_sort_block(blocks.get(self.SORT_HEADER, []))

        return Settings(thresholds=thresholds, sorting=sorting)

    def _read_blocks(self) -> Dict[str, List[str]]:
        content = self.settings_path.read_text(encoding="utf-8")

        blocks: Dict[str, List[str]] = {}
        current_header: Optional[str] = None

        for raw_line in content.splitlines():
            line = raw_line.strip()

            if not line:
                continue

            header = self._match_header(line)

            if header is not None:
                if header in blocks:
                    raise ValueError(f"Duplicate block header: {header}")
                blocks[header] = []
                current_header = header
                continue

            if current_header is None:
                raise ValueError(f"Line found outside of any block: {line}")

            blocks[current_header].append(line)

        return blocks

    def _match_header(self, line: str) -> Optional[str]:
        upper = line.upper()

        if upper == self.THRESHOLD_HEADER:
            return self.THRESHOLD_HEADER

        if upper == self.SORT_HEADER:
            return self.SORT_HEADER

        return None

    def _parse_threshold_block(self, lines: List[str]) -> ThresholdSettings:
        # An empty THRESHOLD block is valid: it means "no limiting". Returning an
        # empty ThresholdSettings (no active rules) avoids crashing the CLI/GUI
        # with a raw ValueError when the user leaves the block empty.
        if not lines:
            return ThresholdSettings()

        entries: List[ThresholdEntry] = []
        seen: Set[Criterion] = set()

        for line in lines:
            entry = self._parse_threshold_line(line)

            if entry.criterion in seen:
                raise ValueError(
                    f"Duplicate criterion in THRESHOLD block: {entry.criterion.value}"
                )

            seen.add(entry.criterion)
            entries.append(entry)

        return ThresholdSettings(entries=tuple(entries))

    def _parse_threshold_line(self, line: str) -> ThresholdEntry:
        parts = [
            part.strip()
            for part in line.split(",")
        ]

        if len(parts) != self.THRESHOLD_FIELD_COUNT:
            raise ValueError(f"Invalid THRESHOLD line: {line}")

        name_text, toggle_text, k_text = parts

        criterion = normalize_criterion(name_text)
        enabled = self._normalize_toggle(toggle_text)
        k = self._parse_k(k_text)

        minimum = CRITERION_MIN_K[criterion]

        if enabled and k < minimum:
            raise ValueError(
                f"k for {criterion.value} must be >= {minimum} when ON: {k_text}"
            )

        return ThresholdEntry(criterion=criterion, enabled=enabled, k=k)

    def _normalize_toggle(self, toggle: str) -> bool:
        key = toggle.strip().lower()

        if key not in self.VALID_TOGGLE:
            raise ValueError(f"Invalid ON/OFF value: {toggle}")

        return self.VALID_TOGGLE[key]

    def _parse_k(self, k_text: str) -> int:
        text = k_text.strip()

        # isdigit() returns False for negative numbers ('-' is not a digit), so negatives are implicitly rejected
        if not text.isdigit():
            raise ValueError(f"Invalid k value (must be a non-negative integer): {k_text}")

        return int(text)

    def _parse_sort_block(self, lines: List[str]) -> SortingConfig:
        rules: List[SortRule] = []
        seen: Set[SortCriterion] = set()

        for line in lines:
            rule = self._parse_sort_line(line)

            if rule.criterion in seen:
                raise ValueError(
                    f"Duplicate criterion in SORT block: {rule.criterion.value}"
                )

            seen.add(rule.criterion)
            rules.append(rule)

        self._validate_sequential_priorities(rules)

        return SortingConfig(rules=tuple(rules))

    def _parse_sort_line(self, line: str) -> SortRule:
        parts = [
            part.strip()
            for part in line.split(",")
        ]

        if len(parts) != self.SORT_FIELD_COUNT:
            raise ValueError(f"Invalid SORT line: {line}")

        priority_text, name_text = parts

        priority = self._parse_priority(priority_text)
        criterion = normalize_sort_criterion(name_text)

        return SortRule(priority=priority, criterion=criterion)

    def _parse_priority(self, priority_text: str) -> int:
        text = priority_text.strip()

        if not text.isdigit() or int(text) < 1:
            raise ValueError(
                f"Invalid sort priority (must be a positive integer): {priority_text}"
            )

        return int(text)

    def _validate_sequential_priorities(self, rules: List[SortRule]) -> None:
        priorities = sorted(rule.priority for rule in rules)
        expected = list(range(1, len(priorities) + 1))

        if priorities != expected:
            raise ValueError(
                f"SORT priorities must be sequential starting at 1 with no gaps: {priorities}"
            )
