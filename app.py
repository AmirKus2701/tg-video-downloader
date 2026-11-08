from sys import argv, exit as sys_exit

from PySide6.QtWidgets import QApplication

from core.settings import load_settings
from ui.cursor import HandCursor
from ui.main_window import APP_TITLE, MainWindow
from ui.theme import apply_theme


def main():
    app = QApplication(argv)
    app.setApplicationName(APP_TITLE)
    app.installEventFilter(HandCursor(app))  # курсор-рука на кнопках и ссылках

    settings = load_settings()
    apply_theme(app, settings["theme"])

    window = MainWindow(settings)
    window.show()
    sys_exit(app.exec())


if __name__ == "__main__":
    main()