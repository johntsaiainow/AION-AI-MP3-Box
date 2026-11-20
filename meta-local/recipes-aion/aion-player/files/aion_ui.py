"""Shared presentation for the AION terminal interface."""

import json
import os
from pathlib import Path
import re
import select
import shutil
import sys
import unicodedata

from aion_translations import LANGUAGE_COLUMNS, TRANSLATIONS

PRODUCT = "AIY Box Rebirth"
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


def cell_width(char):
    if not char.isprintable() or unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def fit_cells(text, width):
    """Clip and pad text using the terminal width of CJK characters."""
    result = []
    cells = 0
    for char in text:
        if not char.isprintable():
            continue
        size = cell_width(char)
        if cells + size > width:
            break
        result.append(char)
        cells += size
    return "".join(result) + " " * (width - cells)


def menu_lines(text, width):
    text = "".join(char for char in text if char.isprintable())
    first = fit_cells(text, width).rstrip()
    rest = text[len(first):].lstrip()
    if not rest:
        return (first,)
    second = fit_cells(rest, width).rstrip()
    if rest[len(second):].strip():
        second = fit_cells(rest, width - 1).rstrip() + "…"
    return first, second


def dashboard(title, subtitle, entries, group_break=None, status=None, information=None):
    columns, rows = shutil.get_terminal_size((80, 24))
    if (not sys.stdin.isatty() or not sys.stdout.isatty()
            or os.environ.get("TERM", "dumb") == "dumb" or columns < 34 or rows < 18):
        screen(title, subtitle)
        options(entries)
        if status:
            print(status)
        return selection()

    side_column = columns // 4 + 3 if information and columns >= 66 else 0
    side_width = columns - side_column if side_column else 0
    left_width = columns // 4 - 2 if side_width else columns - 4
    capacity = rows - 9
    pages = [[]]
    used = 0
    for key, label in entries:
        prefix = max(4, len(str(key)) + 1)
        lines = menu_lines(label, left_width - prefix)
        cost = len(lines) + (key == group_break)
        if used + cost > capacity:
            pages.append([])
            used = 0
        pages[-1].append((key, prefix, lines))
        used += cost
    page = 0

    def update_information():
        panel = information(side_width, rows - 6)
        frame = ["\0337"]
        for row, (text, color) in enumerate(panel, 5):
            if color is None:
                width = sum(map(cell_width, re.sub(r"\x1b\[[0-9;]*m", "", text)))
                blank = max(0, side_width - width)
                art = " " * (blank // 2) + text + "\033[0m" + " " * (blank - blank // 2)
                frame.append(f"\033[{row};{side_column}H{art}")
                continue
            width = min(side_width, sum(map(cell_width, text)))
            blank = side_width - width
            centered = " " * (blank // 2) + fit_cells(text, width) + " " * (blank - blank // 2)
            frame.append(f"\033[{row};{side_column}H{accent(centered, color)}")
        frame.append("\0338")
        sys.stdout.write("".join(frame))
        sys.stdout.flush()

    try:
        while True:
            frame = ["\033[2J\033[H"]
            def place(row, column, text):
                frame.append(f"\033[{row};{column}H{text}")

            place(1, 1, accent(fit_cells("  " + PRODUCT, columns - 1), "1;30;46"))
            place(3, 3, accent(fit_cells(title, left_width), "1"))
            place(4, 3, accent(fit_cells(subtitle or "", left_width), "2"))
            place(5, 3, accent("─" * left_width, "36"))
            if side_width:
                for row in range(3, rows - 1):
                    place(row, side_column - 2, accent("│", "36"))
                place(3, side_column, accent(tr("Local information", "本地資訊"), "1"))

            row = 6
            for key, prefix, lines in pages[page]:
                if key == group_break:
                    place(row, 3, accent("─" * left_width, "36"))
                    row += 1
                badge = accent(f"{key:>{prefix - 1}}", "1;93")
                place(row, 3, f"{badge} {lines[0]}")
                row += 1
                if len(lines) > 1:
                    place(row, 3 + prefix, lines[1])
                    row += 1

            if len(pages) > 1:
                place(rows - 3, 3, fit_cells(f"{page + 1}/{len(pages)}  P ◀ N ▶", left_width))
            if status:
                place(rows - 2, 3, accent(fit_cells(status, left_width), "1;33"))
            prompt = tr("Select", "選擇") + " › "
            place(rows - 1, 3, accent(fit_cells(prompt, left_width).rstrip()) + " ")
            sys.stdout.write("".join(frame))
            sys.stdout.flush()

            if side_width:
                while True:
                    update_information()
                    if select.select([sys.stdin], [], [], 1)[0]:
                        break

            value = input().strip().lower()
            if len(pages) > 1 and value in ("p", "n"):
                page = min(len(pages) - 1, max(0, page + (1 if value == "n" else -1)))
                continue
            return value if value.isascii() and value.replace("-", "").isalnum() else ""
    finally:
        print("\033[2J\033[H", end="", flush=True)


def playback_cover_size(columns, rows):
    if columns >= 68 and rows >= 18:
        return min(34, columns // 2 - 5), min(18, rows - 7)
    return min(24, columns - 6), min(7, max(1, rows - 14))


def playback_frame(columns, rows, view, lyrics=None, first_line=0):
    """Build independent terminal rows so playback can redraw only what changed."""
    frame = [[] for _ in range(rows)]
    width = columns - 4

    def place(row, column, text, style=None, limit=None):
        if 1 <= row <= rows and 1 <= column < columns:
            if limit is not None:
                text = fit_cells(text, limit).rstrip()
            if style:
                text = accent(text, style)
            frame[row - 1].append(f"\033[{row};{column}H{text}")

    heading = tr("Now playing", "正在播放") if lyrics is None else tr("Lyrics", "歌詞")
    place(1, 1, fit_cells(f"  {PRODUCT}   /   {heading}", columns - 1), "1;30;46")

    if lyrics is not None:
        place(3, 3, view["title"], "1;37", width)
        for row, line in enumerate(lyrics[first_line:first_line + rows - 6], 5):
            place(row, 3, line, "37", width)
        place(rows - 1, 3, tr("J/K Scroll · L Back · Q Stop", "J/K 捲動 · L 返回 · Q 停止"), "2", width)
        return tuple("".join(row) for row in frame)

    wide = view["music"] and columns >= 68 and rows >= 18
    art_width, art_height = playback_cover_size(columns, rows)
    detail_column = art_width + 8 if wide else 3
    detail_width = columns - detail_column - 1
    if wide:
        for row in range(3, rows - 3):
            place(row, detail_column - 3, "│", "34")
    art_row = 4 if wide else 8
    for row, line in enumerate(view["cover"][:art_height], art_row):
        if not wide and row >= rows - 6:
            break
        place(row, 3, line + "\033[0m")
    if wide and not view["cover"]:
        place(art_row + 1, 3, tr("Album cover", "專輯封面"), "1;36", art_width)
        place(art_row + 3, 3, view["cover_status"], "2", art_width)

    for row, line in enumerate(menu_lines(view["title"], detail_width), 3):
        place(row, detail_column, line, "1;37", detail_width)
    place(5, detail_column, view["artist_album"], "2", detail_width)
    place(6, detail_column, view["state"], "1;36", detail_width)
    progress_row = 8 if wide else rows - 6
    if view["progress"]:
        place(progress_row, detail_column, view["progress"], "36", detail_width)
    if wide or not view["music"]:
        place(10, detail_column, view["audio"], "37", detail_width)
        if view["spectrum"]:
            place(11, detail_column, view["spectrum"], "1;36", detail_width)
    lyric_row = min(15, rows - 6) if wide else rows - 4
    if view["lyric"]:
        lyric_lines = menu_lines(view["lyric"], detail_width)
        for row, line in enumerate(lyric_lines if wide else lyric_lines[:1], lyric_row):
            place(row, detail_column, line, "1;33", detail_width)
    place(rows - 3, 3, view["notice"], "1;33", width)
    place(rows - 2, 3, tr("P Pause · +/− Volume · M Mute · Q Stop", "P 暫停 · +/− 音量 · M 靜音 · Q 停止"), "2", width)
    keys = tr("1–6 EQ · V Volume", "1–6 音色 · V 音量")
    if view["music"]:
        keys += tr(" · L Lyrics", " · L 歌詞")
    place(rows - 1, 3, keys, "2", width)
    return tuple("".join(row) for row in frame)
