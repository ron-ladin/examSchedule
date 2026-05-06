"""
Unit Tests: ExactConflictStrategy
-----------------------------------
Tests for the conflict detection logic in ExactConflictStrategy.

Test cases to implement (use @pytest.mark.parametrize):
    1. Same date, same program, same year, both Obligatory  -> conflict (True)
    2. Same date, same program, same year, one Elective     -> conflict (True)
    3. Same date, same program, same year, both Elective    -> no conflict (False)
    4. Same date, different program, same year              -> no conflict (False)
    5. Same date, same program, different year              -> no conflict (False)

Notes:
    - Use pytest fixtures to build Course and CourseOffering objects.
    - Do NOT test file parsing here -- only the conflict logic.
    - Import ExactConflictStrategy from src.adapters.exact_conflict_strategy.
"""
