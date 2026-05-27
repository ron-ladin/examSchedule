from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


PROGRAMME_COLOURS = [
    "#AED6F1",
    "#A9DFBF",
    "#F9E79F",
    "#F5CBA7",
    "#D2B4DE",
]


class CalendarGrid(QTableWidget):
    DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(7)
        self.setHorizontalHeaderLabels(self.DAYS)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

    def populate(self, assignments: dict, programme_colour_map: dict[str, str]) -> None:
        self.clearContents()
        self.setRowCount(0)
        if not assignments:
            return

        from datetime import date, timedelta
        dates = sorted(assignments.keys())
        start = dates[0]
        end = dates[-1]

        first_day = start - timedelta(days=start.weekday() + 1) % 7

        total_days = (end - first_day).days + 1
        rows = (total_days + 6) // 7
        self.setRowCount(rows)

        for r in range(rows):
            for c in range(7):
                d = first_day + timedelta(days=r * 7 + c)
                if d < start or d > end:
                    continue
                if d in assignments:
                    label, programme_id = assignments[d]
                    item = QTableWidgetItem(label)
                    colour = programme_colour_map.get(programme_id, "#FFFFFF")
                    item.setBackground(QColor(colour))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.setItem(r, c, item)
                else:
                    item = QTableWidgetItem(d.strftime("%d"))
                    item.setForeground(QColor("#AAAAAA"))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.setItem(r, c, item)
