from csv import writer as csv_writer

from telethon import TelegramClient

from logout import logout
from qr_login import API_HASH, API_ID, SESSION_FILE, SESSION_NAME, login

LOGOUT_AFTER = False  # True: после сохранения списка выйти из аккаунта (сессия удалится)


async def save_channels(client):
    rows = []
    async for dialog in client.iter_dialogs():
        if dialog.is_channel:
            entity = dialog.entity
            rows.append([
                dialog.id,
                dialog.name,
                getattr(entity, "username", None) or "",
                "группа" if getattr(entity, "megagroup", False) else "канал",
            ])

    with open("channels.csv", "w", newline="", encoding="utf-8-sig") as f:
        out = csv_writer(f, delimiter=";")
        out.writerow(["id", "название", "username", "тип"])
        out.writerows(rows)

    print(f"Сохранено строк: {len(rows)} -> channels.csv")


async def main(client):
    await client.connect()
    try:
        if not await client.is_user_authorized():
            print("Вход не выполнен, запускаю вход по QR (qr_login.py)...")
            if not await login(client):
                return False

        await save_channels(client)

        if LOGOUT_AFTER:
            await logout(client)  # logout.py
        return True
    finally:
        await client.disconnect()


def run():
    # сессии нет -> файл появится только на этапе входа (qr_login.py), не здесь
    had_session = SESSION_FILE.exists()
    client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)

    try:
        ok = client.loop.run_until_complete(main(client))
    except KeyboardInterrupt:
        print("\nОстановлено пользователем (Ctrl+C).")
        ok = False
        raise SystemExit(130)
    finally:
        # вход отменён или прерван: не оставляем пустой файл сессии
        if not had_session and not ok:
            SESSION_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    run()