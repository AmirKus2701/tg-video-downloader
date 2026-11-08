from asyncio import run
from datetime import UTC, date, datetime, timedelta
from os import getenv, listdir
from os.path import exists, isdir, join
from sys import argv

from core.auth import make_client
from core.channels import count_media, list_channels
from core.common import Cancelled, Options, Reporter
from core.layout import META_NAME, PHOTO_DIR, POSTS_DIR, TEXTS_DIR, VIDEO_DIR
from core.meta import load_meta
from core.navigator import build_navigator, scan_media
from core.pipeline import download_channel
from core.settings import load_settings
from core.telegram import is_post
from core.tz import load_tz
from core.utils import channel_folder, parse_channel

TEST_DIR = "posts_test"  # отдельная папка, чтобы не затереть ваши готовые данные
BAR_WIDTH = 25
COMMANDS = ("channels", "count", "download", "navigator", "days")


def show_progress(done, total, text):
    ratio = min(done / total, 1) if total else 0
    filled = round(BAR_WIDTH * ratio)
    bar = "█" * filled + "░" * (BAR_WIDTH - filled)
    print(f"\r[{bar}] {ratio * 100:3.0f}% {text}".ljust(130), end="", flush=True)


def show_log(text):
    print(f"\r{text}".ljust(130))


def rebuild_navigators(out_dir):
    """Перестраивает 0_navigator.xlsx по уже скачанным данным. Вход в Telegram не нужен."""
    if not isdir(out_dir):
        raise SystemExit(f"Папка {out_dir} не найдена.")

    settings = load_settings()
    rep = Reporter(on_log=show_log)
    for name in sorted(listdir(out_dir)):
        root = join(out_dir, name)
        if isdir(root) and any(
            isdir(join(root, folder)) for folder in (PHOTO_DIR, VIDEO_DIR, POSTS_DIR)
        ):
            print(f"Канал: {name}")
            try:
                build_navigator(root, rep, settings["timezone"])
            except PermissionError:
                print(
                    "Не удалось записать 0_navigator.xlsx: закройте его в Excel и повторите."
                )


async def iter_entities(client):
    raw = getenv("TG_CHANNEL")
    if not raw:
        raise SystemExit("Заполните TG_CHANNEL в .env")
    await (
        client.get_dialogs()
    )  # кэш каналов: без него приватный канал по ID не найдётся
    for item in raw.split(","):
        if not item.strip():
            continue
        try:
            yield await client.get_entity(parse_channel(item))
        except ValueError:
            print(f"Канал {item.strip()} не найден: проверьте ID и подписку.")


