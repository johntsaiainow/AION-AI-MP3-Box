#!/usr/bin/env python3
"""AION AI MP3 Box v0.4.0 - TUI prototype."""

import curses
import locale

locale.setlocale(locale.LC_ALL, "")

MAIN = [
    "Music Library",
    "Playlists",
    "Now Playing",
    "Hardware & System",
    "Exit",
]

SYSTEM = [
    "Wi-Fi & Network",
    "Bluetooth Devices",
    "Storage & Music Partition",
    "Music Library Import",
    "Audio Output",
    "System Information",
    "Configuration Wizard",
]

BLUETOOTH = [
    "Bluetooth Status",
    "Scan Devices",
    "Paired Devices",
    "Connect Device",
    "Audio Output",
]


def draw(stdscr, title, items, selected, message):
    stdscr.erase()
    height, width = stdscr.getmaxyx()

    if height < 15 or width < 45:
        stdscr.addstr(0, 0, "Terminal too small (min 45x15)")
        stdscr.refresh()
        return

    stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
    stdscr.addstr(1, 3, "AION  ♪")
    stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)

    stdscr.addstr(1, width - 21, "AI MP3 BOX v0.4.0")
    stdscr.hline(3, 2, curses.ACS_HLINE, width - 4)

    stdscr.attron(curses.color_pair(1))
    stdscr.addstr(5, 4, title)
    stdscr.attroff(curses.color_pair(1))

    for index, item in enumerate(items):
        y = 7 + index

        if y >= height - 4:
            break

        label = f"  {item}"

        if index == selected:
            stdscr.attron(curses.color_pair(2) | curses.A_BOLD)
            stdscr.addstr(y, 4, label.ljust(width - 8))
            stdscr.attroff(curses.color_pair(2) | curses.A_BOLD)
        else:
            stdscr.addstr(y, 4, label[:width - 8])

    stdscr.hline(height - 4, 2, curses.ACS_HLINE, width - 4)
    stdscr.addstr(height - 3, 3, message[:width - 6])
    stdscr.addstr(
        height - 2, 3,
        "UP/DOWN Navigate | Enter Select | Esc Back"[:width - 6]
    )

    stdscr.refresh()


def main(stdscr):
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()

    curses.init_pair(1, curses.COLOR_CYAN, -1)
    curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLUE)

    stdscr.keypad(True)

    screen = "main"
    selected = 0
    message = "Ready"

    while True:
        if screen == "main":
            title, items = "MAIN MENU", MAIN
        elif screen == "system":
            title, items = "HARDWARE & SYSTEM", SYSTEM
        else:
            title, items = "BLUETOOTH MANAGEMENT", BLUETOOTH

        draw(stdscr, title, items, selected, message)

        key = stdscr.getch()

        if key == curses.KEY_UP:
            selected = (selected - 1) % len(items)

        elif key == curses.KEY_DOWN:
            selected = (selected + 1) % len(items)

        elif key in (27, curses.KEY_BACKSPACE):
            if screen == "main":
                return
            if screen == "bluetooth":
                screen = "system"
            else:
                screen = "main"
            selected = 0
            message = "Ready"

        elif key in (10, 13, curses.KEY_ENTER):
            choice = items[selected]

            if screen == "main":
                if choice == "Exit":
                    return
                if choice == "Hardware & System":
                    screen = "system"
                    selected = 0
                    message = "System management"
                else:
                    message = f"{choice}: prototype only"

            elif screen == "system":
                if choice == "Bluetooth Devices":
                    screen = "bluetooth"
                    selected = 0
                    message = "Bluetooth management"
                else:
                    message = f"{choice}: prototype only"

            else:
                message = f"{choice}: prototype only"


if __name__ == "__main__":
    curses.wrapper(main)
