from asyncio import new_event_loop, run_coroutine_threadsafe, set_event_loop
from contextlib import suppress
from threading import Thread
from time import monotonic
from traceback import print_exc

from PySide6.QtCore import QObject, Signal

from core.auth import login_qr, logout, make_client
from core.avatars import save_avatar
from core.channels import count_media, download_channel_avatars, list_channels
from core.common import Cancelled, Reporter
from core.pipeline import download_channel

# ошибки Telegram, которые означают «ключи api_id и api_hash не подходят»
KEY_ERRORS = ("ApiIdInvalidError", "ApiIdPublishedFloodError")

PROGRESS_INTERVAL = 0.1  # не чаще 10 обновлений в секунду, иначе окно будет тормозить


def describe(error):
    """Понятный текст ошибки для окна."""
    name = type(error).__name__
    if name == "ApiIdInvalidError":
        return "Telegram не принял api_id или api_hash. Проверьте ключи на my.telegram.org."
    if name == "ApiIdPublishedFloodError":
        return "Telegram заблокировал этот api_id. Создайте новое приложение на my.telegram.org."
    if name == "PasswordHashInvalidError":
        return "Неверный облачный пароль."
    if name == "FloodWaitError":
        return f"Telegram просит подождать {getattr(error, 'seconds', '?')} с. Повторите позже."
    if isinstance(error, (ConnectionError, TimeoutError, OSError)):
        return f"Нет соединения или ошибка диска: {error}"
    return f"{name}: {error}"