async def day_report(client, entity, day, out_dir, tz_name):
    """Сравнивает посты одного дня в Telegram с тем, что лежит на диске."""
    tz = load_tz(tz_name) or UTC
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    end = start + timedelta(days=1)

    messages = []
    async for msg in client.iter_messages(entity, offset_date=end):
        if msg.date.astimezone(tz) < start:
            break
        messages.append(msg)
    messages.sort(key=lambda m: m.id)

    # склеиваем альбомы так же, как это делает программа
    groups, current, group_id = [], [], None
    for msg in messages:
        if msg.grouped_id and msg.grouped_id == group_id:
            current.append(msg)
            continue
        if current:
            groups.append(current)
        current, group_id = [msg], msg.grouped_id
    if current:
        groups.append(current)

    root = channel_folder(out_dir, entity)
    meta = load_meta(join(root, META_NAME))
    photos = scan_media(root, PHOTO_DIR)
    videos = scan_media(root, VIDEO_DIR)

    print(f"\nКанал: {getattr(entity, 'title', entity.id)}")
    print(
        f"День: {day} ({tz_name}). Сообщений: {len(messages)}, групп (постов и альбомов): {len(groups)}"
    )
    print(f"Папка для сверки: {root}\n")
    print(f"{'id':>8} {'время':5}  текст  фото/диск  видео/диск  meta  .md  примечание")

    counted = missing = 0
    for group in groups:
        post_id = next((m.id for m in group if m.text), group[0].id)
        time_text = group[0].date.astimezone(tz).strftime("%H:%M")
        has_text = any(m.text for m in group)
        photo_count = sum(1 for m in group if m.photo)
        video_count = sum(1 for m in group if m.video)
        photos_disk = len(photos.get(post_id, []))
        videos_disk = len(videos.get(post_id, []))
        in_meta = str(post_id) in meta
        has_md = exists(join(root, TEXTS_DIR, f"{post_id}.md"))

        note = ""
        if not is_post(group):
            names = {type(m.media).__name__ for m in group if m.media}
            names |= {
                type(m.action).__name__ for m in group if getattr(m, "action", None)
            }
            note = "не считается постом: " + (
                ", ".join(sorted(names)) or "заглушка или пустое сообщение"
            )
        else:
            counted += 1
            if not (in_meta or has_md or photos_disk or videos_disk):
                missing += 1
                note = "НЕТ НА ДИСКЕ"

        print(
            f"{post_id:>8} {time_text:5}  {'да' if has_text else 'нет':5} "
            f"{photo_count:>5}/{photos_disk:<5} {video_count:>6}/{videos_disk:<5} "
            f"{'да' if in_meta else 'нет':4}  {'да' if has_md else 'нет':3}  {note}"
        )

    print(f"\nПостов по правилам программы: {counted}. Из них нет на диске: {missing}.")
    print(
        "Если скачивали без фото или видео, посты только с медиа не попадут в meta: это не ошибка."
    )


async def main(command):
    settings = load_settings(use_env=True)
    if not settings["api_id"] or not settings["api_hash"]:
        raise SystemExit("Заполните TG_API_ID и TG_API_HASH в .env")

    # временно используем вашу прежнюю сессию session.session из папки проекта
    client = make_client(settings["api_id"], settings["api_hash"], "session")
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise SystemExit("Нет входа: сначала выполните python qr_login.py")

        if command == "channels":
            for channel in await list_channels(client):
                username = f"@{channel.username}" if channel.username else "-"
                print(f"{channel.id} | {channel.name} | {username} | {channel.kind}")

        elif command == "count":
            async for entity in iter_entities(client):
                photos, videos = await count_media(client, entity)
                print(f"Канал: {entity.title}\nФото: {photos}\nВидео: {videos}\n")

        elif command == "download":
            limit = next((int(arg) for arg in argv[2:] if arg.isdigit()), None)
            opts = Options(
                out_dir=TEST_DIR,
                limit=limit,
                dry_run="dry" in argv,
                timezone=settings["timezone"],
            )
            rep = Reporter(on_progress=show_progress, on_log=show_log)
            async for entity in iter_entities(client):
                try:
                    await download_channel(client, entity, opts, rep)
                except Cancelled:
                    print("\nОстановлено.")

        elif command == "days":
            day = date.fromisoformat(argv[2])
            out_dir = argv[3] if len(argv) > 3 else TEST_DIR
            async for entity in iter_entities(client):
                await day_report(client, entity, day, out_dir, settings["timezone"])
    finally:
        await client.disconnect()


def run_cli():
    command = argv[1] if len(argv) > 1 else ""
    usage = (
        "Команды: channels | count | download [число постов] [dry] | navigator [папка] | "
        "days ГГГГ-ММ-ДД [папка]"
    )
    if command not in COMMANDS:
        raise SystemExit(usage)

    if command == "days":
        try:
            date.fromisoformat(argv[2])
        except (IndexError, ValueError):
            raise SystemExit(
                "Укажите дату так: python dev_cli.py days 2026-03-14 [папка]"
            )

    try:
        if command == "navigator":
            rebuild_navigators(argv[2] if len(argv) > 2 else TEST_DIR)
        else:
            run(main(command))
    except KeyboardInterrupt:
        print("\nОстановлено пользователем (Ctrl+C).")
        raise SystemExit(130)


if __name__ == "__main__":
    run_cli()
