from datetime import timezone
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TZ = "Asia/Almaty"  # Астана и Алматы живут по одному времени


@lru_cache(maxsize=None)
def load_tz(name):
    """Часовой пояс по имени или None, если его нет в системе (в Windows нужен пакет tzdata)."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def to_local(date, name):
    """В 0_meta.json даты хранятся в UTC без пояса. Переводим в нужный часовой пояс
    и отбрасываем пояс, потому что Excel не принимает даты с часовым поясом."""
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    tz = load_tz(name)
    local = date.astimezone(tz) if tz else date.astimezone()  # без tz: часовой пояс компьютера
    return local.replace(tzinfo=None)