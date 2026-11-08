from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractButton, QComboBox, QListWidget


class HandCursor(QObject):
    """Рука при наведении на кнопки, выпадающие списки и строки списка каналов."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show:
            if isinstance(obj, (QAbstractButton, QComboBox)):
                obj.setCursor(Qt.CursorShape.PointingHandCursor)
            elif isinstance(obj, QListWidget):
                obj.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        return False  # события не перехватываем