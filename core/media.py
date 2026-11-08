from asyncio import sleep, to_thread
from json import dump
from os import makedirs, remove, symlink
from os import replace as replace_file
from os.path import abspath, basename, dirname, exists, join, relpath
from subprocess import run as run_process
from sys import platform
from tempfile import TemporaryDirectory

from telethon.errors import FloodWaitError

from core.common import Cancelled
from core.layout import META_NAME, PHOTO_DIR, POSTS_DIR, TEXTS_DIR, VIDEO_DIR
from core.meta import load_meta, save_meta
from core.telegram import iter_posts, scan_size, step
from core.utils import channel_folder, is_skipped, make_title

MAX_RETRIES = 3

# PowerShell-скрипт создаёт .lnk ярлыки списком (один запуск на весь канал)
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


def file_ext(msg, default):
    return (msg.file.ext if msg.file and msg.file.ext else None) or default


def build_targets(root, kind_dir, post_id, items, default_ext):
    """(сообщение, путь к файлу): один файл лежит прямо в папке типа, несколько в подпапке с номерами."""
    base = join(root, kind_dir)
    if len(items) == 1:
        return [(items[0], join(base, f"{post_id}{file_ext(items[0], default_ext)}"))]

    folder = join(base, str(post_id))
    return [
        (msg, join(folder, f"{number}{file_ext(msg, default_ext)}"))
        for number, msg in enumerate(items, start=1)
    ]


def link_path(post_dir, target):
    return join(post_dir, basename(target) + (".lnk" if platform == "win32" else ""))


def create_shortcuts(pairs):
    """Ярлыки (путь ярлыка, путь файла). Возвращает текст ошибки или пустую строку."""
    if not pairs:
        return ""

    if platform != "win32":
        try:
            for link, target in pairs:
                symlink(target, link)
        except OSError as error:
            return str(error)
        return ""

    with TemporaryDirectory() as tmp:
        json_path = join(tmp, "links.json")
        ps_path = join(tmp, "make_links.ps1")
        with open(json_path, "w", encoding="utf-8") as f:
            # ensure_ascii=True: кириллица пишется как \uXXXX, без проблем с кодировкой
            dump([{"link": link, "target": target} for link, target in pairs], f, ensure_ascii=True)
        with open(ps_path, "w", encoding="utf-8") as f:
            f.write(PS_SCRIPT)

        result = run_process(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_path, json_path],
            capture_output=True,
            text=True,
            errors="replace",
        )

    return "" if result.returncode == 0 else (result.stderr.strip() or result.stdout.strip())


async def wait_seconds(seconds, rep):
    """Пауза, которую можно прервать кнопкой «Остановить»."""
    for _ in range(int(seconds) + 1):
        rep.check()
        await sleep(1)


