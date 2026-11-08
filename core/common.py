from dataclasses import dataclass
from threading import Event

from core.tz import DEFAULT_TZ


class Cancelled(Exception):
    """Операцию остановил пользователь."""


@dataclass
class Options:
    out_dir: str = "posts"
    texts: bool = True
    photos: bool = True
    videos: bool = True
    limit: int | None = None      # None: все посты; число: только последние N постов
    only_with_text: bool = False  # True: медиа только у постов с текстом
    dry_run: bool = False         # True: только посчитать, ничего не писать на диск
    timezone: str = DEFAULT_TZ    # в каком часовом поясе показывать даты в навигаторе


class Reporter:
    """Связь ядра с интерфейсом: прогресс, журнал и остановка. Само ядро ничего не печатает."""

    def __init__(self, on_progress=None, on_log=None, cancel_event=None):
        self._on_progress = on_progress
        self._on_log = on_log
        self._cancel = cancel_event or Event()

    def progress(self, done, total, text=""):
        if self._on_progress:
            self._on_progress(done, total, text)

    def log(self, text):
        if self._on_log:
            self._on_log(text)

    def cancel(self):
        self._cancel.set()

    @property
    def cancelled(self):
        return self._cancel.is_set()

    def check(self):
        if self._cancel.is_set():
            raise Cancelled