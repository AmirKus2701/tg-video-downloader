from datetime import datetime
from os import chmod, listdir, remove, stat
from os.path import basename, dirname, exists, isdir, isfile, join, relpath, splitext
from stat import S_IWRITE

from openpyxl import Workbook, load_workbook

from core.layout import (
    LEGACY_INDEX_NAMES, META_NAME, NAV_NAME, PHOTO_DIR, POSTS_DIR, TEXTS_DIR, VIDEO_DIR,
)
from core.meta import load_meta, save_meta
from core.tz import load_tz, to_local
from core.xlsx import DATE_FORMAT, save_protected, set_link

POSTS_HEADERS = ["id", "дата", "просмотры", "заголовок", "длина", "фото", "видео",
                 "папка поста", "текст", "фото (ссылка)", "видео (ссылка)"]
POSTS_WIDTHS = (10, 18, 12, 60, 8, 8, 8, 14, 14, 18, 18)
FILES_HEADERS = ["id поста", "дата", "заголовок", "тип", "№", "файл", "размер, МБ"]
FILES_WIDTHS = (10, 18, 60, 8, 6, 45, 12)


def number_key(name):
    stem = splitext(name)[0]
    return (0, int(stem)) if stem.isdigit() else (1, stem)


def scan_media(root, kind_dir):
    """{id поста: [пути к файлам]}. Одиночный файл лежит в папке типа, альбом в подпапке с номером поста."""
    base = join(root, kind_dir)
    result = {}
    if not isdir(base):
        return result

    for name in listdir(base):
        path = join(base, name)
        if isdir(path) and name.isdigit():
            files = [
                join(path, item)
                for item in sorted(listdir(path), key=number_key)
                if not item.endswith(".part")
            ]
            if files:
                result[int(name)] = files
        elif isfile(path) and not name.endswith(".part") and splitext(name)[0].isdigit():
            result[int(splitext(name)[0])] = [path]
    return result


def read_legacy_index(path):
    """Старый индекс (id, дата, просмотры, заголовок, фото, видео, длина) -> {id: {date, views, title, length}}."""
    entries = {}
    try:
        wb = load_workbook(path, read_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, max_col=7, values_only=True):
            post_id, date, views, title = row[0], row[1], row[2], row[3]
            length = row[6] if len(row) > 6 else None
            if post_id is None:
                continue
            if isinstance(date, datetime):
                date = date.isoformat(timespec="minutes")
            elif isinstance(date, str):
                try:
                    date = datetime.strptime(date, "%Y-%m-%d %H:%M").isoformat(timespec="minutes")
                except ValueError:
                    date = None
            entries[str(int(post_id))] = {"date": date, "views": views, "title": title, "length": length}
        wb.close()
    except Exception:
        return {}
    return entries


def import_legacy(root, meta, rep):
    """Переносит данные из старых индексов в meta (ничего не затирая). Даты там тоже в UTC.
    Возвращает список найденных файлов."""
    found = []
    for name in LEGACY_INDEX_NAMES:
        path = join(root, name)
        if not exists(path):
            continue
        found.append(path)
        for key, entry in read_legacy_index(path).items():
            record = meta.setdefault(key, {})
            for field, value in entry.items():
                if value is not None:
                    record.setdefault(field, value)  # существующие значения не трогаем
    if found:
        rep.log(f"Данные из старого индекса перенесены в {META_NAME}.")
    return found


def remove_legacy(paths, rep):
    for path in paths:
        try:
            chmod(path, S_IWRITE)  # снимаем «только чтение»
            remove(path)
            rep.log(f"Старый файл {basename(path)} удалён.")
        except OSError as error:
            rep.log(f"Не удалось удалить {basename(path)}: {error}")


def to_row(entry, tz_name):
    """(дата в местном времени, просмотры, заголовок, длина) для одного поста."""
    try:
        date = to_local(datetime.fromisoformat(entry.get("date")), tz_name)
    except (TypeError, ValueError):
        date = None
    return date, entry.get("views"), entry.get("title"), entry.get("length")


