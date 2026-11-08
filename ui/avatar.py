from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap

from ui.widgets import style_avatar

SHARPNESS = 2  # рисуем вдвое крупнее, чтобы аватарка была чёткой на экранах с масштабом


def round_pixmap(path, size):
    """Фото обрезается по центру до квадрата и вписывается в круг. None, если файл не открылся."""
    source = QPixmap(path)
    if source.isNull():
        return None

    side = size * SHARPNESS
    scaled = source.scaled(
        side,
        side,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )

    result = QPixmap(side, side)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addEllipse(0, 0, side, side)
    painter.setClipPath(clip)
    painter.drawPixmap(
        (side - scaled.width()) // 2, (side - scaled.height()) // 2, scaled
    )
    painter.end()

    result.setDevicePixelRatio(SHARPNESS)
    return result


def show_avatar(label, name, key, size, image_path=None):
    """Фото аккаунта в круге. Если фото нет, остаётся цветной круг с первой буквой имени."""
    pixmap = round_pixmap(image_path, size) if image_path else None
    label.clear()
    if pixmap is None:
        style_avatar(label, name, key, size)
        return
    label.setStyleSheet("background: transparent;")
    label.setPixmap(pixmap)
