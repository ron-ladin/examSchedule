"""Presentation helper for ResultsPanel summary text."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SummaryView:
    text: str
    style: str


class ResultSummaryPresenter:
    """Own summary text decisions for the results panel."""

    _OK_STYLE = "color: #059669; font-weight: 600; font-size: 12px;"
    _ERROR_STYLE = "color: #DC2626; font-weight: 600; font-size: 12px;"

    def __init__(self) -> None:
        self._ranking_dirty_message: str | None = None

    @property
    def ranking_dirty(self) -> bool:
        return self._ranking_dirty_message is not None

    @property
    def ranking_dirty_message(self) -> str | None:
        return self._ranking_dirty_message

    def mark_ranking_dirty(self, message: str) -> None:
        self._ranking_dirty_message = message

    def clear_ranking_dirty(self) -> None:
        self._ranking_dirty_message = None

    def build(
        self,
        *,
        has_any_periods: bool,
        has_results: bool,
        is_stale: bool,
        is_imported_schedule: bool,
        combined_options_total: int,
        period_schedules_total: int,
        has_more: bool,
    ) -> SummaryView | None:
        """Return summary text/style or None when no summary should be shown."""
        if not has_any_periods:
            return None

        if is_stale:
            return SummaryView("Results stale - regenerate required.", self._ERROR_STYLE)

        if not has_results:
            return SummaryView("⚠  No valid schedules found.", self._ERROR_STYLE)

        if is_imported_schedule:
            return SummaryView(
                "✓  Imported schedule loaded "
                f"({period_schedules_total:,} period schedules in view)",
                self._OK_STYLE,
            )

        loaded_text = "loaded so far" if has_more else "loaded in total"
        return SummaryView(
            f"✓  {combined_options_total:,} combined schedule options available "
            f"({period_schedules_total:,} period schedules {loaded_text})",
            self._OK_STYLE,
        )