async def download_file(msg, target, rep, on_percent):
    """Качает в .part и переименовывает после завершения. True при успехе."""
    makedirs(dirname(target), exist_ok=True)
    tmp = f"{target}.part"

    def callback(received, total):
        rep.check()  # остановка посреди файла
        on_percent(received * 100 // total if total else 0)

    for _ in range(MAX_RETRIES):
        if exists(tmp):
            remove(tmp)
        try:
            await msg.download_media(file=tmp, progress_callback=callback)
            replace_file(tmp, target)
            return True
        except Cancelled:
            if exists(tmp):
                remove(tmp)
            raise
        except FloodWaitError as error:
            rep.log(f"Telegram просит подождать {error.seconds} с, жду...")
            await wait_seconds(error.seconds, rep)
        except Exception as error:
            rep.log(f"Не удалось скачать {relpath(target)}: {error}")
            break

    if exists(tmp):
        remove(tmp)  # неполный файл не оставляем
    return False


async def save_media(client, entity, opts, rep):
    """Фото и видео в 0_фото / 0_видео, папки постов с ярлыками, данные постов в 0_meta.json."""
    root = channel_folder(opts.out_dir, entity)
    if not opts.dry_run:
        for folder in (PHOTO_DIR, VIDEO_DIR, POSTS_DIR):
            makedirs(join(root, folder), exist_ok=True)

    meta_path = join(root, META_NAME)
    meta = load_meta(meta_path)
    total, unit = await scan_size(client, entity, opts.limit)

    stats = {"posts": 0, "files": 0, "skipped": 0, "failed": 0, "bytes": 0, "scanned": 0}
    pending_links = []
    cancelled = False

    def report(extra=""):
        gigabytes = stats["bytes"] / 1024 ** 3
        text = f"{unit} {stats['scanned']}/{total} · файлов {stats['files']} · {gigabytes:.2f} ГБ"
        rep.progress(stats["scanned"], total, f"{text} · {extra}" if extra else text)

    try:
        async for group in iter_posts(client, entity, opts.limit):
            rep.check()
            stats["scanned"] += step(group, opts.limit)
            group.sort(key=lambda m: m.id)

            if any(is_skipped(m) for m in group):  # сообщения про авторские права игнорируем
                report()
                continue

            post = next((m for m in group if m.text), None)
            if post is None and opts.only_with_text:
                report()
                continue
            post_id = post.id if post else group[0].id

            photos = [m for m in group if m.photo] if opts.photos else []
            videos = [m for m in group if m.video] if opts.videos else []
            targets = (
                build_targets(root, PHOTO_DIR, post_id, photos, ".jpg")
                + build_targets(root, VIDEO_DIR, post_id, videos, ".mp4")
            )

            if targets:
                stats["posts"] += 1
                source = post or group[0]
                # update, а не замена: поля, записанные при сохранении текстов (длина), остаются
                meta.setdefault(str(post_id), {}).update({
                    "date": source.date.replace(tzinfo=None).isoformat(timespec="minutes"),
                    "views": source.views or 0,
                    "title": make_title(post) if post else "",
                })

            for msg, path in targets:
                if exists(path):  # уже скачано раньше
                    stats["skipped"] += 1
                    continue

                size = msg.file.size if msg.file and msg.file.size else 0
                if opts.dry_run:
                    stats["files"] += 1
                    stats["bytes"] += size
                    continue

                label = f"пост {post_id}: {relpath(path, root)}"
                ok = await download_file(
                    msg, path, rep, lambda percent, label=label: report(f"{label} {percent}%")
                )
                if ok:
                    stats["files"] += 1
                    stats["bytes"] += size
                else:
                    stats["failed"] += 1

            # папка поста: только ярлыки (на текст из «Текст постов» и на все медиафайлы поста)
            if targets and not opts.dry_run:
                post_dir = join(root, POSTS_DIR, str(post_id))
                makedirs(post_dir, exist_ok=True)

                linked = [path for _, path in targets if exists(path)]
                text_path = join(root, TEXTS_DIR, f"{post_id}.md")
                if exists(text_path):
                    linked.insert(0, text_path)

                for path in linked:
                    link = link_path(post_dir, path)
                    if not exists(link):
                        pending_links.append((abspath(link), abspath(path)))

            report()
    except Cancelled:
        cancelled = True
    finally:
        if not opts.dry_run:
            save_meta(meta_path, meta)  # данные постов сохраняем всегда, даже при остановке

    if pending_links and not opts.dry_run:
        rep.log(f"Создаю ярлыки: {len(pending_links)}...")
        error = await to_thread(create_shortcuts, pending_links)
        if error:
            rep.log(f"Ярлыки созданы с ошибкой: {error}")

    gigabytes = f"{stats['bytes'] / 1024 ** 3:.2f} ГБ"
    if opts.dry_run:
        rep.log(f"Медиа (пробный режим): постов {stats['posts']}, к скачиванию {stats['files']} файлов "
                f"(~{gigabytes}), уже есть {stats['skipped']}")
    else:
        rep.log(f"Медиа: постов {stats['posts']}, скачано {stats['files']} ({gigabytes}), "
                f"уже было {stats['skipped']}, ошибок {stats['failed']}, ярлыков {len(pending_links)}")

    if cancelled:
        raise Cancelled
    return stats