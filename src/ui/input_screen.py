from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QFileDialog, QButtonGroup,
    QRadioButton, QMessageBox,
)
from PyQt6.QtCore import Qt
from pathlib import Path


class InputScreen(QWidget):
    def __init__(self, on_generate, parent=None):
        super().__init__(parent)
        self._on_generate = on_generate
        self._courses_path: Path | None = None
        self._dates_path: Path | None = None
        self._courses: list = []
        self._periods: list = []
        self._all_programme_ids: list[str] = []

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_file_panel())
        layout.addWidget(self._build_programme_panel())
        layout.addWidget(self._build_generate_panel())

    def _build_file_panel(self) -> QGroupBox:
        box = QGroupBox("1. Load Data Files")
        layout = QVBoxLayout(box)

        # Mode
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Load mode:"))
        self._mode_group = QButtonGroup(self)
        for label in ("Replace", "Append", "Update"):
            rb = QRadioButton(label)
            self._mode_group.addButton(rb)
            mode_row.addWidget(rb)
        self._mode_group.buttons()[0].setChecked(True)
        layout.addLayout(mode_row)

        # Courses
        courses_row = QHBoxLayout()
        self._courses_label = QLabel("No file loaded")
        btn_courses = QPushButton("Load Courses File…")
        btn_courses.clicked.connect(self._load_courses)
        courses_row.addWidget(btn_courses)
        courses_row.addWidget(self._courses_label, 1)
        layout.addLayout(courses_row)

        # Dates
        dates_row = QHBoxLayout()
        self._dates_label = QLabel("No file loaded")
        btn_dates = QPushButton("Load Dates File…")
        btn_dates.clicked.connect(self._load_dates)
        dates_row.addWidget(btn_dates)
        dates_row.addWidget(self._dates_label, 1)
        layout.addLayout(dates_row)

        return box

    def _build_programme_panel(self) -> QGroupBox:
        box = QGroupBox("2. Select Study Programmes (max 5)")
        layout = QVBoxLayout(box)
        self._programme_list = QListWidget()
        self._programme_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self._programme_list.itemSelectionChanged.connect(self._enforce_max_programmes)
        layout.addWidget(self._programme_list)
        self._programme_hint = QLabel("Load a courses file first")
        layout.addWidget(self._programme_hint)
        return box

    def _build_generate_panel(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.addStretch()
        btn = QPushButton("Generate Schedules")
        btn.setFixedHeight(40)
        btn.clicked.connect(self._generate)
        layout.addWidget(btn)
        return widget

    def _load_courses(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select courses file", "", "Text files (*.txt);;All files (*)")
        if not path:
            return
        self._courses_path = Path(path)
        try:
            from src.adapters.readers.course_file_reader import CourseFileReader
            mode = self._mode_group.checkedButton().text().lower()
            new_courses = list(CourseFileReader(self._courses_path).read())
            if mode == "replace":
                self._courses = new_courses
            elif mode == "append":
                self._courses = list({c.id: c for c in self._courses + new_courses}.values())
            else:
                existing = {c.id: c for c in self._courses}
                existing.update({c.id: c for c in new_courses})
                self._courses = list(existing.values())
            self._courses_label.setText(f"{self._courses_path.name} ({len(self._courses)} courses)")
            self._refresh_programme_list()
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))

    def _load_dates(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select dates file", "", "Text files (*.txt);;All files (*)")
        if not path:
            return
        self._dates_path = Path(path)
        try:
            from src.adapters.readers.exam_period_file_reader import ExamPeriodFileReader
            mode = self._mode_group.checkedButton().text().lower()
            new_periods = list(ExamPeriodFileReader(self._dates_path).read())
            if mode == "replace":
                self._periods = new_periods
            else:
                self._periods = list({(p.semester, p.moed): p for p in self._periods + new_periods}.values())
            self._dates_label.setText(f"{self._dates_path.name} ({len(self._periods)} periods)")
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))

    def _refresh_programme_list(self):
        ids = sorted({o.program_id for c in self._courses for o in c.offerings})
        self._all_programme_ids = ids
        self._programme_list.clear()
        for pid in ids:
            item = QListWidgetItem(pid)
            self._programme_list.addItem(item)
        self._programme_hint.setText(f"{len(ids)} programmes available")

    def _enforce_max_programmes(self):
        selected = self._programme_list.selectedItems()
        if len(selected) > 5:
            last = selected[-1]
            last.setSelected(False)
            self._programme_hint.setText("Maximum 5 programmes allowed")
        else:
            self._programme_hint.setText(f"{len(selected)} / 5 selected")

    def _generate(self):
        if not self._courses:
            QMessageBox.warning(self, "Missing Data", "Please load a courses file first.")
            return
        if not self._periods:
            QMessageBox.warning(self, "Missing Data", "Please load a dates file first.")
            return
        selected = [item.text() for item in self._programme_list.selectedItems()]
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select at least one programme.")
            return
        self._on_generate(self._courses, self._periods, selected)
