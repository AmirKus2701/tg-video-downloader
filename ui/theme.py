from string import Template

PALETTES = {
    "dark": {
        "bg": "#17212b",
        "panel": "#0e1621",
        "card": "#1f2b38",
        "field": "#242f3d",
        "border": "#2b3a4a",
        "hover": "#202b36",
        "selected": "#2b5278",
        "on_selected": "#ffffff",
        "text": "#f5f5f5",
        "muted": "#6d7f8f",
        "accent": "#5288c1",
        "accent_hover": "#6498d2",
        "danger": "#ec6a6a",
        "qr_bg": "#ffffff",
        "qr_fg": "#0e1621",
    },
    "light": {
        "bg": "#e7ebf0",
        "panel": "#ffffff",
        "card": "#ffffff",
        "field": "#f1f3f5",
        "border": "#dfe3e7",
        "hover": "#f3f5f7",
        "selected": "#3390ec",
        "on_selected": "#ffffff",
        "text": "#222222",
        "muted": "#8a96a3",
        "accent": "#3390ec",
        "accent_hover": "#2a7fd1",
        "danger": "#e53935",
        "qr_bg": "#ffffff",
        "qr_fg": "#0e1621",
    },
}

# цвета аватарок, как в Telegram
AVATAR_COLORS = ("#e17076", "#faa774", "#a695e7", "#7bc862", "#6ec9cb", "#65aadd", "#ee7aae")

_QSS = Template("""
QWidget { color: $text; font-family: "Segoe UI", "Inter", "Roboto", sans-serif; font-size: 14px; }
QMainWindow, QDialog { background: $bg; }
QLabel { background: transparent; }

QLabel[role="title"] { font-size: 26px; font-weight: 600; }
QLabel[role="h2"] { font-size: 20px; font-weight: 600; }
QLabel[role="value"] { font-size: 30px; font-weight: 600; }
QLabel[role="muted"] { color: $muted; }
QLabel[role="error"] { color: $danger; }
QLabel[role="step"] { background: $accent; color: #ffffff; border-radius: 13px; font-weight: 600; }

QFrame#sidebar { background: $panel; border-right: 1px solid $border; }
QFrame#card { background: $card; border-radius: 16px; }
QFrame#statCard { background: $card; border-radius: 14px; }
QFrame#divider { background: $border; min-height: 1px; max-height: 1px; }

QLineEdit { background: $field; border: 1px solid $border; border-radius: 10px; padding: 10px 12px; selection-background-color: $accent; }
QLineEdit:focus { border: 1px solid $accent; }

QPushButton { background: $field; border: none; border-radius: 10px; padding: 10px 20px; }
QPushButton:hover { background: $hover; }
QPushButton[role="primary"] { background: $accent; color: #ffffff; font-weight: 600; }
QPushButton[role="primary"]:hover { background: $accent_hover; }
QPushButton[role="flat"] { background: transparent; color: $accent; padding: 8px 12px; }
QPushButton[role="flat"]:hover { background: $hover; }
QPushButton[role="danger"] { background: transparent; color: $danger; border: 1px solid $danger; }
QPushButton[role="danger"]:hover { background: $hover; }
QPushButton:disabled { color: $muted; }
QPushButton[role="primary"]:disabled { background: $border; color: $muted; }
QPushButton[role="flat"]:disabled { color: $muted; }
QPushButton[role="danger"]:disabled { color: $muted; border: 1px solid $border; }

QProgressBar { background: $border; border: none; border-radius: 2px; min-height: 4px; max-height: 4px; }
QProgressBar::chunk { background: $accent; border-radius: 2px; }
QProgressBar[role="download"] { border-radius: 4px; min-height: 8px; max-height: 8px; }
QProgressBar[role="download"]::chunk { border-radius: 4px; }

QListWidget { background: transparent; border: none; outline: none; }

QComboBox { background: $field; border: 1px solid $border; border-radius: 10px; padding: 8px 12px; }
QComboBox:disabled { color: $muted; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: $card; border: 1px solid $border; selection-background-color: $selected; selection-color: #ffffff; outline: none; }

QPlainTextEdit { background: $field; border: 1px solid $border; border-radius: 10px; padding: 8px; selection-background-color: $accent; font-family: "Cascadia Mono", "Consolas", monospace; font-size: 12px; }

QToolTip { background: $card; color: $text; border: 1px solid $border; padding: 4px 8px; }

QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
""")

_current = "dark"


def build_qss(colors):
    return _QSS.safe_substitute(colors)


def apply_theme(app, name):
    global _current
    _current = name if name in PALETTES else "dark"
    app.setStyleSheet(build_qss(PALETTES[_current]))


def palette():
    return PALETTES[_current]


def avatar_color(key):
    return AVATAR_COLORS[abs(int(key)) % len(AVATAR_COLORS)]