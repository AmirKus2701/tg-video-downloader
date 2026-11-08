from datetime import datetime
from json import JSONDecodeError, load
from os import listdir, stat
from os.path import (
    abspath,
    basename,
    dirname,
    exists,
    isdir,
    isfile,
    join,
    relpath,
    splitext,
)

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from save_media import META_NAME, PHOTO_DIR, POSTS_DIR, VIDEO_DIR
from save_posts import OUT_DIR, save_protected

INDEX_NAME = "0_index.xlsx"  # таблица с текстами постов (из save_posts.py)
NAV_NAME = "0_navigator.xlsx"  # имя навигатора, можно поменять
DATE_FORMAT = "YYYY-MM-DD HH:MM"
LINK_FONT = Font(color="0563C1", underline="single")


def set_link(cell, path, label):
    """Кликабельная ссылка. Формула HYPERLINK; если путь слишком длинный (лимит Excel 255 символов), обычная гиперссылка."""
    path = abspath(path)
    if len(path) <= 250 and len(label) <= 250:
        safe_path = path.replace('"', '""')
        safe_label = label.replace('"', '""')
        cell.value = f'=HYPERLINK("{safe_path}", "{safe_label}")'
    else:
        cell.value = label
        cell.hyperlink = path
    cell.font = LINK_FONT


def number_key(name):
    stem = splitext(name)[0]
    return (0, int(stem)) if stem.isdigit() else (1, stem)


def scan_media(root, kind_dir):
    """Возвращает {id поста: [пути к файлам]}.
    Одиночный файл лежит прямо в папке типа, альбом - в подпапке с номером поста."""
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
        elif (
            isfile(path) and not name.endswith(".part") and splitext(name)[0].isdigit()
        ):
            result[int(splitext(name)[0])] = [path]
    return result


def read_meta(root):
    """Читает 0_meta.json (его пишет save_media.py): {id: (дата, просмотры, заголовок)}. Есть у всех постов с медиа."""
    path = join(root, META_NAME)
    meta = {}
    if not exists(path):
        print(
            f"Нет файла {META_NAME}: запустите save_media.py, чтобы получить даты постов без текста."
        )
        return meta

    try:
        with open(path, encoding="utf-8") as f:
            data = load(f)
    except (JSONDecodeError, OSError):
        print(f"Не удалось прочитать {META_NAME}.")
        return meta

    for key, item in data.items():
        try:
            date = datetime.fromisoformat(item.get("date"))
        except (TypeError, ValueError):
            date = None
        meta[int(key)] = (date, item.get("views"), item.get("title"))

    print(f"Из {META_NAME} прочитано постов: {len(meta)}")
    return meta


def read_index(root):
    """Читает даты, просмотры и заголовки из 0_index.xlsx: {id: (дата, просмотры, заголовок)}. Только посты с текстом."""
    path = join(root, INDEX_NAME)
    meta = {}
    if not exists(path):
        print(f"Нет файла {INDEX_NAME} (сначала запустите save_posts.py).")
        return meta

    wb = load_workbook(path, read_only=True)
    ws = wb.active
    for post_id, date, views, title in ws.iter_rows(
        min_row=2, max_col=4, values_only=True
    ):
        if post_id is None:
            continue
        if isinstance(date, str):
            try:
                date = datetime.strptime(date, "%Y-%m-%d %H:%M")
            except ValueError:
                pass  # оставляем как есть
        meta[int(post_id)] = (date, views, title)
    wb.close()

    print(f"Из {INDEX_NAME} прочитано постов: {len(meta)}")
    return meta


def add_media_link(cell, files):
    """Один файл: ссылка на файл. Несколько: ссылка на папку альбома."""
    if not files:
        return
    if len(files) == 1:
        set_link(cell, files[0], basename(files[0]))
    else:
        set_link(cell, dirname(files[0]), f"{len(files)} шт.")


