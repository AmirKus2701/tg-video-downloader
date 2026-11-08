from datetime import datetime
from os.path import exists, join, normpath

from PySide6.QtCore import Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit,
    QProgressBar, QPushButton, QSizePolicy, QVBoxLayout,
)

from core.common import Options
from core.layout import NAV_NAME
from core.utils import safe_name
from ui.checkbox import CheckBox

LIMITS = (
    ("Все посты", None),
    ("Последние 5", 5),
    ("Последние 20", 20),
    ("Последние 100", 100),
    ("Последние 500", 500),
)
LABEL_WIDTH = 130


class ElidedLabel(QLabel):
    """Длинный текст обрезается многоточием и не растягивает окно."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_full_text(self, text):
        self._full = text
        self.setToolTip(text)
        self._elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        text = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideMiddle, max(0, self.width()))
        self.setText(text)


class DownloadPanel(QFrame):
    start_requested = Signal(object)   # Options
    stop_requested = Signal()
    folder_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._info = None
        self._out_dir = ""
        self._timezone = ""
        self._running = False
        self._stopping = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("Скачивание")
        title.setProperty("role", "h2")
        layout.addWidget(title)

        # что скачивать
        checks = QHBoxLayout()
        checks.setSpacing(30)
        self.texts = CheckBox("Тексты постов")
        self.photos = CheckBox("Фото")
        self.videos = CheckBox("Видео")
        for box in (self.texts, self.photos, self.videos):
            box.setChecked(True)
            box.toggled.connect(self._update_buttons)
            checks.addWidget(box)
        checks.addStretch(1)
        layout.addLayout(checks)

        # сколько постов
        limit_row = QHBoxLayout()
        limit_row.setSpacing(14)
        limit_label = QLabel("Сколько постов")
        limit_label.setFixedWidth(LABEL_WIDTH)
        self.limit = QComboBox()
        for text, value in LIMITS:
            self.limit.addItem(text, value)
        self.limit.setMinimumWidth(220)
        limit_row.addWidget(limit_label)
        limit_row.addWidget(self.limit)
        limit_row.addStretch(1)
        layout.addLayout(limit_row)

        # папка
        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        folder_label = QLabel("Папка")
        folder_label.setFixedWidth(LABEL_WIDTH)
        self.folder = ElidedLabel()
        self.choose = QPushButton("Выбрать…")
        self.choose.clicked.connect(self._choose_folder)
        open_folder = QPushButton("Открыть")
        open_folder.clicked.connect(self._open_folder)
        folder_row.addWidget(folder_label)
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(self.choose)
        folder_row.addWidget(open_folder)
        layout.addLayout(folder_row)

        self.folder_hint = ElidedLabel()
        self.folder_hint.setProperty("role", "muted")
        layout.addWidget(self.folder_hint)

        divider = QFrame()
        divider.setObjectName("divider")
        layout.addWidget(divider)

        # кнопки
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.start = QPushButton("Начать")
        self.start.setProperty("role", "primary")
        self.start.clicked.connect(lambda: self._begin(False))
        self.estimate = QPushButton("Оценить объём")
        self.estimate.clicked.connect(lambda: self._begin(True))
        self.stop = QPushButton("Остановить")
        self.stop.setProperty("role", "danger")
        self.stop.clicked.connect(self._stop)
        buttons.addWidget(self.start)
        buttons.addWidget(self.estimate)
        buttons.addWidget(self.stop)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        # состояние и прогресс
        self.status = ElidedLabel()
        layout.addWidget(self.status)

        bar_row = QHBoxLayout()
        bar_row.setSpacing(12)
        self.bar = QProgressBar()
        self.bar.setProperty("role", "download")
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.percent = QLabel("0%")
        self.percent.setFixedWidth(48)
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bar_row.addWidget(self.bar, 1)
        bar_row.addWidget(self.percent)
        layout.addLayout(bar_row)

        self.progress_text = ElidedLabel()
        self.progress_text.setProperty("role", "muted")
        layout.addWidget(self.progress_text)

        # журнал и навигатор
        footer = QHBoxLayout()
        self.log_toggle = QPushButton("Показать журнал")
        self.log_toggle.setProperty("role", "flat")
        self.log_toggle.clicked.connect(self._toggle_log)
        self.navigator = QPushButton("Открыть навигатор")
        self.navigator.clicked.connect(self._open_navigator)
        footer.addWidget(self.log_toggle)
        footer.addStretch(1)
        footer.addWidget(self.navigator)
        layout.addLayout(footer)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setFixedHeight(170)
        self.log.hide()
        layout.addWidget(self.log)

        self.status.set_full_text("Выберите канал и нажмите «Начать».")
        self._update_buttons()

    # ---------- канал и папка ----------

    def set_channel(self, info, out_dir, timezone):
        self._info = info
        self._out_dir = out_dir
        self._timezone = timezone
        self._show_folder()
        self.log.clear()
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.percent.setText("0%")
        self.progress_text.set_full_text("")
        self.status.set_full_text("Готово к скачиванию.")
        self._update_buttons()

    def refresh(self):
        for box in (self.texts, self.photos, self.videos):
            box.update()

    def _channel_dir(self):
        return join(self._out_dir, safe_name(self._info.name)) if self._info else ""

    def _show_folder(self):
        self.folder.set_full_text(self._out_dir)
        if self._info:
            self.folder_hint.set_full_text(f"Канал сохранится в подпапку «{safe_name(self._info.name)}».")

    def _choose_folder(self):
        start = self._out_dir if exists(self._out_dir) else ""
        folder = QFileDialog.getExistingDirectory(self, "Папка для скачивания", start)
        if folder:
            self._out_dir = normpath(folder)
            self._show_folder()
            self.folder_changed.emit(self._out_dir)
            self._update_buttons()

    def _open_folder(self):
        target = self._channel_dir()
        if not exists(target):
            target = self._out_dir
        if not exists(target):
            self.status.set_full_text("Папка появится после первого скачивания.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def _open_navigator(self):
        path = join(self._channel_dir(), NAV_NAME)
        if exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _toggle_log(self):
        show = not self.log.isVisible()
        self.log.setVisible(show)
        self.log_toggle.setText("Скрыть журнал" if show else "Показать журнал")

    # ---------- запуск и остановка ----------

    def _begin(self, dry_run):
        if not self._info or self._running:
            return
        self._running = True
        self._stopping = False
        self.log.clear()
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.percent.setText("0%")
        self.progress_text.set_full_text("")
        self.status.set_full_text("Подготовка…")
        self._update_buttons()

        self.start_requested.emit(Options(
            out_dir=self._out_dir,
            texts=self.texts.isChecked(),
            photos=self.photos.isChecked(),
            videos=self.videos.isChecked(),
            limit=self.limit.currentData(),
            dry_run=dry_run,
            timezone=self._timezone,
        ))

    def _stop(self):
        if self._running and not self._stopping:
            self._stopping = True
            self.status.set_full_text("Останавливаю…")
            self._update_buttons()
            self.stop_requested.emit()

    def _update_buttons(self, *args):
        chosen = self.texts.isChecked() or self.photos.isChecked() or self.videos.isChecked()
        ready = self._info is not None and not self._running
        self.start.setEnabled(ready and chosen)
        self.estimate.setEnabled(ready and chosen)
        self.stop.setEnabled(self._running and not self._stopping)
        for widget in (self.texts, self.photos, self.videos, self.limit, self.choose):
            widget.setEnabled(not self._running)
        has_navigator = bool(self._info) and exists(join(self._channel_dir(), NAV_NAME))
        self.navigator.setEnabled(has_navigator)

    # ---------- ход работы (приходит из потока Telegram) ----------

    @Slot(int, int, str)
    def set_progress(self, done, total, text):
        if total > 0:
            self.bar.setRange(0, total)
            self.bar.setValue(min(done, total))
            self.percent.setText(f"{min(done, total) * 100 // total}%")
        else:
            self.bar.setRange(0, 1)
            self.bar.setValue(0)
            self.percent.setText("0%")
        self.progress_text.set_full_text(text)

    @Slot(str)
    def add_log(self, text):
        self.log.appendPlainText(f"{datetime.now():%H:%M:%S}  {text}")
        self.status.set_full_text(text)

    @Slot(str, bool, object)
    def finish(self, status, dry_run, result):
        self._running = False
        self._stopping = False
        if status == "done":
            self.bar.setValue(self.bar.maximum())
            self.percent.setText("100%")
            text = self._summary(dry_run, result)
        elif status == "cancelled":
            text = "Остановлено. Уже скачанное сохранено: при следующем запуске оно будет пропущено."
        else:
            text = f"Ошибка: {result}"
        self.status.set_full_text(text)
        self.progress_text.set_full_text("")
        self._update_buttons()

    @staticmethod
    def _summary(dry_run, result):
        media = result.get("media") if result else None
        texts = result.get("texts") if result else None
        parts = []
        if media is not None:
            gigabytes = media["bytes"] / 1024 ** 3
            if dry_run:
                parts.append(f"к скачиванию {media['files']} файлов (~{gigabytes:.2f} ГБ), "
                             f"уже есть {media['skipped']}")
            else:
                parts.append(f"скачано файлов {media['files']} ({gigabytes:.2f} ГБ), "
                             f"уже было {media['skipped']}, ошибок {media['failed']}")
        if texts is not None:
            parts.append(f"постов с текстом {texts}" if dry_run else f"текстов сохранено {texts}")
        prefix = "Оценка" if dry_run else "Готово"
        return f"{prefix}: " + " · ".join(parts) if parts else f"{prefix}."