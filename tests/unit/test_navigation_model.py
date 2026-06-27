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