def add_media_link(cell, files):
    """Один файл: ссылка на файл. Несколько: ссылка на папку альбома."""
    if not files:
        return
    if len(files) == 1:
        set_link(cell, files[0], basename(files[0]))
    else:
        set_link(cell, dirname(files[0]), f"{len(files)} шт.")


def find_text(root, post_id):
    """Файл с текстом поста: сначала «Текст постов», затем старое место в корне папки канала."""
    for path in (join(root, TEXTS_DIR, f"{post_id}.md"), join(root, f"{post_id}.md")):
        if exists(path):
            return path
    return None


def build_navigator(root, rep, tz_name):
    """Строит единственную таблицу 0_navigator.xlsx. Возвращает (постов, файлов) или None."""
    if load_tz(tz_name) is None:
        rep.log(f"Часовой пояс {tz_name} не найден (установите пакет tzdata). "
                "Использую часовой пояс компьютера.")

    meta_path = join(root, META_NAME)
    meta = load_meta(meta_path)

    legacy = import_legacy(root, meta, rep)
    if legacy:
        save_meta(meta_path, meta)  # данные старого индекса теперь хранятся в 0_meta.json

    photos = scan_media(root, PHOTO_DIR)
    videos = scan_media(root, VIDEO_DIR)
    post_ids = sorted({int(key) for key in meta} | set(photos) | set(videos))

    if not post_ids:
        rep.log("Навигатор: постов не найдено.")
        return None

    wb = Workbook()
    posts_ws = wb.active
    posts_ws.title = "Посты"
    posts_ws.append(POSTS_HEADERS)

    files_ws = wb.create_sheet("Файлы")
    files_ws.append(FILES_HEADERS)

    total_files = 0
    for post_id in post_ids:
        date, views, title, length = to_row(meta.get(str(post_id), {}), tz_name)
        post_photos = photos.get(post_id, [])
        post_videos = videos.get(post_id, [])

        posts_ws.append([post_id, date, views, title, length, len(post_photos), len(post_videos)])
        row = posts_ws.max_row
        if date:
            posts_ws.cell(row, 2).number_format = DATE_FORMAT

        post_dir = join(root, POSTS_DIR, str(post_id))
        if isdir(post_dir):
            set_link(posts_ws.cell(row, 8), post_dir, "папка")

        text_path = find_text(root, post_id)
        if text_path:
            set_link(posts_ws.cell(row, 9), text_path, f"{post_id}.md")

        add_media_link(posts_ws.cell(row, 10), post_photos)
        add_media_link(posts_ws.cell(row, 11), post_videos)

        for kind, items in (("фото", post_photos), ("видео", post_videos)):
            for number, path in enumerate(items, start=1):
                size_mb = round(stat(path).st_size / 1024 ** 2, 2)
                files_ws.append([post_id, date, title, kind, number, None, size_mb])
                file_row = files_ws.max_row
                if date:
                    files_ws.cell(file_row, 2).number_format = DATE_FORMAT
                set_link(files_ws.cell(file_row, 6), path, relpath(path, root))
                total_files += 1

    for column, width in zip("ABCDEFGHIJK", POSTS_WIDTHS):
        posts_ws.column_dimensions[column].width = width
    for column, width in zip("ABCDEFG", FILES_WIDTHS):
        files_ws.column_dimensions[column].width = width

    for sheet, last_column in ((posts_ws, "K"), (files_ws, "G")):
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = f"A1:{last_column}{sheet.max_row}"

    save_protected(wb, join(root, NAV_NAME))
    rep.log(f"Навигатор: постов {len(post_ids)}, медиафайлов {total_files}, "
            f"время в поясе {tz_name} -> {NAV_NAME}")

    remove_legacy(legacy, rep)  # старый индекс удаляем только после успешного сохранения навигатора
    return len(post_ids), total_files