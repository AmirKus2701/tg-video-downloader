from json import JSONDecodeError, dump, load
from os import replace as replace_file
from os.path import exists


def load_meta(path):
    """Читает 0_meta.json: {id поста: {date, views, title, length}}."""
    if not exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return load(f)
    except (JSONDecodeError, OSError):
        return {}


def save_meta(path, meta):
    """Пишет через временный файл, чтобы не получить обрезанный JSON."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        dump(meta, f, ensure_ascii=False, indent=1)
    replace_file(tmp, path)