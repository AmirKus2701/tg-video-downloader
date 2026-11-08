from json import JSONDecodeError, dump, load
from os import getenv
from os import replace as replace_file
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from dotenv import find_dotenv, load_dotenv

from core.tz import DEFAULT_TZ
from core.utils import safe_name

load_dotenv(find_dotenv())  # нужен для dev_cli.py (TG_CHANNEL и ключи разработчика)

APP_DIR_NAME = "tg-video-downloader"
LEGACY_PROFILE_ID = "legacy"
DEFAULTS = {
    "profiles": [],
    "api_id": "",  # старые поля: нужны только для переноса в профиль и для dev_cli.py
    "api_hash": "",
    "out_dir": "",
    "theme": "dark",
    "timezone": DEFAULT_TZ,
}


def data_dir():
    """Папка данных приложения (настройки и сессии): %APPDATA%\\tg-video-downloader."""
    base = getenv("APPDATA")
    path = (Path(base) if base else Path.home() / ".config") / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file():
    return data_dir() / "settings.json"


def session_path():
    """Файл входа старой версии (до профилей)."""
    return str(data_dir() / "session")


def default_out_dir():
    """Папка по умолчанию — TelegramArchive на рабочем столе."""
    desktop = Path.home() / "Desktop"
    # На всякий случай, если папки Desktop нет (редко, но бывает)
    if not desktop.exists():
        desktop = Path.home()
    return str(desktop / "TelegramArchive")


# ---------- профили ----------


def new_profile(api_id, api_hash, name=""):
    return {
        "id": uuid4().hex[:8],
        "name": name,
        "api_id": api_id,
        "api_hash": api_hash,
        "tg_user_id": None,
        "out_dir": "",
    }


def display_name(profile):
    return profile.get("name") or "Новый профиль"


def find_profile(settings, profile_id):
    return next((p for p in settings["profiles"] if p["id"] == profile_id), None)


def profile_out_dir(settings, profile):
    """Папка скачивания профиля: своя у каждого профиля, чтобы файлы разных людей не смешивались."""
    if profile.get("out_dir"):
        return profile["out_dir"]
    return str(Path(settings["out_dir"]) / safe_name(display_name(profile)))


def profile_session(profile):
    """Файл входа профиля: у каждого профиля свой, поэтому аккаунты не смешиваются."""
    if profile.get("session"):  # профиль, перенесённый из старой версии
        return profile["session"]
    folder = data_dir() / "profiles" / profile["id"]
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder / "session")


def delete_profile_files(profile):
    """Удаляет файл входа профиля. Скачанные файлы не трогает."""
    try:
        legacy = profile.get("session")
        if legacy:
            for suffix in (".session", ".session-journal"):
                Path(f"{legacy}{suffix}").unlink(missing_ok=True)
        else:
            rmtree(data_dir() / "profiles" / profile["id"], ignore_errors=True)
    except OSError:
        pass


def has_credentials(item):
    return str(item.get("api_id", "")).isdigit() and bool(item.get("api_hash"))


# ---------- настройки ----------


def load_settings(use_env=False):
    """use_env=True только для dev_cli.py: берёт ключи из .env. Приложение их из .env не читает."""
    data = dict(DEFAULTS)
    try:
        with open(settings_file(), encoding="utf-8") as f:
            loaded = load(f)
        if isinstance(loaded, dict):
            data.update(loaded)
    except (OSError, JSONDecodeError):
        pass

    profiles = data.get("profiles")
    data["profiles"] = (
        [p for p in profiles if isinstance(p, dict) and p.get("id")]
        if isinstance(profiles, list)
        else []
    )
    data["api_id"] = str(data.get("api_id") or "")
    data["api_hash"] = data.get("api_hash") or ""
    data["out_dir"] = data.get("out_dir") or default_out_dir()
    data["timezone"] = data.get("timezone") or DEFAULT_TZ

    # перенос ключей из старой версии (одна учётная запись) в первый профиль
    migrated = False
    if not data["profiles"] and data["api_id"].isdigit() and data["api_hash"]:
        data["profiles"].append(
            {
                "id": LEGACY_PROFILE_ID,
                "name": "Основной",
                "api_id": data["api_id"],
                "api_hash": data["api_hash"],
                "tg_user_id": None,
                "out_dir": "",
                "session": session_path(),  # старый файл входа остаётся рабочим
            }
        )
        data["api_id"] = ""
        data["api_hash"] = ""
        migrated = True

    if migrated:
        save_settings(data)

    if use_env:
        data["api_id"] = data["api_id"] or str(getenv("TG_API_ID") or "")
        data["api_hash"] = data["api_hash"] or getenv("TG_API_HASH") or ""
    return data


def save_settings(data):
    path = settings_file()
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        dump(data, f, ensure_ascii=False, indent=2)
    replace_file(tmp, path)
