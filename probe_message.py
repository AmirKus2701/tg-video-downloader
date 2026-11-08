from asyncio import run
from collections import Counter
from datetime import UTC
from os import getenv
from sys import argv

from core.auth import make_client
from core.settings import load_settings
from core.telegram import is_post
from core.tz import load_tz
from core.utils import is_skipped, parse_channel

USAGE = (
    "Использование:\n"
    "  python probe_message.py 3242              один пост\n"
    "  python probe_message.py 3211-3247         диапазон\n"
    "  python probe_message.py 3211-3247 -100…   диапазон в другом канале (ID из channels.csv)"
)


def parse_ids(text):
    first, _, last = text.partition("-")
    start = int(first)
    end = int(last) if last else start
    if end < start or end - start > 500:
        raise ValueError("диапазон должен быть не длиннее 500 номеров")
    return list(range(start, end + 1))


def entities_text(msg):
    counts = Counter(
        type(e).__name__.replace("MessageEntity", "") for e in (msg.entities or [])
    )
    return ", ".join(f"{name}:{count}" for name, count in counts.items()) or "-"


def media_text(msg):
    media = getattr(msg, "media", None)
    if media is None:
        return "-"
    name = type(media).__name__.replace("MessageMedia", "")
    webpage = getattr(media, "webpage", None)
    if webpage is not None:
        name += f"({type(webpage).__name__})"
    return name


def describe(msg_id, msg, tz):
    if msg is None:
        return f"{msg_id:>6}  нет такого сообщения (удалено или недоступно)"

    action = getattr(msg, "action", None)
    kind = (
        "служебное:" + type(action).__name__.replace("MessageAction", "")
        if action is not None
        else "сообщение"
    )

    flags = []
    if getattr(msg, "photo", None):
        flags.append("фото")
    if getattr(msg, "video", None):
        flags.append("видео")
    if getattr(msg, "grouped_id", None):
        flags.append("альбом")
    if getattr(msg, "restriction_reason", None):
        flags.append("ОГРАНИЧЕНИЕ")
    if getattr(msg, "fwd_from", None):
        flags.append("пересланное")
    if is_skipped(msg):
        flags.append("заглушка авторских прав")

    text = msg.raw_text or ""
    snippet = text.replace("\n", " ")[:28]
    when = msg.date.astimezone(tz).strftime("%d.%m %H:%M") if msg.date else "-"
    views = msg.views if msg.views is not None else "-"
    verdict = "да" if is_post([msg]) else "НЕТ"

    return (
        f"{msg_id:>6}  {when}  просм.{views!s:>5}  {kind}  медиа:{media_text(msg)}  "
        f"текст:{len(text)}  сущности:{entities_text(msg)}  "
        f"{'/'.join(flags) or '-'}  пост:{verdict}  «{snippet}»"
    )


async def main(ids, raw_channel):
    settings = load_settings(use_env=True)
    if not settings["api_id"] or not settings["api_hash"]:
        raise SystemExit("Заполните TG_API_ID и TG_API_HASH в .env")

    client = make_client(settings["api_id"], settings["api_hash"], "session")
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise SystemExit("Нет входа: сначала выполните python qr_login.py")

        await (
            client.get_dialogs()
        )  # кэш каналов: без него приватный канал по ID не найдётся
        entity = await client.get_entity(parse_channel(raw_channel))
        tz = load_tz(settings["timezone"]) or UTC
        print(
            f"Канал: {getattr(entity, 'title', entity.id)}  (время: {settings['timezone']})\n"
        )

        found = 0
        for start in range(0, len(ids), 100):
            chunk = ids[start : start + 100]
            messages = await client.get_messages(entity, ids=chunk)
            for msg_id, msg in zip(chunk, messages):
                found += msg is not None
                print(describe(msg_id, msg, tz))
        print(f"\nСообщений найдено: {found} из {len(ids)}")
    finally:
        await client.disconnect()


def run_probe():
    if len(argv) < 2:
        raise SystemExit(USAGE)
    try:
        ids = parse_ids(argv[1])
    except ValueError as error:
        raise SystemExit(f"{error}\n\n{USAGE}")

    raw_channel = (
        argv[2] if len(argv) > 2 else (getenv("TG_CHANNEL") or "").split(",")[0]
    )
    if not raw_channel.strip():
        raise SystemExit(
            "Заполните TG_CHANNEL в .env или укажите ID канала вторым аргументом."
        )

    try:
        run(main(ids, raw_channel))
    except KeyboardInterrupt:
        print("\nОстановлено пользователем (Ctrl+C).")
        raise SystemExit(130)


if __name__ == "__main__":
    run_probe()
