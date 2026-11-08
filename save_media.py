from asyncio import sleep
from json import JSONDecodeError, dump, load
from os import getenv, makedirs, remove, symlink
from os import replace as replace_file
from os.path import abspath, basename, dirname, exists, join, relpath
from subprocess import run as run_process
from sys import platform
from tempfile import TemporaryDirectory

from dotenv import load_dotenv, find_dotenv
from telethon import TelegramClient
from telethon.errors import FloodWaitError

from logout import logout
from qr_login import API_HASH, API_ID, SESSION_FILE, SESSION_NAME, login
from save_posts import OUT_DIR, is_skipped, make_title, parse_channel, safe_name

load_dotenv(find_dotenv())

RAW_CHANNELS = getenv("TG_CHANNEL")

PHOTO_DIR = "0_фото"
VIDEO_DIR = "0_видео"
POSTS_DIR = "0_посты"    # папка с отдельной папкой на каждый пост
META_NAME = "0_meta.json"  # дата, просмотры и заголовок каждого поста с медиа

LIMIT = 7             # None: все посты; число, например 7: только последние 7 постов (для теста)
DRY_RUN = False          # True: ничего не скачивать, только показать сколько файлов и места нужно
ONLY_WITH_TEXT = False   # False: все фото и видео канала; True: только у постов с текстом
LOGOUT_AFTER = False     # True: после скачивания выйти из аккаунта (сессия удалится)
MAX_RETRIES = 3          # сколько раз повторять скачивание при паузе от Telegram
BAR_WIDTH = 25

if not RAW_CHANNELS:
    raise SystemExit("Заполните TG_CHANNEL в .env")

# PowerShell-скрипт, который создаёт .lnk ярлыки списком (один запуск на весь канал)
PS_SCRIPT = """
$items = Get-Content -Raw -LiteralPath $args[0] | ConvertFrom-Json
$shell = New-Object -ComObject WScript.Shell
foreach ($item in $items) {
    $shortcut = $shell.CreateShortcut($item.link)
    $shortcut.TargetPath = $item.target
    $shortcut.WorkingDirectory = Split-Path -Parent $item.target
    $shortcut.Save()
}
"""


async def iter_posts(client, entity):
    """Отдаёт посты как списки сообщений: альбом (общий grouped_id) собирается в один пост.
    LIMIT считает посты, а не сообщения, поэтому альбом никогда не обрывается."""
    group, group_id, posts = [], None, 0
    async for msg in client.iter_messages(entity, reverse=LIMIT is None):
        if msg.grouped_id and msg.grouped_id == group_id:
            group.append(msg)
            continue
        if group:
            yield group
            posts += 1
            if LIMIT and posts >= LIMIT:
                return
        group = [msg]
        group_id = msg.grouped_id
    if group:
        yield group


def file_ext(msg, default):
    return (msg.file.ext if msg.file and msg.file.ext else None) or default


def build_targets(root, kind_dir, post_id, items, default_ext):
    """Возвращает список (сообщение, путь к файлу): один файл или подпапка с номерами."""
    base = join(root, kind_dir)
    if len(items) == 1:
        return [(items[0], join(base, f"{post_id}{file_ext(items[0], default_ext)}"))]

    folder = join(base, str(post_id))
    return [
        (msg, join(folder, f"{number}{file_ext(msg, default_ext)}"))
        for number, msg in enumerate(items, start=1)
    ]


def link_path(post_dir, target):
    """Путь ярлыка в папке поста: имя файла + .lnk (в Windows)."""
    suffix = ".lnk" if platform == "win32" else ""
    return join(post_dir, basename(target) + suffix)


