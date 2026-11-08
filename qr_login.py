"""
Быстрый вход в аккаунт телеграмма по QR-коду, чтобы скачивать посты с вашего аккаунта
"""

from asyncio import CancelledError, create_task, sleep
from contextlib import suppress
from getpass import getpass
from os import getenv
from pathlib import Path
from time import monotonic
from time import sleep as sync_sleep
from tkinter import Label, TclError, Tk

from dotenv import find_dotenv, load_dotenv
from PIL import Image, ImageTk
from qrcode import make as make_qr
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

load_dotenv(find_dotenv())

API_ID = getenv("TG_API_ID")
API_HASH = getenv("TG_API_HASH")

SESSION_NAME = "session"
SESSION_FILE = Path(f"{SESSION_NAME}.session")
QR_FILE = Path("qr.png")
QR_LIFETIME = 30  # секунд жизни одного QR-кода
BAR_WIDTH = 30  # ширина прогресс-бара в символах

if not API_ID or not API_HASH:
    raise SystemExit("Заполните TG_API_ID и TG_API_HASH в .env")


class WindowClosed(Exception):
    """Пользователь закрыл окно с QR-кодом."""


class QrWindow:
    """Окно с QR-кодом из файла qr.png."""

    def __init__(self):
        self.closed = False
        self.root = Tk()
        self.root.title("Telegram: вход по QR")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.label = Label(self.root)
        self.label.pack(padx=10, pady=10)
        self.photo = None

    def _on_close(self):
        self.closed = True
        self.close()

    def _update(self):
        if self.closed:
            raise WindowClosed
        try:
            self.root.update()
        except TclError:
            self.closed = True
            raise WindowClosed

    def show(self, url):
        make_qr(url).save(QR_FILE)
        with Image.open(QR_FILE) as img:
            self.photo = ImageTk.PhotoImage(img.copy())
        self.label.configure(image=self.photo)
        self._update()

    def pump(self):
        self._update()

    def close(self):
        with suppress(TclError):
            self.root.destroy()


def remove_qr_file():
    for _ in range(10):
        try:
            QR_FILE.unlink(missing_ok=True)
            return
        except PermissionError:
            sync_sleep(0.2)
    print(f"Не удалось удалить {QR_FILE}, удалите его вручную.")


def draw_bar(left, attempt):
    filled = round(BAR_WIDTH * left / QR_LIFETIME)
    bar = "█" * filled + "░" * (BAR_WIDTH - filled)
    print(f"\rQR №{attempt} [{bar}] {left:4.1f} с ", end="", flush=True)


async def wait_with_progress(qr_login, window, attempt):
    task = create_task(qr_login.wait(QR_LIFETIME))
    started = monotonic()
    try:
        while not task.done():
            draw_bar(max(0.0, QR_LIFETIME - (monotonic() - started)), attempt)
            window.pump()
            await sleep(0.2)
        return task.result()
    finally:
        if not task.done():
            task.cancel()
            with suppress(CancelledError, Exception):
                await task


async def login(client):
    """Входит по QR. Клиент должен быть уже подключён. Возвращает True при успехе."""
    remove_qr_file()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Вы уже вошли как: {me.first_name} (id {me.id})")
        return True

    window = None
    try:
        print(
            "На телефоне: Telegram -> Настройки -> Устройства -> Подключить устройство"
        )
        print("Наведите камеру на QR-код в открывшемся окне.\n")

        window = QrWindow()
        qr_login = await client.qr_login()
        attempt = 1

        while True:
            window.show(qr_login.url)
            try:
                await wait_with_progress(qr_login, window, attempt)
                break
            except TimeoutError:
                attempt += 1
                await qr_login.recreate()
            except SessionPasswordNeededError:
                window.close()
                window = None
                print("\nВключена двухфакторная защита.")
                await client.sign_in(password=getpass("Облачный пароль Telegram: "))
                break

        me = await client.get_me()
        print(f"\nВход выполнен: {me.first_name} (id {me.id})")
        return True
    except WindowClosed:
        print("\nОкно с QR-кодом закрыто, вход отменён.")
        return False
    finally:
        if window:
            window.close()
        remove_qr_file()


def run():
    client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)

    async def runner():
        await client.connect()
        try:
            return await login(client)
        finally:
            await client.disconnect()

    try:
        ok = client.loop.run_until_complete(runner())
    except KeyboardInterrupt:
        print("\nОстановлено пользователем (Ctrl+C).")
        raise SystemExit(130)

    if not ok:
        SESSION_FILE.unlink(missing_ok=True)  # убираем пустую сессию после отмены


if __name__ == "__main__":
    run()
