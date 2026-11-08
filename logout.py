"""
Быстрый выход из аккаунта, который вы вошли с помощью скрипта - qr_login.py
"""
from telethon import TelegramClient

from qr_login import API_HASH, API_ID, SESSION_FILE, SESSION_NAME


async def logout(client):
    """Закрывает сессию в Telegram и удаляет session.session. Клиент должен быть подключён."""
    if not await client.is_user_authorized():
        print("Вы и так не авторизованы.")
        return False

    await client.log_out()  # закрывает сессию на стороне Telegram и удаляет файл сессии
    print("Выход выполнен, сессия закрыта.")
    return True


def run():
    # без файла сессии выходить не из чего, и создавать его не нужно
    if not SESSION_FILE.exists():
        print("Файл сессии не найден, выходить не из чего.")
        return

    client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)

    async def runner():
        await client.connect()
        try:
            await logout(client)
        finally:
            await client.disconnect()

    try:
        client.loop.run_until_complete(runner())
    except KeyboardInterrupt:
        print("\nОстановлено пользователем (Ctrl+C).")
        raise SystemExit(130)


if __name__ == "__main__":
    run()