def create_shortcuts(pairs):
    """Создаёт ярлыки: (путь ярлыка, путь файла). В Windows .lnk, иначе символические ссылки."""
    if not pairs:
        return

    if platform != "win32":
        for link, target in pairs:
            symlink(target, link)
        return

    with TemporaryDirectory() as tmp:
        json_path = join(tmp, "links.json")
        ps_path = join(tmp, "make_links.ps1")
        with open(json_path, "w", encoding="utf-8") as f:
            # ensure_ascii=True: кириллица и спецсимволы пишутся как \uXXXX, без проблем с кодировкой
            dump([{"link": link, "target": target} for link, target in pairs], f, ensure_ascii=True)
        with open(ps_path, "w", encoding="utf-8") as f:
            f.write(PS_SCRIPT)

        result = run_process(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_path, json_path],
            capture_output=True,
            text=True,
        )

    if result.returncode != 0:
        print(f"Ярлыки созданы с ошибкой: {result.stderr.strip() or result.stdout.strip()}")


def load_meta(path):
    """Читает уже сохранённые данные постов (чтобы не затирать их при тестовых запусках)."""
    if not exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return load(f)
    except (JSONDecodeError, OSError):
        return {}


def save_meta(path, meta):
    """Записывает данные постов через временный файл, чтобы не получить обрезанный файл."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        dump(meta, f, ensure_ascii=False, indent=1)
    replace_file(tmp, path)


def draw_status(done, total, files, size, extra="", unit="сообщений"):
    """Одна обновляющаяся строка: полоса, счётчик, файлы, объём."""
    ratio = min(done / total, 1) if total else 0
    filled = round(BAR_WIDTH * ratio)
    bar = "█" * filled + "░" * (BAR_WIDTH - filled)
    gigabytes = size / 1024 ** 3
    line = (f"[{bar}] {ratio * 100:3.0f}% | {unit} {done}/{total} "
            f"| файлов {files} | {gigabytes:.2f} ГБ {extra}")
    print(f"\r{line}".ljust(115), end="", flush=True)


async def download_file(msg, target, on_percent):
    """Качает во временный .part и переименовывает после завершения. True при успехе."""
    makedirs(dirname(target), exist_ok=True)
    tmp = f"{target}.part"

    def callback(done, total):
        on_percent(done * 100 // total if total else 0)

    for _ in range(MAX_RETRIES):
        if exists(tmp):
            remove(tmp)
        try:
            await msg.download_media(file=tmp, progress_callback=callback)
            replace_file(tmp, target)
            return True
        except FloodWaitError as error:
            print(f"\nTelegram просит подождать {error.seconds} с, жду...")
            await sleep(error.seconds + 1)
        except Exception as error:
            print(f"\nНе удалось скачать {relpath(target)}: {error}")
            break

    if exists(tmp):
        remove(tmp)  # неполный файл не оставляем
    return False


async def save_channel_media(client, entity):
    title = getattr(entity, "title", str(entity.id))
    root = join(OUT_DIR, safe_name(title))
    makedirs(join(root, PHOTO_DIR), exist_ok=True)
    makedirs(join(root, VIDEO_DIR), exist_ok=True)
    makedirs(join(root, POSTS_DIR), exist_ok=True)

    meta_path = join(root, META_NAME)
    meta = load_meta(meta_path)

    total_messages = (await client.get_messages(entity, limit=0)).total
    # при LIMIT прогресс считаем по постам, иначе по сообщениям
    total_count = LIMIT if LIMIT else total_messages
    unit = "постов" if LIMIT else "сообщений"

    stats = {"posts": 0, "files": 0, "skipped": 0, "failed": 0, "bytes": 0, "scanned": 0}
    pending_links = []  # ярлыки, которые нужно создать

    def status(extra=""):
        draw_status(stats["scanned"], total_count, stats["files"], stats["bytes"], extra, unit)

    print(f"[{title}] {unit} для обработки: {total_count}")
    status()

    try:
        async for group in iter_posts(client, entity):
            stats["scanned"] += 1 if LIMIT else len(group)
            group.sort(key=lambda m: m.id)

            if any(is_skipped(m) for m in group):  # сообщения про авторские права игнорируем
                status()
                continue

            post = next((m for m in group if m.text), None)
            if post is None and ONLY_WITH_TEXT:
                status()
                continue
            post_id = post.id if post else group[0].id

            photos = [m for m in group if m.photo]
            videos = [m for m in group if m.video]
            targets = (
                build_targets(root, PHOTO_DIR, post_id, photos, ".jpg")
                + build_targets(root, VIDEO_DIR, post_id, videos, ".mp4")
            ) if (photos or videos) else []

            if targets:
                stats["posts"] += 1
                # дата, просмотры и заголовок поста (у поста без подписи заголовок пустой)
                source = post or group[0]
                meta[str(post_id)] = {
                    "date": source.date.replace(tzinfo=None).isoformat(timespec="minutes"),
                    "views": source.views or 0,
                    "title": make_title(post) if post else "",
                }

            for msg, path in targets:
                if exists(path):  # уже скачано раньше
                    stats["skipped"] += 1
                    continue

                size = msg.file.size if msg.file and msg.file.size else 0
                if DRY_RUN:
                    stats["files"] += 1
                    stats["bytes"] += size
                    continue

                label = f"пост {post_id}: {relpath(path, root)}"
                ok = await download_file(
                    msg, path, lambda percent, label=label: status(f"| {label} {percent}%")
                )
                if ok:
                    stats["files"] += 1
                    stats["bytes"] += size
                else:
                    stats["failed"] += 1

            # папка поста: текст + ярлыки на все его медиафайлы
            if targets and not DRY_RUN:
                post_dir = join(root, POSTS_DIR, str(post_id))
                makedirs(post_dir, exist_ok=True)

                if post and post.text:
                    md_path = join(post_dir, f"{post_id}.md")
                    if not exists(md_path):
                        with open(md_path, "w", encoding="utf-8") as f:
                            f.write(post.text)

                for _, path in targets:
                    if exists(path):
                        link = link_path(post_dir, path)
                        if not exists(link):
                            pending_links.append((abspath(link), abspath(path)))

            status()
    finally:
        # данные постов сохраняем всегда, даже если скрипт прервали
        if not DRY_RUN:
            save_meta(meta_path, meta)

    print()  # переход со строки прогресса на новую строку

    if pending_links:
        print(f"[{title}] создаю ярлыки: {len(pending_links)}...")
        create_shortcuts(pending_links)

    total = f"{stats['bytes'] / 1024 ** 3:.2f} ГБ"
    if DRY_RUN:
        print(f"[{title}] пробный режим: постов с медиа {stats['posts']}, "
              f"к скачиванию {stats['files']} файлов (~{total}), уже есть {stats['skipped']}")
    else:
        print(f"[{title}] готово: постов с медиа {stats['posts']}, скачано {stats['files']} ({total}), "
              f"пропущено (уже есть) {stats['skipped']}, ошибок {stats['failed']}, "
              f"ярлыков {len(pending_links)}, в {META_NAME} записей {len(meta)}")


async def main(client):
    await client.connect()
    try:
        if not await client.is_user_authorized():
            print("Вход не выполнен, запускаю вход по QR (qr_login.py)...")
            if not await login(client):
                return False

        # заполняет кэш каналов: без него новая сессия не найдёт приватный канал по ID
        await client.get_dialogs()

        for raw in RAW_CHANNELS.split(","):
            if not raw.strip():
                continue
            try:
                entity = await client.get_entity(parse_channel(raw))
            except ValueError:
                print(f"Канал {raw.strip()} не найден: проверьте ID и что аккаунт подписан на канал.")
                continue
            await save_channel_media(client, entity)

        if LOGOUT_AFTER:
            await logout(client)  # logout.py
        return True
    finally:
        await client.disconnect()


def run():
    had_session = SESSION_FILE.exists()
    client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)
    ok = False

    try:
        ok = client.loop.run_until_complete(main(client))
    except KeyboardInterrupt:
        print("\nОстановлено пользователем (Ctrl+C).")
        raise SystemExit(130)
    finally:
        # вход отменён или прерван: не оставляем пустой файл сессии
        if not had_session and not ok:
            SESSION_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    run()