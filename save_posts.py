from os import chmod, getenv, makedirs
from os import replace as replace_file
from os.path import abspath, exists, join
from re import sub
from stat import S_IREAD, S_IWRITE
from zipfile import ZIP_DEFLATED, ZipFile

from dotenv import load_dotenv, find_dotenv
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.workbook.protection import WorkbookProtection
from telethon import TelegramClient

from logout import logout
from qr_login import API_HASH, API_ID, SESSION_FILE, SESSION_NAME, login

load_dotenv(find_dotenv())

RAW_CHANNELS = getenv("TG_CHANNEL")
OUT_DIR = "posts"
LIMIT = 5          # None: все посты; число, например 5: только последние 5 (для теста)
DRY_RUN = False
LOGOUT_AFTER = False   # True: после сохранения выйти из аккаунта (сессия удалится)

if not RAW_CHANNELS:
    raise SystemExit("Заполните TG_CHANNEL в .env")


def parse_channel(value):
    value = value.strip()
    return int(value) if value.lstrip("-").isdigit() else value


def safe_name(text, max_len=60):
    text = sub(r'[\\/:*?"<>|\n\r]+', " ", text or "").strip()
    return text[:max_len] or "channel"

SKIP_PHRASES = (
    "due to copyright infringement",  # This message couldn't be displayed ... due to copyright infringement.
)

def is_skipped(msg):
    """True для сообщений, которые не нужно сохранять."""
    text = (msg.raw_text or "").replace("’", "'").lower()
    return any(phrase in text for phrase in SKIP_PHRASES)


def make_title(msg, max_len=100):
    """Заголовок для Excel: первая непустая строка чистого текста, без markdown."""
    for line in (msg.raw_text or "").splitlines():
        if line.strip():
            return line.strip()[:max_len]
    return ""

def protect_workbook(wb, ws):
    """Защита структуры книги без пароля. Лист не защищаем, чтобы работала сортировка."""
    wb.security = WorkbookProtection(lockStructure=True)  # листы нельзя добавить, удалить, переименовать


def add_read_only_flag(path):
    """Добавляет в файл рекомендацию «открывать только для чтения»."""
    tmp = f"{path}.tmp"
    patched = False

    with ZipFile(path) as src, ZipFile(tmp, "w", ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "xl/workbook.xml" and b"<workbookPr" in data:
                data = data.replace(
                    b"<workbookPr",
                    b'<fileSharing readOnlyRecommended="1"/><workbookPr',
                    1,
                )
                patched = True
            dst.writestr(item, data)

    replace_file(tmp, path)
    if not patched:
        print("Не удалось добавить рекомендацию «только чтение» в файл.")


def save_protected(wb, ws, path):
    """Сохраняет файл с защитой и ставит атрибут «только чтение»."""
    if exists(path):
        chmod(path, S_IWRITE)  # снимаем атрибут, иначе повторный запуск не сможет перезаписать файл

    protect_workbook(wb, ws)
    wb.save(path)
    add_read_only_flag(path)
    chmod(path, S_IREAD)       # файл всегда открывается только для чтения


async def save_channel(client, channel):
    entity = await client.get_entity(channel)
    title = getattr(entity, "title", str(channel))
    folder = join(OUT_DIR, safe_name(title))
    makedirs(folder, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Посты"
    ws.append(["id", "дата", "просмотры", "заголовок", "фото", "видео", "длина", "файл"])

    count = 0
    # reverse=True: от старых постов к новым (при LIMIT вернутся последние посты)
    async for msg in client.iter_messages(entity, reverse=LIMIT is None, limit=LIMIT):
        if not msg.text or is_skipped(msg):  # пустые и «авторские» сообщения пропускаем
            continue

        file_name = f"{msg.id}.md"
        with open(join(folder, file_name), "w", encoding="utf-8") as f:
            f.write(msg.text)  # в .md остаётся форматирование

        ws.append([
            msg.id,
            msg.date.replace(tzinfo=None),   # настоящая дата (Excel не принимает дату с часовым поясом)
            msg.views or 0,
            make_title(msg),            # в Excel заголовок без markdown
            "да" if msg.photo else "нет",
            "да" if msg.video else "нет",
            len(msg.raw_text),          # длина чистого текста, без символов разметки
            file_name,
        ])

        # кликабельная ссылка с полным путём к файлу
        full_path = abspath(join(folder, file_name))
        cell = ws.cell(row=ws.max_row, column=8)
        cell.value = f'=HYPERLINK("{full_path}", "{file_name}")'
        cell.font = Font(color="0563C1", underline="single")
        ws.cell(row=ws.max_row, column=2).number_format = "YYYY-MM-DD HH:MM"

        count += 1
        print(f"\r[{title}] сохранено постов: {count}", end="", flush=True)

    for column, width in zip("ABCDEFGH", (10, 18, 12, 60, 8, 8, 8, 14)):
        ws.column_dimensions[column].width = width

    ws.freeze_panes = "A2"                    # закрепляем первую строку (заголовки)
    ws.auto_filter.ref = f"A1:H{ws.max_row}"  # стрелки сортировки и фильтра

    save_protected(wb, ws, join(folder, "0_index.xlsx"))
    print(f"\n[{title}] готово: {count} постов -> {folder}")

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
                await save_channel(client, parse_channel(raw))
            except ValueError:
                print(f"Канал {raw.strip()} не найден: проверьте ID и что аккаунт подписан на канал.")

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