from datetime import date

from src.ui.navigation_model import NavigationModel


class _MetadataBackedSchedules:
    def __len__(self):
        return 2

    def __iter__(self):
        raise AssertionError("navigation should use metadata, not materialize schedules")

    def navigation_entries(self):
        return [
            ((("C1", date(2026, 1, 5)),), 0),
            ((("C1", date(2026, 1, 6)),), 1),
        ]


class _RangedMetadataBackedSchedules:
    def __init__(self):
        self.entries = [
            ((("C1", date(2026, 1, 5)),), 0),
            ((("C1", date(2026, 1, 6)),), 1),
        ]
        self.full_calls = 0
        self.range_calls = 0

    def __len__(self):
        return len(self.entries)

    def __iter__(self):
        raise AssertionError("navigation should use metadata, not schedules")

    def navigation_entries(self):
        self.full_calls += 1
        return list(self.entries)

    def navigation_entries_range(self, start_index, count):
        self.range_calls += 1
        return list(self.entries[start_index : start_index + count])


def test_navigation_model_uses_sqlite_metadata_without_materializing_schedules():
    schedules = _MetadataBackedSchedules()
    model = NavigationModel(lambda: {"FALL - Aleph": schedules})

    options = model.date_options("FALL - Aleph")

    assert len(options) == 2
    assert model.nav_position("FALL - Aleph", 1) == (1, 0)


def test_navigation_model_rebuilds_missing_period_lazily():
    model = NavigationModel(lambda: {})

    assert model.date_options("FALL - Aleph") == []
    assert model.nav_position("FALL - Aleph", 0) is None


def test_navigation_model_appends_metadata_range_without_full_rebuild():
    schedules = _RangedMetadataBackedSchedules()
    model = NavigationModel(lambda: {"FALL - Aleph": schedules})
    model.rebuild("FALL - Aleph")

    schedules.entries.extend(
        [
            ((("C1", date(2026, 1, 6)),), 2),
            ((("C1", date(2026, 1, 7)),), 3),
        ]
    )

    model.append_entries("FALL - Aleph", start_index=2, count=2)

    full_model = NavigationModel(lambda: {"FALL - Aleph": schedules})
    full_model.rebuild("FALL - Aleph")

    assert schedules.full_calls == 2
    assert schedules.range_calls == 1
    assert model.date_options("FALL - Aleph") == full_model.date_options(
        "FALL - Aleph"
    )
    assert model.index_nav("FALL - Aleph") == full_model.index_nav("FALL - Aleph")
    assert model._signature_pos_cache["FALL - Aleph"] == (
        full_model._signature_pos_cache["FALL - Aleph"]
    )
