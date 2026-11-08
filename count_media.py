from os import getenv

from dotenv import find_dotenv, load_dotenv
from telethon import TelegramClient
from telethon.tl.types import InputMessagesFilterPhotos, InputMessagesFilterVideo

load_dotenv(find_dotenv())

API_ID = getenv("TG_API_ID")
API_HASH = getenv("TG_API_HASH")
RAW_CHANNELS = getenv("TG_CHANNEL")

if not API_ID or not API_HASH or not RAW_CHANNELS:
    raise SystemExit("Заполните TG_API_ID, TG_API_HASH и TG_CHANNEL в .env")

client = TelegramClient("session", int(API_ID), API_HASH)


def parse_channel(value):
    value = value.strip()
    return int(value) if value.lstrip("-").isdigit() else value


async def count_media(channel):
    entity = await client.get_entity(channel)
    title = getattr(entity, "title", str(channel))
    username = getattr(entity, "username", None)

    # limit=0 не скачивает сообщения, а возвращает только общее число (.total)
    photos = await client.get_messages(
        entity, limit=0, filter=InputMessagesFilterPhotos
    )
    videos = await client.get_messages(entity, limit=0, filter=InputMessagesFilterVideo)
    return title, username, photos.total, videos.total


async def main():
    channels = [parse_channel(raw) for raw in RAW_CHANNELS.split(",") if raw.strip()]
    total_photos = 0
    total_videos = 0

    for channel in channels:
        title, username, photos, videos = await count_media(channel)
        total_photos += photos
        total_videos += videos

        print(f"Канал: {title}")
        print(f"Юзернейм: {'@' + username if username else 'нет (приватный канал)'}")
        print(f"Фото: {photos}")
        print(f"Видео: {videos}")
        print()

    # общий итог показываем, только если каналов больше одного
    if len(channels) > 1:
        print("Итого по всем каналам")
        print(f"Фото: {total_photos}")
        print(f"Видео: {total_videos}")


def run():
    try:
        with client:  # вход (номер, код) происходит здесь, поэтому try снаружи
            client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\nОстановлено пользователем (Ctrl+C).")
        raise SystemExit(130)  # 130 - стандартный код выхода при Ctrl+C


if __name__ == "__main__":
    run()
