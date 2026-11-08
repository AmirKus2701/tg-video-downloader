from zlib import crc32

from PySide6.QtCore import QSize, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.avatar import show_avatar
from ui.download_panel import DownloadPanel
from ui.widgets import ROW_HEIGHT, ChannelDelegate, StatCard, make_avatar

SIDEBAR_WIDTH = 330
USER_AVATAR = 38


def fmt(number):
    return f"{number:,}".replace(",", " ")


class MainView(QWidget):
    channel_selected = Signal(object)  # ChannelInfo
    settings_requested = Signal()
    refresh_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_id = None
        self._summary_text = ""
        self._user = ""
        self.panel = DownloadPanel()

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_content(), 1)

    # ---------- левая панель ----------

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск каналов")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        summary_row = QHBoxLayout()
        summary_row.setContentsMargins(6, 0, 0, 0)
        summary_row.setSpacing(6)

        self.summary = QLabel("")
        self.summary.setProperty("role", "muted")
        self.summary.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.setProperty("role", "flat")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setToolTip("Обновить список каналов")
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)

        summary_row.addWidget(self.summary)
        summary_row.addWidget(self.refresh_btn)
        layout.addLayout(summary_row)

        self.list = QListWidget()
        self.list.setItemDelegate(ChannelDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list.currentItemChanged.connect(self._on_current)
        layout.addWidget(self.list, 1)

        divider = QFrame()
        divider.setObjectName("divider")
        layout.addWidget(divider)

        footer = QHBoxLayout()
        footer.setContentsMargins(4, 4, 0, 0)
        footer.setSpacing(10)
        self.user_avatar = make_avatar(USER_AVATAR)
        self.user_name = QLabel("")
        self.user_name.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        settings = QPushButton("Настройки")
        settings.setProperty("role", "flat")
        settings.clicked.connect(lambda: self.settings_requested.emit())
        footer.addWidget(self.user_avatar)
        footer.addWidget(self.user_name, 1)
        footer.addWidget(settings)
        layout.addLayout(footer)
        return sidebar

    # ---------- правая часть ----------

    def _build_content(self):
        self.pages = QStackedWidget()

        # страница 0: ничего не выбрано
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.addStretch(1)
        empty_title = QLabel("Выберите канал слева")
        empty_title.setProperty("role", "h2")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_hint = QLabel("Здесь появятся сведения о канале и панель скачивания.")
        empty_hint.setProperty("role", "muted")
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_hint)
        empty_layout.addStretch(1)
        self.pages.addWidget(empty)

        # страница 1: сведения о канале и скачивание
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 36, 40, 36)
        layout.setSpacing(22)

        header = QHBoxLayout()
        header.setSpacing(18)
        self.avatar = make_avatar(76)
        texts = QVBoxLayout()
        texts.setSpacing(4)
        self.title = QLabel("")
        self.title.setProperty("role", "title")
        self.title.setWordWrap(True)
        self.subtitle = QLabel("")
        self.subtitle.setProperty("role", "muted")
        self.id_label = QLabel("")
        self.id_label.setProperty("role", "muted")
        self.id_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        texts.addWidget(self.title)
        texts.addWidget(self.subtitle)
        texts.addWidget(self.id_label)
        header.addWidget(self.avatar)
        header.addLayout(texts, 1)
        layout.addLayout(header)

        stats = QHBoxLayout()
        stats.setSpacing(16)
        self.photos_card = StatCard("фото")
        self.videos_card = StatCard("видео")
        stats.addWidget(self.photos_card)
        stats.addWidget(self.videos_card)
        stats.addStretch(1)
        layout.addLayout(stats)

        layout.addWidget(self.panel)
        layout.addStretch(1)

        # окно может быть невысоким: вместо обрезания появляется прокрутка
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        page.setAutoFillBackground(False)  # после setWidget: Qt включает заливку сам
        scroll.viewport().setAutoFillBackground(False)
        self.pages.addWidget(scroll)
        return self.pages

    # ---------- данные ----------

    def _set_summary(self, text):
        self._summary_text = text
        self.summary.setText(text)

    def set_user(self, name, image=None):
        """Имя профиля и фото аккаунта (путь к файлу или None) внизу слева."""
        self._user = name
        self.user_name.setText(name)
        self.set_user_avatar(image)
        self._set_summary("Загрузка списка…")

    def set_user_avatar(self, image):
        # crc32 вместо hash(): цвет буквы не меняется от запуска к запуску
        show_avatar(
            self.user_avatar, self._user, crc32(self._user.encode()), USER_AVATAR, image
        )

    @Slot(object)
    def set_channels(self, channels):
        self.list.clear()
        for info in channels:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, info)
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            self.list.addItem(item)

        self._current_id = None
        self.pages.setCurrentIndex(0)
        self._set_summary(
            f"Каналов и групп: {len(channels)}" if channels else "Каналов не найдено"
        )
        self._filter(self.search.text())
        self.set_refreshing(False)  # ← добавь эту строку

    @Slot(object, int, int)
    def set_counts(self, channel_id, photos, videos):
        if channel_id == self._current_id:
            self.photos_card.set_value(fmt(photos))
            self.videos_card.set_value(fmt(videos))

    @Slot(object)
    def set_counts_failed(self, channel_id):
        if channel_id == self._current_id:
            self.photos_card.set_value("—")
            self.videos_card.set_value("—")

    @Slot(object, str)
    def set_channel_avatar(self, channel_id, path):
        """Обновляет аватарку конкретного канала в списке и справа, если канал выбран."""
        for row in range(self.list.count()):
            item = self.list.item(row)
            info = item.data(Qt.ItemDataRole.UserRole)
            if info and info.id == channel_id:
                info.avatar_path = path
                item.setData(Qt.ItemDataRole.UserRole, info)
                self.list.viewport().update()

                # если этот канал сейчас выбран — обновляем большую аватарку
                if channel_id == self._current_id:
                    from ui.avatar import show_avatar

                    show_avatar(self.avatar, info.name, info.id, 76, path)
                break

    def current_info(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def set_locked(self, locked):
        """Пока идёт скачивание, выбрать другой канал нельзя."""
        self.list.setEnabled(not locked)
        self.search.setEnabled(not locked)
        self.summary.setText("Идёт скачивание…" if locked else self._summary_text)

    def refresh(self):
        self.list.viewport().update()
        self.panel.refresh()

    # ---------- внутреннее ----------

    def _filter(self, text):
        query = text.strip().lower()
        for row in range(self.list.count()):
            item = self.list.item(row)
            info = item.data(Qt.ItemDataRole.UserRole)
            haystack = f"{info.name} {info.username} {info.id}".lower()
            item.setHidden(bool(query) and query not in haystack)

    def _on_current(self, current, previous):
        if current is None:
            self._current_id = None
            self.pages.setCurrentIndex(0)
            return

        info = current.data(Qt.ItemDataRole.UserRole)
        self._current_id = info.id

        # большая аватарка справа — теперь с реальным фото
        from ui.avatar import show_avatar

        show_avatar(
            self.avatar, info.name, info.id, 76, getattr(info, "avatar_path", None)
        )

        self.title.setText(info.name)
        username = f"@{info.username}" if info.username else "приватный, без username"
        self.subtitle.setText(f"{info.kind} · {username}")
        self.id_label.setText(f"ID: {info.id}")
        self.photos_card.set_value("…")
        self.videos_card.set_value("…")
        self.pages.setCurrentIndex(1)
        self.channel_selected.emit(info)

    def set_refreshing(self, refreshing: bool):
        """Блокирует кнопку и меняет текст во время обновления."""
        self.refresh_btn.setEnabled(not refreshing)
        if refreshing:
            self.summary.setText("Обновление…")
        else:
            # текст вернётся сам, когда придёт новый список каналов
            pass

    def set_locked(self, locked):
        """Пока идёт скачивание, выбрать другой канал нельзя."""
        self.list.setEnabled(not locked)
        self.search.setEnabled(not locked)
        self.refresh_btn.setEnabled(not locked)
        self.summary.setText("Идёт скачивание…" if locked else self._summary_text)
