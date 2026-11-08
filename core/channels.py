from asyncio import Semaphore, gather
from dataclasses import dataclass

from telethon.tl.types import InputMessagesFilterPhotos, InputMessagesFilterVideo

from core.avatars import channel_avatar_file, save_channel_avatar


@dataclass
class ChannelInfo:
    id: int
    name: str
    username: str
    kind: str
    avatar_path: str | None = None


async def list_channels(client):
    items = []
    async for dialog in client.iter_dialogs():
        if dialog.is_channel:
            entity = dialog.entity
            channel_id = dialog.id
            items.append(
                ChannelInfo(
                    id=channel_id,
                    name=dialog.name,
                    username=getattr(entity, "username", None) or "",
                    kind="группа" if getattr(entity, "megagroup", False) else "канал",
                    avatar_path=channel_avatar_file(
                        channel_id
                    ),  # сразу подставляем кэш
                )
            )
    return items


async def count_media(client, entity):
    """(фото, видео). Считает сам Telegram, ничего не скачивается."""
    photos = await client.get_messages(
        entity, limit=0, filter=InputMessagesFilterPhotos
    )
    videos = await client.get_messages(entity, limit=0, filter=InputMessagesFilterVideo)
    return photos.total, videos.total


async def download_channel_avatars(client, channels, on_ready, max_concurrent=4):
    """
    Качает недостающие аватарки каналов в фоне.
    on_ready(channel_id, path) вызывается, когда аватарка готова.
    """
    missing = [ch for ch in channels if not ch.avatar_path]
    if not missing:
        return

    sem = Semaphore(max_concurrent)

    async def one(channel):
        async with sem:
            try:
                # скачиваем в память (маленькие файлы)
                data = await client.download_profile_photo(
                    channel.id, file=bytes, download_big=False
                )
                path = save_channel_avatar(channel.id, data)
                if path:
                    channel.avatar_path = path
                    on_ready(channel.id, path)
            except Exception:
                # молча пропускаем — у канала может не быть фото или временная ошибка
                pass

    await gather(*(one(ch) for ch in missing))
