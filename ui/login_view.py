from math import ceil
from time import monotonic

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from ui.layout_utils import centered_scroll, fit_card
from ui.widgets import QrWidget

CARD_WIDTH = 860

STEPS = (
    "Откройте Telegram на телефоне.",
    "Перейдите в Настройки → Устройства → Подключить устройство.",
    "Наведите камеру на этот QR-код.",
)


class LoginView(QWidget):
    retry = Signal()
    show_profiles = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._deadline = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)

        self.card = QFrame()
        self.card.setObjectName("card")
        self.card.setFixedWidth(CARD_WIDTH)
        body = QHBoxLayout(self.card)
        body.setContentsMargins(44, 44, 44, 44)
        body.setSpacing(48)

        # левая часть: QR и отсчёт
        left = QVBoxLayout()
        left.setSpacing(14)
        self.qr = QrWidget()
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 300)
        self.bar.setValue(0)
        self.countdown = QLabel("")
        self.countdown.setProperty("role", "muted")
        self.countdown.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.qr)
        left.addWidget(self.bar)
        left.addWidget(self.countdown)
        left.addStretch(1)

        # правая часть: инструкция
        right = QVBoxLayout()
        right.setSpacing(16)
        title = QLabel("Вход в Telegram по QR-коду")
        title.setProperty("role", "title")
        title.setWordWrap(True)
        self.profile_label = QLabel("")
        self.profile_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        right.addWidget(title)
        right.addWidget(self.profile_label)
        for number, text in enumerate(STEPS, start=1):
            right.addLayout(self._step(number, text))

        self.bind_note = QLabel("")
        self.bind_note.setProperty("role", "muted")
        self.bind_note.setWordWrap(True)
        right.addWidget(self.bind_note)

        note = QLabel("Если включена двухфакторная защита, после сканирования появится запрос облачного пароля.")
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        right.addWidget(note)

        self.status = QLabel("")
        self.status.setProperty("role", "error")
        self.status.setWordWrap(True)
        self.status.hide()
        right.addWidget(self.status)
        right.addStretch(1)

        buttons = QHBoxLayout()
        self.retry_button = QPushButton("Повторить")
        self.retry_button.setProperty("role", "primary")
        self.retry_button.clicked.connect(lambda: self.retry.emit())
        self.retry_button.hide()
        profiles = QPushButton("Профили")
        profiles.setProperty("role", "flat")
        profiles.clicked.connect(lambda: self.show_profiles.emit())
        buttons.addWidget(self.retry_button)
        buttons.addWidget(profiles)
        buttons.addStretch(1)
        right.addLayout(buttons)

        body.addLayout(left)
        body.addLayout(right, 1)

        centered_scroll(self, self.card)

    @staticmethod
    def _step(number, text):
        row = QHBoxLayout()
        row.setSpacing(14)
        badge = QLabel(str(number))
        badge.setProperty("role", "step")
        badge.setFixedSize(26, 26)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(text)
        label.setWordWrap(True)
        row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(label, 1)
        return row

    # ---------- размеры ----------

    def _fit(self):
        fit_card(self.card, CARD_WIDTH)

    def showEvent(self, event):
        super().showEvent(event)
        self._fit()
        QTimer.singleShot(0, self._fit)

    # ---------- состояния ----------

    def set_profile(self, name, bound):
        self.profile_label.setText(f"Профиль: {name}")
        if bound:
            self.bind_note.setText("Войти можно только тем аккаунтом Telegram, к которому привязан этот профиль.")
        else:
            self.bind_note.setText("Профиль привяжется к аккаунту, с которого вы войдёте первым. "
                                   "Другой аккаунт в него войти уже не сможет.")
        QTimer.singleShot(0, self._fit)

    @Slot()
    def show_connecting(self):
        self._timer.stop()
        self.qr.set_message("Подключение…")
        self.bar.setValue(0)
        self.countdown.setText("")
        self.status.hide()
        self.retry_button.hide()
        QTimer.singleShot(0, self._fit)

    @Slot(str, int)
    def show_qr(self, url, lifetime):
        self._deadline = monotonic() + lifetime
        self.bar.setRange(0, lifetime * 10)
        self.qr.set_url(url)
        self.status.hide()
        self.retry_button.hide()
        self._tick()
        self._timer.start()
        QTimer.singleShot(0, self._fit)

    @Slot(str)
    def show_error(self, text):
        self._timer.stop()
        self.bar.setValue(0)
        self.countdown.setText("")
        self.qr.set_message("Не удалось подключиться")
        self.status.setText(text)
        self.status.show()
        self.retry_button.show()
        QTimer.singleShot(0, self._fit)

    def _tick(self):
        left = max(0.0, self._deadline - monotonic())
        self.bar.setValue(int(left * 10))
        self.countdown.setText(f"Код обновится через {ceil(left)} с" if left > 0 else "Обновляю код…")