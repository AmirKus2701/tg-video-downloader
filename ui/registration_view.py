from PySide6.QtCore import QPointF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ui import theme
from ui.layout_utils import centered_scroll, fit_card

MY_TELEGRAM = "https://my.telegram.org"

CARD_WIDTH = 860
FIELD_HEIGHT = 52
FIELD_STYLE = "padding: 14px 16px; font-size: 15px;"

STEPS = (
    "Откройте my.telegram.org и введите номер телефона в международном формате, например +77011234567.",
    "Код входа придёт сообщением в приложение Telegram (чат «Telegram»), а не по SMS. Введите его на сайте.",
    "Откройте «API development tools» и заполните форму: App title и Short name — любые "
    "(Short name латиницей, без пробелов), Platform — Desktop, URL оставьте пустым. "
    "Нажмите «Create application».",
    "Скопируйте App api_id (число) и App api_hash (32 символа).",
    "Вставьте их справа. Имя профиля приложение спросит после первого входа.",
)


def eye_icon(color, crossed):
    """Иконка глазка рисуется кодом, поэтому отдельные файлы не нужны."""
    ratio = 2
    pixmap = QPixmap(24 * ratio, 24 * ratio)
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    outline = QPainterPath()
    outline.moveTo(2.5, 12)
    outline.quadTo(12, 3, 21.5, 12)
    outline.quadTo(12, 21, 2.5, 12)
    painter.drawPath(outline)
    painter.drawEllipse(QPointF(12, 12), 3.2, 3.2)
    if crossed:
        painter.drawLine(QPointF(4, 20), QPointF(20, 4))
    painter.end()
    return QIcon(pixmap)


class SecretField(QLineEdit):
    """Поле, скрытое точками, с глазком справа: клик показывает или скрывает значение."""

    def __init__(self, placeholder, on_enter):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(FIELD_HEIGHT)
        self.setStyleSheet(FIELD_STYLE)
        self.setEchoMode(QLineEdit.EchoMode.Password)
        self.returnPressed.connect(on_enter)

        self._toggle = QAction(self)
        self._toggle.triggered.connect(self._flip)
        self.addAction(self._toggle, QLineEdit.ActionPosition.TrailingPosition)
        self.refresh_icon()

    def revealed(self):
        return self.echoMode() == QLineEdit.EchoMode.Normal

    def _flip(self):
        self.setEchoMode(QLineEdit.EchoMode.Password if self.revealed() else QLineEdit.EchoMode.Normal)
        self.refresh_icon()

    def hide_text(self):
        self.setEchoMode(QLineEdit.EchoMode.Password)
        self.refresh_icon()

    def refresh_icon(self):
        color = theme.palette()["muted"]
        shown = self.revealed()
        # значение скрыто: глазок открыт (нажмите, чтобы показать); значение видно: глазок перечёркнут
        self._toggle.setIcon(eye_icon(color, crossed=shown))
        self._toggle.setToolTip("Скрыть" if shown else "Показать")


class RegistrationView(QWidget):
    submitted = Signal(str, str)   # api_id, api_hash
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.card = QFrame()
        self.card.setObjectName("card")
        self.card.setFixedWidth(CARD_WIDTH)
        body = QHBoxLayout(self.card)
        body.setContentsMargins(40, 36, 40, 36)
        body.setSpacing(44)
        body.addLayout(self._build_guide(), 1)
        body.addLayout(self._build_form(), 1)

        centered_scroll(self, self.card)

    # ---------- левая часть: инструктаж ----------

    def _build_guide(self):
        column = QVBoxLayout()
        column.setSpacing(14)

        title = QLabel("Как получить ключи")
        title.setProperty("role", "h2")
        column.addWidget(title)

        for number, text in enumerate(STEPS, start=1):
            column.addLayout(self._step(number, text))

        open_site = QPushButton("Открыть my.telegram.org")
        open_site.setProperty("role", "flat")
        open_site.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(MY_TELEGRAM)))
        column.addWidget(open_site, 0, Qt.AlignmentFlag.AlignLeft)

        note = QLabel("Если сайт показывает «ERROR», отключите VPN, попробуйте другой браузер "
                      "или повторите позже.")
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        column.addWidget(note)
        column.addStretch(1)
        return column

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

    # ---------- правая часть: поля ----------

    def _build_form(self):
        column = QVBoxLayout()
        column.setSpacing(14)

        title = QLabel("Ваши ключи")
        title.setProperty("role", "h2")
        intro = QLabel("Ключи принадлежат только вам: у каждого человека должны быть свои. "
                       "Не показывайте api_hash другим.")
        intro.setProperty("role", "muted")
        intro.setWordWrap(True)
        column.addWidget(title)
        column.addWidget(intro)

        self.api_id = SecretField("api_id (только цифры)", self._submit)
        self.api_hash = SecretField("api_hash (32 символа)", self._submit)
        column.addSpacing(4)
        column.addWidget(self.api_id)
        column.addWidget(self.api_hash)

        self.error = QLabel("")
        self.error.setProperty("role", "error")
        self.error.setWordWrap(True)
        self.error.hide()
        column.addWidget(self.error)

        bind = QLabel("Профиль привяжется к аккаунту Telegram, с которого вы войдёте первым. "
                      "Другой аккаунт войти в него не сможет.")
        bind.setProperty("role", "muted")
        bind.setWordWrap(True)
        column.addWidget(bind)
        column.addStretch(1)

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
        column.addLayout(buttons)
        return column

    # ---------- размеры ----------

    def _fit(self):
        fit_card(self.card, CARD_WIDTH)

    def showEvent(self, event):
        super().showEvent(event)
        self.api_id.refresh_icon()    # на случай, если тему сменили, пока экран был закрыт
        self.api_hash.refresh_icon()
        self._fit()
        QTimer.singleShot(0, self._fit)  # повторно, когда шрифты и стили уже применены
        self.api_id.setFocus()

    # ---------- данные ----------

    def clear(self):
        """Поля всегда пустые и скрытые: ключи вводит пользователь."""
        self.api_id.clear()
        self.api_hash.clear()
        self.api_id.hide_text()
        self.api_hash.hide_text()
        self._hide_error()

    def set_values(self, api_id, api_hash):
        """Вернуть введённое, чтобы исправить опечатку. Значения остаются скрытыми."""
        self.api_id.setText(api_id)
        self.api_hash.setText(api_hash)

    def set_back_visible(self, visible):
        self.back_button.setVisible(visible)

    def show_error(self, text):
        self.error.setText(text)
        self.error.show()
        QTimer.singleShot(0, self._fit)

    def _hide_error(self):
        self.error.hide()
        QTimer.singleShot(0, self._fit)

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