class TelegramWorker(QObject):
    """Telethon живёт в своём потоке; окно общается с ним только через методы и сигналы."""

    authorized = Signal(
        str, object
    )  # имя в Telegram, ID аккаунта (object: ID не помещается в int32)
    unauthorized = Signal()
    keys_rejected = Signal(str)  # Telegram не принял api_id/api_hash
    qr_ready = Signal(str, int)  # ссылка для QR, время жизни в секундах
    password_needed = Signal()
    login_failed = Signal(str)
    avatar_loaded = Signal(
        str, str
    )  # id профиля, путь к фото ("" если у аккаунта нет фото)
    channel_avatar_loaded = Signal(object, str)  # channel_id, path
    channels_loaded = Signal(object)  # список ChannelInfo
    counts_loaded = Signal(object, int, int)  # id канала, фото, видео
    counts_failed = Signal(object)
    download_progress = Signal(int, int, str)  # сделано, всего, текст
    download_log = Signal(str)
    download_finished = Signal(
        str, bool, object
    )  # статус (done/cancelled/error), пробный режим, результат
    logged_out = Signal()
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._loop = new_event_loop()
        self._thread = Thread(target=self._run_loop, name="telegram-loop", daemon=True)
        self._thread.start()
        self._client = None
        self._rep = Reporter()
        self._dl_rep = None
        self._last_progress = 0.0
        self._password_future = None

    # ---------- служебное ----------

    def _run_loop(self):
        set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(self, coro):
        future = run_coroutine_threadsafe(coro, self._loop)
        future.add_done_callback(self._on_done)
        return future

    def _on_done(self, future):
        if future.cancelled():
            return
        error = future.exception()
        if error and not isinstance(error, Cancelled):
            self.failed.emit(describe(error))

    async def _close_client(self):
        client, self._client = self._client, None
        if client:
            with suppress(Exception):
                await client.disconnect()

    def _report_error(self, error):
        """Отказ по ключам ведёт на экран регистрации, остальные ошибки на экран входа."""
        if type(error).__name__ in KEY_ERRORS:
            self.keys_rejected.emit(describe(error))
        else:
            self.login_failed.emit(describe(error))

    async def _whoami(self):
        me = await self._client.get_me()
        return (me.first_name or me.username or str(me.id)), me.id

    # ---------- подключение и вход ----------

    def start(self, api_id, api_hash, session):
        self._rep.cancel()  # останавливаем возможный незаконченный вход
        self._submit(self._start(api_id, api_hash, session))

    async def _start(self, api_id, api_hash, session):
        await self._close_client()
        try:
            # клиент создаётся внутри цикла, в котором будет работать
            self._client = make_client(api_id, api_hash, session)
            await self._client.connect()
            if await self._client.is_user_authorized():
                name, user_id = await self._whoami()
                self.authorized.emit(name, user_id)
            else:
                self.unauthorized.emit()
        except Exception as error:
            self._report_error(error)

    def begin_qr_login(self):
        self._rep = Reporter()
        self._submit(self._login(self._rep))

    async def _login(self, rep):
        try:
            ok = await login_qr(self._client, rep, self._emit_qr, self._ask_password)
            if ok:
                name, user_id = await self._whoami()
                self.authorized.emit(name, user_id)
        except Cancelled:
            pass
        except Exception as error:
            if not rep.cancelled:  # ошибки отменённого входа окну не нужны
                self._report_error(error)

    def _emit_qr(self, url, lifetime):
        self.qr_ready.emit(url, lifetime)

    async def _ask_password(self):
        self._password_future = self._loop.create_future()
        self.password_needed.emit()
        return await self._password_future

    def submit_password(self, text):
        self._loop.call_soon_threadsafe(self._set_password, text)

    def _set_password(self, text):
        if self._password_future and not self._password_future.done():
            self._password_future.set_result(text)

    def cancel_login(self):
        self._rep.cancel()

    def reject_account(self):
        """Чужой аккаунт вошёл в профиль: завершаем его вход в приложении и удаляем файл входа."""
        self._submit(self._reject())

    async def _reject(self):
        with suppress(Exception):
            if self._client:
                await logout(self._client)
        await self._close_client()

    def load_avatar(self, *args, **kwargs):
        pass

    # ---------- фото аккаунта ----------

    async def _load_avatar(self, profile_id):
        try:
            # file=bytes: фото приходит в памяти, поэтому нет путаницы с именами файлов и расширениями
            data = await self._client.download_profile_photo(
                "me", file=bytes, download_big=False
            )
            path = save_avatar(
                profile_id, data
            )  # None, если у аккаунта нет фото: старое фото убирается
        except Exception:
            print_exc()  # причина видна в терминале
            return
        print(
            f"Фото аккаунта: {'сохранено в ' + path if path else 'у аккаунта нет фото'}"
        )
        self.avatar_loaded.emit(profile_id, path or "")

    # ---------- каналы ----------

    def load_channels(self):
        self._submit(self._load_channels())

    async def _load_channels(self):
        channels = await list_channels(self._client)
        self.channels_loaded.emit(channels)

        # запускаем фоновую загрузку аватарок
        def on_ready(channel_id, path):
            self.channel_avatar_loaded.emit(channel_id, path)

        await download_channel_avatars(self._client, channels, on_ready)

    def load_counts(self, channel_id):
        self._submit(self._load_counts(channel_id))

    async def _load_counts(self, channel_id):
        try:
            entity = await self._client.get_entity(channel_id)
            photos, videos = await count_media(self._client, entity)
            self.counts_loaded.emit(channel_id, photos, videos)
        except Exception:
            self.counts_failed.emit(channel_id)

    # ---------- скачивание ----------

    def start_download(self, channel_id, opts):
        self._last_progress = 0.0
        rep = Reporter(on_progress=self._emit_progress, on_log=self.download_log.emit)
        self._dl_rep = rep
        self._submit(self._download(channel_id, opts, rep))

    def stop_download(self):
        if self._dl_rep:
            self._dl_rep.cancel()

    def _emit_progress(self, done, total, text):
        now = monotonic()
        if done >= total or now - self._last_progress >= PROGRESS_INTERVAL:
            self._last_progress = now
            self.download_progress.emit(done, total, text)

    async def _download(self, channel_id, opts, rep):
        try:
            entity = await self._client.get_entity(channel_id)
            result = await download_channel(self._client, entity, opts, rep)
            self.download_finished.emit("done", opts.dry_run, result)
        except Cancelled:
            self.download_finished.emit("cancelled", opts.dry_run, None)
        except Exception as error:
            self.download_finished.emit("error", opts.dry_run, describe(error))

    # ---------- выход и закрытие ----------

    def logout(self):
        self._submit(self._logout())

    async def _logout(self):
        try:
            if self._client:
                await logout(self._client)
        finally:
            await self._close_client()
        self.logged_out.emit()

    def release(self):
        """Закрывает соединение и освобождает файл входа (нужно перед удалением профиля)."""
        with suppress(Exception):
            run_coroutine_threadsafe(self._close_client(), self._loop).result(timeout=5)

    def shutdown(self):
        self.stop_download()
        self.release()
        self._loop.call_soon_threadsafe(self._loop.stop)
