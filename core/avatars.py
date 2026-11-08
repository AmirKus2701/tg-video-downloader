from os import replace as replace_file
from os.path import exists
from pathlib import Path

from core.settings import data_dir


def avatar_path(profile_id):
    """Где лежит аватарка профиля. Хранится рядом с настройками приложения, а не в скачанных файлах."""
    folder = data_dir() / "avatars"
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder / f"{profile_id}.jpg")


def avatar_file(profile_id):
    """Путь к сохранённой аватарке или None, если её нет."""
    path = avatar_path(profile_id)
    return path if exists(path) else None


def remove_avatar(profile_id):
    try:
        Path(avatar_path(profile_id)).unlink(missing_ok=True)
    except OSError:
        pass


def save_avatar(profile_id, data):
    """data: байты картинки или None (у аккаунта нет фото).
    Возвращает путь к файлу или None, если фото нет."""
    if not data:
        remove_avatar(profile_id)
        return None
    path = avatar_path(profile_id)
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    replace_file(tmp, path)
    return path


# ---------- аватарки каналов ----------


def channel_avatar_path(channel_id):
    """Путь к кэшированной аватарке канала."""
    folder = data_dir() / "channel_avatars"
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder / f"{channel_id}.jpg")


def channel_avatar_file(channel_id):
    """Путь к аватарке канала или None, если её ещё нет."""
    path = channel_avatar_path(channel_id)
    return path if exists(path) else None


def save_channel_avatar(channel_id, data):
    """Сохраняет аватарку канала. data=None → удаляет старую."""
    path = channel_avatar_path(channel_id)
    if not data:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
        return None
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    replace_file(tmp, path)
    return path