def build_navigator(root):
    meta = read_meta(root)
    meta.update(
        read_index(root)
    )  # данные из 0_index.xlsx главнее, 0_meta.json добирает недостающие

    photos = scan_media(root, PHOTO_DIR)
    videos = scan_media(root, VIDEO_DIR)
    post_ids = sorted(set(meta) | set(photos) | set(videos))

    if not post_ids:
        print(f"[{basename(root)}] постов не найдено, пропускаю.")
        return

    missing = [post_id for post_id in post_ids if post_id not in meta]
    if missing:
        print(
            f"[{basename(root)}] постов без даты: {len(missing)}, например {missing[:5]}"
        )

    wb = Workbook()
    posts_ws = wb.active
    posts_ws.title = "Посты"
    posts_ws.append(
        [
            "id",
            "дата",
            "просмотры",
            "заголовок",
            "фото",
            "видео",
            "папка поста",
            "текст",
            "фото (ссылка)",
            "видео (ссылка)",
        ]
    )

    files_ws = wb.create_sheet("Файлы")
    files_ws.append(["id поста", "дата", "заголовок", "тип", "№", "файл", "размер, МБ"])

    total_files = 0
    for post_id in post_ids:
        date, views, title = meta.get(post_id, (None, None, None))
        post_photos = photos.get(post_id, [])
        post_videos = videos.get(post_id, [])

        # --- лист «Посты» ---
        posts_ws.append(
            [post_id, date, views, title, len(post_photos), len(post_videos)]
        )
        row = posts_ws.max_row
        if isinstance(date, datetime):
            posts_ws.cell(row, 2).number_format = DATE_FORMAT

        post_dir = join(root, POSTS_DIR, str(post_id))
        if isdir(post_dir):
            set_link(posts_ws.cell(row, 7), post_dir, "папка")

        md_path = join(post_dir, f"{post_id}.md")
        if not exists(md_path):
            md_path = join(root, f"{post_id}.md")
        if exists(md_path):
            set_link(posts_ws.cell(row, 8), md_path, f"{post_id}.md")

        add_media_link(posts_ws.cell(row, 9), post_photos)
        add_media_link(posts_ws.cell(row, 10), post_videos)

        # --- лист «Файлы» ---
        for kind, items in (("фото", post_photos), ("видео", post_videos)):
            for number, path in enumerate(items, start=1):
                size_mb = round(stat(path).st_size / 1024**2, 2)
                files_ws.append([post_id, date, title, kind, number, None, size_mb])
                file_row = files_ws.max_row
                if isinstance(date, datetime):
                    files_ws.cell(file_row, 2).number_format = DATE_FORMAT
                set_link(files_ws.cell(file_row, 6), path, relpath(path, root))
                total_files += 1

    # оформление: ширина колонок, закрепление первой строки, фильтры
    for column, width in zip("ABCDEFGHIJ", (10, 18, 12, 60, 8, 8, 14, 14, 18, 18)):
        posts_ws.column_dimensions[column].width = width
    for column, width in zip("ABCDEFG", (10, 18, 60, 8, 6, 45, 12)):
        files_ws.column_dimensions[column].width = width

    for sheet, last_column in ((posts_ws, "J"), (files_ws, "G")):
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = f"A1:{last_column}{sheet.max_row}"

    save_protected(wb, posts_ws, join(root, NAV_NAME))
    print(
        f"[{basename(root)}] навигатор готов: постов {len(post_ids)}, медиафайлов {total_files} -> {NAV_NAME}"
    )


def run():
    if not isdir(OUT_DIR):
        raise SystemExit(f"Папка {OUT_DIR} не найдена: сначала скачайте посты и медиа.")

    try:
        for name in sorted(listdir(OUT_DIR)):
            root = join(OUT_DIR, name)
            if not isdir(root):
                continue
            if not any(
                isdir(join(root, folder))
                for folder in (PHOTO_DIR, VIDEO_DIR, POSTS_DIR)
            ):
                continue  # это не папка канала с медиа
            try:
                build_navigator(root)
            except PermissionError:
                print(
                    f"[{name}] не удалось записать {NAV_NAME}: закройте его в Excel и запустите снова."
                )
    except KeyboardInterrupt:
        print("\nОстановлено пользователем (Ctrl+C).")
        raise SystemExit(130)


if __name__ == "__main__":
    run()
