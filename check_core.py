from pathlib import Path

# файл: (что должно быть внутри, чего быть не должно)
CHECKS = {
    "core/meta.py": (["def load_meta", "def save_meta"], ["from core.meta", "import core"]),
    "core/media.py": (["def save_media", "format_post", "from core.meta import"], ["def load_meta"]),
    "core/posts.py": (["def save_posts", "format_post"], ["def save_media"]),
    "core/utils.py": (["def format_post", "def make_title", "def safe_name"], []),
    "core/navigator.py": (["def build_navigator"], ["def save_media"]),
    "core/pipeline.py": (["def download_channel"], ["def save_media("]),
    "core/settings.py": (["def profile_out_dir", "def load_settings"], []),
    "core/tz.py": (["def to_local"], []),
    "core/xlsx.py": (["def save_protected"], []),
}

problems = 0
for name, (need, forbid) in CHECKS.items():
    path = Path(name)
    if not path.exists():
        print(f"НЕТ ФАЙЛА   {name}")
        problems += 1
        continue

    text = path.read_text(encoding="utf-8")
    missing = [item for item in need if item not in text]
    stale = [item for item in forbid if item in text]
    if missing or stale:
        problems += 1
        print(f"НЕВЕРНЫЙ    {name}  (нет: {missing or '-'}; лишнее: {stale or '-'})")
    else:
        print(f"ок          {name}")

print("\nВсё в порядке." if not problems else f"\nПроблемных файлов: {problems}")