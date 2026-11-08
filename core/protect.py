from os import chmod, listdir
from os.path import exists, isfile, join
from stat import S_IREAD, S_IWRITE


def unlock(path):
    """Снимает «только чтение» (нужно, чтобы программа могла перезаписать или удалить файл)."""
    if exists(path):
        chmod(path, S_IREAD | S_IWRITE)


def lock(path):
    """Ставит «только чтение»."""
    chmod(path, S_IREAD)


def write_locked(path, text):
    """Записывает текст и сразу защищает файл от редактирования."""
    unlock(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    lock(path)


def lock_folder(folder):
    """Защищает все .md в папке (в том числе скачанные раньше). Возвращает их число."""
    count = 0
    try:
        names = listdir(folder)
    except OSError:
        return 0
    for name in names:
        path = join(folder, name)
        if name.endswith(".md") and isfile(path):
            try:
                lock(path)
                count += 1
            except OSError:
                pass
    return count