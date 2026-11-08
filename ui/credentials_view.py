from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

MY_TELEGRAM = "https://my.telegram.org"

CARD_WIDTH = 580
FIELD_HEIGHT = 52
FIELD_STYLE = "padding: 14px 16px; font-size: 15px;"  # выше и просторнее, цвета берутся из общей темы

STEPS = (
    "Откройте my.telegram.org и войдите по номеру телефона (код придёт в приложение Telegram).",
    "Выберите «API development tools» и создайте приложение: название и короткое имя могут быть любыми.",
    "Скопируйте api_id и api_hash в поля ниже.",
)


class CredentialsView(QWidget):
    submitted = Signal(str, str)   # api_id, api_hash
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.card = QFrame()
        self.card.setObjectName("card")
        self.card.setFixedWidth(CARD_WIDTH)
        body = QVBoxLayout(self.card)
        body.setContentsMargins(40, 36, 40, 36)
        body.setSpacing(14)

        title = QLabel("Подключение к Telegram")
        title.setProperty("role", "title")
        intro = QLabel("Для входа нужны ключи вашего приложения Telegram: api_id и api_hash. "
                       "Они бесплатные и хранятся только на этом компьютере.")
        intro.setProperty("role", "muted")
        intro.setWordWrap(True)
        body.addWidget(title)
        body.addWidget(intro)

        for number, text in enumerate(STEPS, start=1):
            body.addLayout(self._step(number, text))

        open_site = QPushButton("Открыть my.telegram.org")
        open_site.setProperty("role", "flat")
        open_site.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(MY_TELEGRAM)))
        body.addWidget(open_site, 0, Qt.AlignmentFlag.AlignLeft)

        self.api_id = self._field("api_id (только цифры)")
        self.api_hash = self._field("api_hash (32 символа)")
        body.addSpacing(4)
        body.addWidget(self.api_id)
        body.addWidget(self.api_hash)

        self.error = QLabel("")
        self.error.setProperty("role", "error")
        self.error.setWordWrap(True)
        self.error.hide()
        body.addWidget(self.error)

        buttons = QHBoxLayout()
        self.back_button = QPushButton("Назад")
        self.back_button.setProperty("role", "flat")
        self.back_button.clicked.connect(lambda: self.back.emit())
        submit = QPushButton("Продолжить")
        submit.setProperty("role", "primary")
        submit.clicked.connect(self._submit)
        buttons.addWidget(self.back_button)
        buttons.addStretch(1)
        buttons.addWidget(submit)
        body.addSpacing(6)
        body.addLayout(buttons)

        outer = QVBoxLayout(self)
        outer.addStretch(1)
        outer.addWidget(self.card, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)

    def _field(self, placeholder):
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        field.setMinimumHeight(FIELD_HEIGHT)
        field.setStyleSheet(FIELD_STYLE)
        field.returnPressed.connect(self._submit)
        return field

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

    # ---------- высота карточки ----------

    def _fit_card(self):
        """Qt занижает высоту текста с переносом строк, поэтому подгоняем карточку вручную."""
        layout = self.card.layout()
        layout.invalidate()
        needed = layout.heightForWidth(CARD_WIDTH) if layout.hasHeightForWidth() else -1
        self.card.setMinimumHeight(max(layout.sizeHint().height(), needed))

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_card()
        QTimer.singleShot(0, self._fit_card)  # повторно, когда шрифты и стили уже применены
        self.api_id.setFocus()

    def show_error(self, text):
        self.error.setText(text)
        self.error.show()
        QTimer.singleShot(0, self._fit_card)

    def _hide_error(self):
        self.error.hide()
        QTimer.singleShot(0, self._fit_card)

    # ---------- данные ----------

    def clear(self):
        """Поля всегда пустые: ключи вводит пользователь."""
        self.api_id.clear()
        self.api_hash.clear()
        self._hide_error()

    def set_back_visible(self, visible):
        self.back_button.setVisible(visible)

    def _submit(self):
        api_id = self.api_id.text().strip()
        api_hash = self.api_hash.text().strip()
        if not api_id.isdigit():
            self.show_error("api_id — это число, только цифры.")
            return
        if len(api_hash) != 32 or not (api_hash.isascii() and api_hash.isalnum()):
            self.show_error("api_hash — это строка из 32 символов (буквы и цифры).")
            return
        self._hide_error()
        self.submitted.emit(api_id, api_hash)