from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QTextOption
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)
from qrcode import QRCode
from qrcode.constants import ERROR_CORRECT_M

from ui import theme

ROW_HEIGHT = 66
ROW_AVATAR = 46


def initial(name):
    for char in name or "":
        if char.isalnum():
            return char.upper()
    return "?"


def make_avatar(size):
    label = QLabel()
    label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def style_avatar(label, name, key, size):
    label.setText(initial(name))
    label.setStyleSheet(
        f"background: {theme.avatar_color(key)}; color: #ffffff; border-radius: {size // 2}px; "
        f"font-size: {int(size * 0.42)}px; font-weight: 600;"
    )


class QrWidget(QWidget):
    """QR-код рисуется прямо в окне: без файлов и без PIL."""

    SIZE = 300
    PADDING = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._matrix = None
        self._message = "Подключение…"

    def set_url(self, url):
        qr = QRCode(error_correction=ERROR_CORRECT_M, border=0)
        qr.add_data(url)
        qr.make(fit=True)
        self._matrix = qr.get_matrix()
        self.update()

    def set_message(self, text):
        self._matrix = None
        self._message = text
        self.update()

    def paintEvent(self, event):
        colors = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors["qr_bg"]))
        painter.drawRoundedRect(QRectF(self.rect()), 20, 20)

        if not self._matrix:
            painter.setPen(QColor("#6d7f8f"))
            painter.drawText(
                QRectF(self.rect()),
                self._message,
                QTextOption(Qt.AlignmentFlag.AlignCenter),
            )
            return

        # целый размер клетки: квадраты получаются чёткими, без щелей
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        count = len(self._matrix)
        cell = max(1, (self.SIZE - 2 * self.PADDING) // count)
        side = cell * count
        left = (self.width() - side) // 2
        top = (self.height() - side) // 2

        painter.setBrush(QColor(colors["qr_fg"]))
        for y, row in enumerate(self._matrix):
            for x, filled in enumerate(row):
                if filled:
                    painter.drawRect(left + x * cell, top + y * cell, cell, cell)


class StatCard(QFrame):
    def __init__(self, caption):
        super().__init__()
        self.setObjectName("statCard")
        self.setMinimumWidth(190)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(2)

        self.value = QLabel("…")
        self.value.setProperty("role", "value")
        label = QLabel(caption)
        label.setProperty("role", "muted")
        layout.addWidget(self.value)
        layout.addWidget(label)

    def set_value(self, text):
        self.value.setText(text)


class ChannelDelegate(QStyledItemDelegate):
    """Строка списка каналов: круглая аватарка, название и подпись."""

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(self, painter, option, index):
        info = index.data(Qt.ItemDataRole.UserRole)
        if info is None:
            return

        from ui.avatar import round_pixmap  # локальный импорт, чтобы избежать циклов

        colors = theme.palette()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        rect = option.rect.adjusted(6, 2, -6, -2)

        painter.setPen(Qt.PenStyle.NoPen)
        if selected or hovered:
            painter.setBrush(
                QColor(colors["selected"] if selected else colors["hover"])
            )
            painter.drawRoundedRect(rect, 10, 10)

        # аватарка
        ax = rect.left() + 10
        ay = rect.top() + (rect.height() - ROW_AVATAR) // 2

        pixmap = None
        if getattr(info, "avatar_path", None):
            pixmap = round_pixmap(info.avatar_path, ROW_AVATAR)

        if pixmap is not None:
            # реальное фото
            painter.drawPixmap(ax, ay, pixmap)
        else:
            # цветной круг + буква
            painter.setBrush(QColor(theme.avatar_color(info.id)))
            painter.drawEllipse(ax, ay, ROW_AVATAR, ROW_AVATAR)

            letter_font = QFont(option.font)
            letter_font.setPixelSize(20)
            letter_font.setBold(True)
            painter.setFont(letter_font)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(
                QRectF(ax, ay, ROW_AVATAR, ROW_AVATAR),
                initial(info.name),
                QTextOption(Qt.AlignmentFlag.AlignCenter),
            )

        # название и подпись
        text_x = ax + ROW_AVATAR + 12
        text_w = rect.right() - text_x - 10
        middle = rect.top() + rect.height() // 2

        title_font = QFont(option.font)
        title_font.setPixelSize(15)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(colors["on_selected"] if selected else colors["text"]))
        painter.drawText(
            text_x,
            middle - 4,
            QFontMetrics(title_font).elidedText(
                info.name, Qt.TextElideMode.ElideRight, text_w
            ),
        )

        subtitle = info.kind + (
            f" · @{info.username}" if info.username else " · приватный"
        )
        sub_font = QFont(option.font)
        sub_font.setPixelSize(12)
        sub_color = QColor(colors["on_selected"] if selected else colors["muted"])
        if selected:
            sub_color.setAlpha(200)
        painter.setFont(sub_font)
        painter.setPen(sub_color)
        painter.drawText(
            text_x,
            middle + 16,
            QFontMetrics(sub_font).elidedText(
                subtitle, Qt.TextElideMode.ElideRight, text_w
            ),
        )

        painter.restore()
