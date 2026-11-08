from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget


def fit_card(card, width):
    """Qt занижает высоту текста с переносом строк, поэтому подгоняем высоту карточки вручную."""
    layout = card.layout()
    layout.invalidate()
    needed = layout.heightForWidth(width) if layout.hasHeightForWidth() else -1
    card.setMinimumHeight(max(layout.sizeHint().height(), needed))


def centered_scroll(page, card):
    """Карточка по центру страницы; если окно мало, появляется прокрутка вместо обрезания."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    inner = QWidget()
    layout = QVBoxLayout(inner)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.addStretch(1)
    layout.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
    layout.addStretch(1)

    scroll.setWidget(inner)
    inner.setAutoFillBackground(False)  # после setWidget: Qt включает заливку сам
    scroll.viewport().setAutoFillBackground(False)

    outer = QVBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(scroll)