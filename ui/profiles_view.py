from zlib import crc32

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.avatars import avatar_file
from core.settings import display_name
from ui.avatar import show_avatar
from ui.layout_utils import centered_scroll, fit_card
from ui.widgets import make_avatar

COLUMN_WIDTH = 640
AVATAR = 52


class ProfilesView(QWidget):
    opened = Signal(str)  # id профиля
    deleted = Signal(str)
    added = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.column = QWidget()
        self.column.setFixedWidth(COLUMN_WIDTH)
        layout = QVBoxLayout(self.column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title = QLabel("Профили")
        title.setProperty("role", "title")
        hint = QLabel(
            "Каждый профиль — отдельный аккаунт Telegram со своими ключами api_id и api_hash. "
            "Войти в профиль можно только тем аккаунтом, к которому он привязан."
        )
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(6)

        self.rows = QVBoxLayout()
        self.rows.setSpacing(12)
        layout.addLayout(self.rows)

        add = QPushButton("Добавить профиль")
        add.setProperty("role", "primary")
        add.clicked.connect(lambda: self.added.emit())
        layout.addSpacing(6)
        layout.addWidget(add, 0, Qt.AlignmentFlag.AlignLeft)

        centered_scroll(self, self.column)

    def _fit(self):
        fit_card(self.column, COLUMN_WIDTH)

    def showEvent(self, event):
        super().showEvent(event)
        self._fit()
        QTimer.singleShot(0, self._fit)

    def set_profiles(self, profiles):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for profile in profiles:
            self.rows.addWidget(self._row(profile))
        QTimer.singleShot(0, self._fit)

    def _row(self, profile):
        card = QFrame()
        card.setObjectName("card")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        name = display_name(profile)
        avatar = make_avatar(AVATAR)
        # фото аккаунта из кэша; пока его нет (или у аккаунта нет фото), показывается буква
        show_avatar(
            avatar,
            name,
            crc32(profile["id"].encode()),
            AVATAR,
            avatar_file(profile["id"]),
        )

        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = QLabel(name)
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        status = (
            "привязан к аккаунту Telegram"
            if profile.get("tg_user_id")
            else "ждёт первого входа"
        )
        subtitle = QLabel(f"Ключи сохранены · {status}")
        subtitle.setProperty("role", "muted")
        texts.addWidget(title)
        texts.addWidget(subtitle)

        profile_id = profile["id"]
        open_button = QPushButton("Открыть")
        open_button.setProperty("role", "primary")
        open_button.clicked.connect(
            lambda checked=False, pid=profile_id: self.opened.emit(pid)
        )
        delete_button = QPushButton("Удалить")
        delete_button.setProperty("role", "danger")
        delete_button.clicked.connect(
            lambda checked=False, pid=profile_id: self.deleted.emit(pid)
        )

        layout.addWidget(avatar)
        layout.addLayout(texts, 1)
        layout.addWidget(open_button)
        layout.addWidget(delete_button)
        return card
