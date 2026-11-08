from asyncio import CancelledError, create_task, sleep
from asyncio import TimeoutError as AsyncTimeoutError
from contextlib import suppress

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from core.common import Cancelled
from core.settings import session_path

QR_LIFETIME = 30  # секунд жизни одного QR-кода


def make_client(api_id, api_hash, session=None):
    """Клиент нужно создавать внутри работающего цикла asyncio (внутри async-функции)."""
    return TelegramClient(session or session_path(), int(api_id), api_hash)


async def login_qr(client, rep, on_qr, ask_password):
    """Вход по QR.
    on_qr(url, lifetime): показать (обновить) QR в окне.
    ask_password(): async-функция, возвращает облачный пароль или None, если пользователь отказался.
    Возвращает True при успехе. Отмена: rep.cancel() -> Cancelled."""
    if await client.is_user_authorized():
        return True

    qr_login = await client.qr_login()
    while True:
        on_qr(qr_login.url, QR_LIFETIME)
        task = create_task(qr_login.wait(QR_LIFETIME))
        try:
            while not task.done():
                rep.check()
                await sleep(0.2)
            task.result()
            return True
        except AsyncTimeoutError:
            await qr_login.recreate()  # код устарел, на следующем круге покажем новый
        except SessionPasswordNeededError:
            password = await ask_password()
            if not password:
                raise Cancelled
            await client.sign_in(password=password)
            return True
        finally:
            if not task.done():
                task.cancel()
                with suppress(CancelledError, Exception):
                    await task


async def logout(client):
    """Закрывает сессию в Telegram и удаляет файл сессии."""
    if await client.is_user_authorized():
        await client.log_out()
        return True
    return False


async def current_user_name(client):
    me = await client.get_me()
    return me.first_name or me.username or str(me.id)