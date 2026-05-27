import sys

from PyQt6.QtWidgets import QApplication

from src.ui.app import ExamSchedulerApp


def main() -> None:
    app = QApplication(sys.argv)
    window = ExamSchedulerApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
