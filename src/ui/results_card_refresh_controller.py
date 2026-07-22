"""Period card refresh and calendar click flow for Results panel."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint

from src.controller import LOAD_BATCH_SIZE
from src.ui.calendar_cell_delegate import _course_ids_for_click_position

if TYPE_CHECKING:  # pragma: no cover - imported only for type checkers.
    from src.ui.results_panel import _ResultsPanel

_AUTO_MODE_DATES = "dates"
_AUTO_MODE_VARIANTS = "variants"


class ResultsCardRefreshController:
    """Refresh period cards and handle calendar cell interactions."""

    def __init__(
        self,
        panel: "_ResultsPanel",
        *,
        display_period_key: Callable[[str], str],
    ) -> None:
        self._panel = panel
        self._display_period_key = display_period_key

    def refresh_period_card(self, period_key: str) -> None:
        self.refresh_period_card_ui(period_key, repaint_calendar=True)

    def refresh_period_card_counters(self, period_key: str) -> None:
        self.refresh_period_card_ui(period_key, repaint_calendar=False)

    def refresh_period_card_ui(
        self,
        period_key: str,
        *,
        repaint_calendar: bool,
    ) -> None:
        panel = self._panel
        schedules = panel._schedules_by_period[period_key]
        total = len(schedules)
        has_more = (
            False
            if panel._is_imported_schedule
            else panel._controller.has_more_schedules(period_key)
        )
        card = panel._cards.get(period_key)

        options = panel._date_options_for_period(period_key)
        index_nav = panel._nav_model.index_nav(period_key)

        if total > 0:
            idx = panel._period_indices.get(period_key, 0)
            if idx < 0 or idx >= total:
                idx = 0
                panel._period_indices[period_key] = idx

            nav_pos = index_nav.get(idx)
            if nav_pos is None:
                panel._rebuild_navigation_cache(period_key)
                options = panel._date_options_for_period(period_key)
                index_nav = panel._nav_model.index_nav(period_key)
                nav_pos = index_nav.get(idx)
        else:
            idx = 0
            nav_pos = None

        if total == 0 or nav_pos is None or not options:
            date_nav_text = "Date option: 0 / 0"
            variant_nav_text = "Variant: 0 / 0"
            same_date_indices: list[int] = []
            date_option_pos = -1
            variant_pos = -1

            if card is not None:
                card.empty_label.setText(
                    f"No schedules were generated for {self._display_period_key(period_key)}."
                )
                card.empty_label.setVisible(True)
                card.cal_table.setVisible(False)
        else:
            date_option_pos, variant_pos = nav_pos
            same_date_indices = options[date_option_pos][1]

            date_total_text = f"{len(options):,}"
            if has_more:
                date_total_text += "+"

            date_nav_text = (
                f"Date option: {date_option_pos + 1:,} / {date_total_text}"
            )
            variant_nav_text = (
                f"Variant for these dates: {variant_pos + 1:,} / {len(same_date_indices):,}"
            )

            if card is not None:
                card.empty_label.setVisible(False)
                card.cal_table.setVisible(True)

        if card is None:
            panel._update_summary()
            return

        card.date_counter_label.setText(date_nav_text)
        card.counter_label.setText(variant_nav_text)

        card.date_jump_input.setEnabled(total > 0)
        card.date_jump_input.setPlaceholderText(
            str(date_option_pos + 1)
            if total > 0 and date_option_pos >= 0
            else "#"
        )

        card.variant_jump_input.setEnabled(total > 0)
        card.variant_jump_input.setPlaceholderText(
            str(variant_pos + 1)
            if total > 0 and variant_pos >= 0
            else "#"
        )

        card.prev_date_btn.setEnabled(total > 0 and date_option_pos > 0)
        card.next_date_btn.setEnabled(
            total > 0 and (date_option_pos < len(options) - 1 or has_more)
        )

        if total > 0 and same_date_indices:
            card.prev_btn.setEnabled(variant_pos > 0)
            card.next_btn.setEnabled(variant_pos < len(same_date_indices) - 1)
        else:
            card.prev_btn.setEnabled(False)
            card.next_btn.setEnabled(False)

        card.load_more_btn.setVisible(has_more)
        ranking_active = panel.is_ranking_active()
        card.load_more_btn.setEnabled(
            has_more
            and period_key not in panel._lm.procs
            and period_key not in panel._lm.auto_load_periods
            and not ranking_active
        )
        if ranking_active and has_more:
            card.load_more_btn.setText("Ranking in progress")
        elif has_more and period_key not in panel._lm.procs:
            card.load_more_btn.setText(f"⟳  +{LOAD_BATCH_SIZE:,} more options")

        active_mode = panel._lm.auto_load_modes.get(period_key)
        if not has_more and active_mode == _AUTO_MODE_DATES:
            panel._lm.stop_auto_load(period_key, refresh=False)

        has_classroom_variants = panel._has_classroom_feature_results(period_key)
        card.variant_navigation.setVisible(has_classroom_variants)
        card.auto_date_btn.setVisible(
            not panel._is_imported_schedule
            and (has_more or active_mode == _AUTO_MODE_DATES)
        )
        card.auto_variant_btn.setVisible(
            not panel._is_imported_schedule
            and (has_classroom_variants or active_mode == _AUTO_MODE_VARIANTS)
        )

        if not panel._is_imported_schedule:
            panel._lm.update_auto_load_button(period_key)
        panel._refresh_favorite_buttons()

        if not repaint_calendar:
            panel._update_summary()
            return

        if schedules:
            panel._cell_data[period_key] = panel._calendar.populate(
                card.cal_table,
                schedules[panel._period_indices[period_key]],
                panel._courses_by_id,
                panel._prog_color_map,
                period_key,
            )
        else:
            card.cal_table.clearContents()
            card.cal_table.setRowCount(0)

        panel._update_summary()

    def on_cell_clicked(
        self,
        period_key: str,
        row: int,
        col: int,
        click_pos: QPoint | None = None,
    ) -> None:
        panel = self._panel
        cell_info = panel._cell_data.get(period_key, {}).get((row, col))

        if cell_info is None:
            return

        exam_date, course_ids, classroom_assignments, unassigned_exams, groups = (
            cell_info
        )

        if not course_ids:
            return

        all_course_ids = list(course_ids)
        all_classroom_assignments = classroom_assignments
        all_unassigned_exams = unassigned_exams

        visible_ids = self.slot_filter_for_click(
            period_key, row, col, groups, click_pos
        )
        if visible_ids is not None:
            course_ids = visible_ids
            classroom_assignments = {
                cid: classroom_assignments.get(cid, []) for cid in course_ids
            }
            unassigned_exams = {
                cid: unassigned_exams[cid]
                for cid in course_ids
                if cid in unassigned_exams
            }

        from src.ui.exam_detail_dialog import ExamDetailDialog

        dialog = ExamDetailDialog(
            exam_date,
            course_ids,
            panel._courses_by_id,
            panel._prog_color_map,
            classroom_assignments,
            unassigned_exams,
            parent=panel,
            all_course_ids=all_course_ids,
            all_classroom_assignments=all_classroom_assignments,
            all_unassigned_exams=all_unassigned_exams,
        )
        dialog.exec()

    def slot_filter_for_click(
        self,
        period_key: str,
        row: int,
        col: int,
        groups: "list[dict] | None",
        click_pos: QPoint | None = None,
    ) -> "list[str] | None":
        """Return the course ids of the slot column under the cursor, or None."""
        if not groups or click_pos is None:
            return None

        card = self._panel._cards.get(period_key)
        table = card.cal_table if card else None
        if table is None:
            return None

        item = table.item(row, col)
        if item is None:
            return None

        rect = table.visualItemRect(item)
        if rect.width() <= 0:
            return None

        return _course_ids_for_click_position(groups, rect, click_pos)
