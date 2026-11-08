from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class SettingsDialog(QDialog):
    theme_changed = Signal(str)
    switch_requested = Signal()
    logout_requested = Signal()

    def __init__(self, parent, account_text, theme_name):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setModal(True)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(14)

        title = QLabel("Настройки")
        title.setProperty("role", "h2")
        account = QLabel(account_text)
        account.setProperty("role", "muted")
        account.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(account)

        layout.addWidget(QLabel("Тема оформления"))
        self.theme = QComboBox()
        self.theme.addItem("Тёмная", "dark")
        self.theme.addItem("Светлая", "light")
        self.theme.setCurrentIndex(max(0, self.theme.findData(theme_name)))
        self.theme.currentIndexChanged.connect(self._on_theme)
        layout.addWidget(self.theme)

        layout.addSpacing(8)
        switch = QPushButton("Сменить профиль")
        switch.clicked.connect(self._on_switch)
        layout.addWidget(switch)

        logout = QPushButton("Выйти из аккаунта")
        logout.setProperty("role", "danger")
        logout.clicked.connect(self._on_logout)
        layout.addWidget(logout)

        buttons = QHBoxLayout()
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addSpacing(6)
        layout.addLayout(buttons)

    def _on_theme(self, index):
        self.theme_changed.emit(self.theme.itemData(index))

    def _on_switch(self):
        self.switch_requested.emit()
        self.accept()

    def _on_logout(self):
        self.logout_requested.emit()
        self.accept()