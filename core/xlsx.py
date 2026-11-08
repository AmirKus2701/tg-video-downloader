from os import chmod
from os import replace as replace_file
from os.path import abspath, exists
from stat import S_IREAD, S_IWRITE
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl.styles import Font
from openpyxl.workbook.protection import WorkbookProtection

DATE_FORMAT = "YYYY-MM-DD HH:MM"
LINK_FONT = Font(color="0563C1", underline="single")


def set_link(cell, path, label):
    """Кликабельная ссылка. Формула HYPERLINK; если путь длиннее лимита Excel (255), обычная гиперссылка."""
    path = abspath(path)
    if len(path) <= 250 and len(label) <= 250:
        safe_path = path.replace('"', '""')
        safe_label = label.replace('"', '""')
        cell.value = f'=HYPERLINK("{safe_path}", "{safe_label}")'
    else:
        cell.value = label
        cell.hyperlink = path
    cell.font = LINK_FONT


def protect_workbook(wb):
    """Защита структуры книги без пароля. Лист не защищаем, чтобы работала сортировка."""
    wb.security = WorkbookProtection(lockStructure=True)


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
    return patched


def save_protected(wb, path):
    """Сохраняет файл с защитой структуры и атрибутом «только чтение»."""
    if exists(path):
        chmod(path, S_IWRITE)  # иначе повторный запуск не сможет перезаписать файл
    protect_workbook(wb)
    wb.save(path)
    add_read_only_flag(path)
    chmod(path, S_IREAD)