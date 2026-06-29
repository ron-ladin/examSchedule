from src.ui.result_summary_presenter import ResultSummaryPresenter


def test_summary_presenter_shows_dirty_message_until_cleared():
    presenter = ResultSummaryPresenter()

    presenter.mark_ranking_dirty(
        "Sort settings changed. Click Result Ranking to apply to current results."
    )
    dirty = presenter.build(
        has_any_periods=True,
        has_results=True,
        is_stale=False,
        is_imported_schedule=False,
        combined_options_total=2,
        period_schedules_total=2,
        has_more=False,
    )

    assert dirty is not None
    assert dirty.text == (
        "Sort settings changed. Click Result Ranking to apply to current results."
    )
    assert presenter.ranking_dirty is True

    presenter.clear_ranking_dirty()
    clean = presenter.build(
        has_any_periods=True,
        has_results=True,
        is_stale=False,
        is_imported_schedule=False,
        combined_options_total=2,
        period_schedules_total=2,
        has_more=False,
    )

    assert clean is not None
    assert "Click Result Ranking" not in clean.text
    assert presenter.ranking_dirty is False


def test_summary_presenter_gives_stale_priority_over_ranking_dirty():
    presenter = ResultSummaryPresenter()
    presenter.mark_ranking_dirty(
        "Sort settings changed. Click Result Ranking to apply to current results."
    )

    summary = presenter.build(
        has_any_periods=True,
        has_results=True,
        is_stale=True,
        is_imported_schedule=False,
        combined_options_total=2,
        period_schedules_total=2,
        has_more=False,
    )

    assert summary is not None
    assert summary.text == "Results stale - regenerate required."
