"""Shared presentation for the AION terminal interface."""

import json
import os
from pathlib import Path
import shutil
import sys
import unicodedata

from aion_translations import LANGUAGE_COLUMNS, TRANSLATIONS

PRODUCT = "AION AI MP3 Box"
LANGUAGES = {
    "1": ("zh_TW", "繁體中文"),
    "2": ("en_US", "English"),
    "3": ("zh_CN", "简体中文"),
    "4": ("ja_JP", "日本語"),
    "5": ("ko_KR", "한국어"),
}
_language = "zh_TW"


def set_language(language):
    global _language
    _language = language if any(language == code for code, _ in LANGUAGES.values()) else "zh_TW"


def use_saved_language():
    path = Path(os.environ.get("AION_CONFIG_PATH", "/var/lib/aion-audio/config.json"))
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        config = {}
    set_language(config.get("language") if isinstance(config, dict) else None)


def tr(english, chinese):
    if _language == "en_US":
        return english
    key = chinese.strip()
    if _language == "zh_TW":
        translated = key
    else:
        text = TRANSLATIONS.get(key)
        if text is None:
            return english
        translated = text[LANGUAGE_COLUMNS[_language]]
    leading = english[:len(english) - len(english.lstrip())]
    trailing = english[len(english.rstrip()):]
    return leading + translated + trailing


def accent(text, code="1;36"):
    if sys.stdout.isatty() and os.environ.get("TERM", "dumb") != "dumb" and "NO_COLOR" not in os.environ:
        return f"\033[{code}m{text}\033[0m"
    return text


def screen(title, subtitle=None):
    width = min(52, shutil.get_terminal_size((52, 24)).columns)
    print()
    print(accent(PRODUCT, "1;37"))
    print(accent(title))
    if subtitle:
        print(subtitle)
    print(accent("─" * width))


def options(items):
    for key, label in items:
        print(f"  {accent(str(key).rjust(2), '1;93')}  {label}")


def selection():
    value = input(f"\n{tr('Selection (letters or numbers)', '選項（字母或數字）')} › ").strip()
    return value if value.isascii() and value.replace("-", "").isalnum() else ""


def fit_cells(text, width):
    """Clip and pad text using the terminal width of CJK characters."""
    result = []
    cells = 0
    for char in text:
        if not char.isprintable():
            continue
        size = 0 if unicodedata.combining(char) else (
            2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
        )
        if cells + size > width:
            break
        result.append(char)
        cells += size
    return "".join(result) + " " * (width - cells)


def dashboard(title, library, entries, group_break, status=None):
    columns, rows = shutil.get_terminal_size((80, 24))
    prompt = tr("Number or letter", "輸入編號或字母") + " › "
    if (not sys.stdin.isatty() or not sys.stdout.isatty()
            or os.environ.get("TERM", "dumb") == "dumb" or columns < 34 or rows < 18):
        screen(title, library)
        options(entries)
        if status:
            print(status)
        return selection()

    width = min(64, columns - 4)
    left = (columns - width) // 2 + 1
    top = max(4, (rows - len(entries) - 7) // 2)
    frame = ["\033[2J\033[H"]

    def place(row, column, text):
        frame.append(f"\033[{row};{column}H{text}")

    header = "  " + PRODUCT
    place(1, 1, accent(fit_cells(header, columns - 1), "1;30;46"))
    place(top, left, accent(title, "1"))
    place(top + 1, left, accent(fit_cells(library, width), "2"))
    place(top + 2, left, accent("─" * width, "36"))

    row = top + 3
    for key, label in entries:
        if key == group_break:
            place(row, left, accent("─" * width, "36"))
            row += 1
        badge = accent(f" {key} ", "1;93")
        place(row, left, f" {badge}  {fit_cells(label, width - 6)}")
        row += 1

    if status:
        place(rows - 2, 3, accent(fit_cells(status, columns - 4), "1;33"))
    place(rows - 1, 3, accent(prompt))
    sys.stdout.write("".join(frame))
    sys.stdout.flush()
    try:
        value = input().strip()
        return value if value.isascii() and value.replace("-", "").isalnum() else ""
    finally:
        print("\033[2J\033[H", end="", flush=True)
