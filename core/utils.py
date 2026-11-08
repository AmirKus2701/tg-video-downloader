from os.path import join
from re import sub

SKIP_PHRASES = (
    "due to copyright infringement",  # This message couldn't be displayed ... due to copyright infringement.
)

# Как показывать пустую строку между абзацами в .md:
#   "markdown" - обычная пустая строка (правильно в VS Code, Obsidian, GitHub)
#   "visible"  - между абзацами добавляется строка с неразрывным пробелом: промежуток виден даже там, где просмотрщик (например, Блокнот) схлопывает пустые строки
BLANK_LINES = "visible"


def parse_channel(value):
    value = str(value).strip()
    return int(value) if value.lstrip("-").isdigit() else value


def safe_name(text, max_len=60):
    text = sub(r'[\\/:*?"<>|\n\r]+', " ", text or "").strip()
    return text[:max_len] or "channel"


def channel_folder(out_dir, entity):
    return join(out_dir, safe_name(getattr(entity, "title", None) or str(entity.id)))


def is_skipped(msg):
    """True для сообщений, которые не нужно сохранять."""
    text = (msg.raw_text or "").replace("’", "'").lower()
    return any(phrase in text for phrase in SKIP_PHRASES)


def make_title(msg, max_len=100):
    """Заголовок: первая непустая строка чистого текста, без markdown."""
    for line in (msg.raw_text or "").splitlines():
        if line.strip():
            return line.strip()[:max_len]
    return ""


def format_post(text):
    """Текст поста для .md, строка в строку как в Telegram.
    Пустая строка в Telegram остаётся пустой строкой (граница абзацев), а одиночный перенос строки
    сохраняется жёстким переносом Markdown: два пробела в конце строки (в обычном тексте не видны)."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u2028", "\n").replace("\u2029", "\n\n")
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip("\n")
    text = sub(r"\n{3,}", "\n\n", text)  # несколько пустых строк подряд сводим к одной

    paragraphs = ["  \n".join(paragraph.split("\n")) for paragraph in text.split("\n\n")]
    spacer = "\n\n\u00a0\n\n" if BLANK_LINES == "visible" else "\n\n"
    return spacer.join(paragraphs) + "\n"