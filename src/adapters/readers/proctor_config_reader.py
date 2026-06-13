"""
Reader: ProctorConfigReader
----------------------------
Reads the proctor ratio file and converts it into a ProctorConfig object.

Responsible only for:
    - Reading the proctor ratio file (CLI input, spec section 2.4.5)
    - Parsing the single "1:X" ratio line
    - Validating the ratio format and value
    - Creating the ProctorConfig object

File format (a single line, spec section 2.4):
    1:X        # one proctor for every X students, X a positive integer
"""

from pathlib import Path

from src.domain.proctor import ProctorConfig


class ProctorConfigReader:
    RATIO_NUMERATOR = "1"
    RATIO_FIELD_COUNT = 2

    def __init__(self, ratio_path: Path):
        self.ratio_path = Path(ratio_path)

    def read(self) -> ProctorConfig:
        line = self._read_ratio_line()
        students_per_proctor = self._parse_ratio_line(line)
        return ProctorConfig(students_per_proctor=students_per_proctor)

    def _read_ratio_line(self) -> str:
        content = self.ratio_path.read_text(encoding="utf-8")

        lines = [
            line.strip()
            for line in content.splitlines()
            if line.strip()
        ]

        # Exactly one ratio line is expected (spec 2.4.5).
        if len(lines) != 1:
            raise ValueError(
                f"Proctor ratio file must contain exactly one '1:X' line: {self.ratio_path}"
            )

        return lines[0]

    def _parse_ratio_line(self, line: str) -> int:
        parts = [
            part.strip()
            for part in line.split(":")
        ]

        if len(parts) != self.RATIO_FIELD_COUNT:
            raise ValueError(f"Invalid proctor ratio (expected '1:X'): {line}")

        numerator, denominator = parts

        # The ratio must always start with "1:" (spec 5.3).
        if numerator != self.RATIO_NUMERATOR:
            raise ValueError(f"Proctor ratio must start with '1:': {line}")

        # X must be a positive integer greater than 0 (spec 2.4.1).
        if not denominator.isdigit() or int(denominator) == 0:
            raise ValueError(f"Proctor ratio X must be a positive integer: {line}")

        return int(denominator)
