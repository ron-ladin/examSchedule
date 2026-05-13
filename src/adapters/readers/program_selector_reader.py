"""
Reader: ProgramSelectorReader
------------------------------
Reads the selected programs file and validates selected program IDs.

Responsible only for:
    - Reading Programs.txt
    - Returning selected program IDs
    - Validating program count and format
"""

from pathlib import Path
from typing import List


class ProgramSelectorReader:
    MAX_SELECTED_PROGRAMS = 5

    def __init__(self, programs_path: Path):
        self.programs_path = Path(programs_path)

    def read(self) -> List[str]:
        content = self.programs_path.read_text(encoding="utf-8").strip()

        programs = [
            item.strip()
            for item in content.split(",")
            if item.strip()
        ]

        if not programs:
            raise ValueError("At least one program must be selected.")

        if len(programs) > self.MAX_SELECTED_PROGRAMS:
            raise ValueError("You can select up to 5 programs only.")

        for program_id in programs:
            if not self._is_valid_program_id(program_id):
                raise ValueError(f"Invalid program id: {program_id}")

        return programs

    def _is_valid_program_id(self, program_id: str) -> bool:
        return len(program_id) == 5 and program_id.isdigit()