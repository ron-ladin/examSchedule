from PyQt6.QtWidgets import QMainWindow, QStackedWidget, QMessageBox

from src.ui.input_screen import InputScreen
from src.ui.output_screen import OutputScreen
from src.interfaces.i_output_exporter import IOutputExporter


class ExamSchedulerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Exam Schedule Generator")
        self.setMinimumSize(1000, 700)

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._input_screen = InputScreen(on_generate=self._run_generation)
        self._output_screen = OutputScreen(on_back=self._show_input)

        self._stack.addWidget(self._input_screen)
        self._stack.addWidget(self._output_screen)
        self._stack.setCurrentWidget(self._input_screen)

    def _show_input(self) -> None:
        self._stack.setCurrentWidget(self._input_screen)

    def _show_output(self, schedules: list, programmes: list[str]) -> None:
        self._output_screen.load_schedules(schedules, programmes)
        self._stack.setCurrentWidget(self._output_screen)

    def _run_generation(self, courses: list, periods: list, selected_programmes: list[str]) -> None:
        try:
            from src.engine.app_controller import AppController
            from src.engine.schedule_generator import ScheduleGenerator
            from src.adapters.exact_conflict_strategy import ExactConflictStrategy
            from src.adapters.in_memory_data_provider import InMemoryDataProvider

            provider = InMemoryDataProvider(courses, periods)
            schedules: list = []

            class ListExporter(IOutputExporter):
                def export_schedules(self, schedules_by_period, courses_by_id):
                    for period_iter in schedules_by_period.values():
                        schedules.extend(period_iter)

            exporter = ListExporter()
            controller = AppController(
                data_provider=provider,
                exporter=exporter,
                generator=ScheduleGenerator(ExactConflictStrategy(selected_programmes)),
                selected_programs=selected_programmes,
            )
            controller.run()

            for s in schedules:
                s.courses = courses

            self._show_output(schedules, selected_programmes)

        except Exception as exc:
            QMessageBox.critical(self, "Generation Error", str(exc))
