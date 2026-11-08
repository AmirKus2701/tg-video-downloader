from os import getenv, listdir, makedirs
from os.path import join
from re import sub

from dotenv import find_dotenv, load_dotenv
from telethon import TelegramClient
from telethon.tl.types import InputMessagesFilterVideo

load_dotenv(find_dotenv())


API_ID = getenv("TG_API_ID")
API_HASH = getenv("TG_API_HASH")
RAW_CHANNELS = getenv("TG_CHANNEL")
OUT_DIR = "videos"

if not API_ID or not API_HASH or not RAW_CHANNELS:
    raise SystemExit("Заполните TG_API_ID, TG_API_HASH и TG_CHANNEL в .env")

client = TelegramClient("session", int(API_ID), API_HASH)


def parse_channel(value):
    value = value.strip()
    return int(value) if value.lstrip("-").isdigit() else value


def safe_name(text, max_len=60):
    text = sub(r'[\\/:*?"<>|\n\r]+', " ", text or "").strip()
    return text[:max_len] or "video"


async def download_channel(channel):
    entity = await client.get_entity(channel)
    title = getattr(entity, "title", str(channel))
    folder = join(OUT_DIR, safe_name(title))
    makedirs(folder, exist_ok=True)

    # id уже скачанных видео (для докачки при повторном запуске)
    done = {name.split("_", 1)[0] for name in listdir(folder)}

    count = 0
    async for msg in client.iter_messages(
        entity, filter=InputMessagesFilterVideo, limit=4
    ):
        """
        В параметре - limit, мы указываем число сколько будем качать видео.
        Это число начинает скачиваться с последними опубликованными видео.
        """

        if str(msg.id) in done:
            continue
        name = f"{msg.id}_{safe_name(msg.text)}"
        await msg.download_media(file=join(folder, name))
        count += 1
        print(f"[{title}] [{count}] скачано: {name}")

    print(f"[{title}] готово. Новых видео: {count}")


async def main():
    for raw in RAW_CHANNELS.split(","):
        if raw.strip():
            await download_channel(parse_channel(raw))


def run():
    try:
        with client:  # вход (номер, код) происходит здесь, поэтому try снаружи
            client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\nОстановлено пользователем (Ctrl+C).")
        raise SystemExit(130)  # 130 - стандартный код выхода при Ctrl+C


if __name__ == "__main__":
    run()
