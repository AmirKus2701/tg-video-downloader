from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QTextOption
from PySide6.QtWidgets import QCheckBox

from ui import theme

BOX = 22
GAP = 10


class CheckBox(QCheckBox):
    """Флажок в стиле приложения: рисуется кодом, поэтому одинаково выглядит в обеих темах."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def sizeHint(self):
        self.ensurePolished()  # шрифт из стиля должен примениться до расчёта ширины
        metrics = self.fontMetrics()
        width = BOX + GAP + metrics.horizontalAdvance(self.text()) + 6
        return QSize(width, max(BOX, metrics.height()) + 8)

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        colors = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.45)

        box = QRectF(1, (self.height() - BOX) / 2, BOX, BOX)
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(colors["accent"]))
            painter.drawRoundedRect(box, 6, 6)

            pen = QPen(QColor("#ffffff"), 2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            tick = QPainterPath()
            tick.moveTo(box.left() + BOX * 0.27, box.top() + BOX * 0.54)
            tick.lineTo(box.left() + BOX * 0.44, box.top() + BOX * 0.70)
            tick.lineTo(box.left() + BOX * 0.75, box.top() + BOX * 0.34)
            painter.drawPath(tick)
        else:
            painter.setPen(QPen(QColor(colors["muted"]), 1.6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(box.adjusted(0.8, 0.8, -0.8, -0.8), 6, 6)

        option = QTextOption(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        option.setWrapMode(QTextOption.WrapMode.NoWrap)
        painter.setPen(QColor(colors["text"]))
        text_rect = QRectF(BOX + GAP + 1, 0, self.width() - BOX - GAP - 1, self.height())
        painter.drawText(text_rect, self.text(), option)