#!/usr/bin/env python3
"""AION AI MP3 Box Configuration Wizard."""

import argparse
import json
import os
from pathlib import Path
import pwd
import sys
import tempfile

from aion_ui import LANGUAGES, options, screen, set_language, tr

DEFAULT_CONFIG = Path(
    "/var/lib/aion-audio/config.json"
)

DEFAULTS = {
    "schema_version": 1,
    "setup_complete": False,
    "language": "zh_TW",
    "audio_backend": "alsa",
    "music_directory": "/mnt/music",
    "device_location": "",
}


def config_path():
    override = os.environ.get("AION_CONFIG_PATH")
    return Path(override) if override else DEFAULT_CONFIG


def load_config():
    path = config_path()
    if not path.exists():
        return DEFAULTS.copy()

    with path.open(encoding="utf-8") as stream:
        data = json.load(stream)

    if not isinstance(data, dict):
        raise ValueError("Invalid configuration format")

    config = DEFAULTS.copy()
    config.update(data)
    return config


def save_config(config):
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary = tempfile.mkstemp(
        prefix=".aion-config-",
        dir=str(path.parent),
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(
                config,
                stream,
                ensure_ascii=False,
                indent=2,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

        if os.geteuid() == 0 and path == DEFAULT_CONFIG:
            account = pwd.getpwnam("aion-audio")
            os.chown(temporary, 0, account.pw_gid)
            os.chmod(temporary, 0o640)
        else:
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)

        directory_fd = os.open(
            str(path.parent), os.O_RDONLY
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def choose(prompt, choices, default, invalid=None):
    while True:
        options(choices.items())

        answer = input(
            f"{prompt} [{default}]: "
        ).strip()

        if not answer:
            return default

        if answer in choices:
            return answer

        print(invalid or tr("Invalid selection.", "選項無效。"))


def select_language(config):
    screen("Language · 語言 · 语言 · 言語 · 언어")
    choices = {key: name for key, (_, name) in LANGUAGES.items()}
    default = next(
        (key for key, (code, _) in LANGUAGES.items() if code == config["language"]),
        "1",
    )
    language = choose("1–5", choices, default, invalid="1–5")
    config["language"] = LANGUAGES[language][0]
    set_language(config["language"])


def select_location(config):
    current = config["device_location"]
    print(tr("Enter a city, region, and country, for example Taipei, Taiwan.",
             "請輸入城市、地區與國家，例如台北，台灣。"))
    print(tr("Press Enter to keep the current location or skip. Enter - to clear it.",
             "按 Enter 保留目前地點或略過。輸入 - 可清除地點。"))
    while True:
        value = input(f"{tr('Device location', '設備地點')} [{current}]: ").strip()
        if not value:
            return
        if len(value) <= 120 and value.isprintable():
            config["device_location"] = "" if value == "-" else value
            return
        print(tr("Enter a location of up to 120 characters.", "設備地點最多可輸入 120 個字元。"))


def wizard(config):
    select_language(config)

    screen(tr("Audio output", "音訊輸出"), tr("Step 1 of 4", "步驟 1／4"))
    outputs = {
        "1": tr("ALSA · AIY Voice HAT", "ALSA · AIY Voice HAT 本機輸出"),
        "2": tr("PulseAudio · Bluetooth", "PulseAudio · 藍牙輸出"),
    }
    audio = choose(
        tr("Audio output", "音訊輸出"),
        outputs,
        "2" if config["audio_backend"] == "pulse" else "1",
    )
    config["audio_backend"] = "alsa" if audio == "1" else "pulse"

    screen(tr("Music directory", "音樂目錄"), tr("Step 2 of 4", "步驟 2／4"))
    print(tr("Press Enter to keep the current directory.", "按 Enter 保留目前的目錄。"))
    while True:
        directory = input(
            f"{tr('Directory', '目錄')} [{config['music_directory']}]: "
        ).strip()
        if not directory:
            break
        path = Path(directory).expanduser()
        if path.is_absolute():
            config["music_directory"] = str(path)
            break
        print(tr("Enter an absolute path.", "請輸入絕對路徑。"))

    screen(tr("Device location", "設備地點"), tr("Step 3 of 4", "步驟 3／4"))
    select_location(config)

    screen(tr("Review settings", "確認設定"), tr("Step 4 of 4", "步驟 4／4"))
    print(f"  {tr('Audio output', '音訊輸出')} · {outputs[audio]}")
    print(f"  {tr('Music directory', '音樂目錄')} · {config['music_directory']}")
    location = config["device_location"] or tr("Not set", "未設定")
    print(f"  {tr('Device location', '設備地點')} · {location}")
    print()
    print(tr(
        "Wi-Fi and Bluetooth are available from the main menu.",
        "可從主選單設定 Wi-Fi 與藍牙。",
    ))
    confirmation = choose(
        tr("Save settings?", "要儲存設定嗎？"),
        {"1": tr("Save", "儲存"), "0": tr("Cancel", "取消")},
        "1",
    )
    if confirmation != "1":
        print(tr("Settings were not saved.", "設定未儲存。"))
        return False

    config["setup_complete"] = True
    save_config(config)
    print(tr("Settings saved.", "設定已儲存。"))
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--location",
        action="store_true",
        help="Change the device location",
    )
    parser.add_argument(
        "--language",
        action="store_true",
        help="Change the interface language",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run wizard even if setup is complete",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Display configuration status",
    )
    args = parser.parse_args()

    try:
        config = load_config()
        set_language(config["language"])

        if args.status:
            print(json.dumps(
                config,
                ensure_ascii=False,
                indent=2,
            ))
            return 0

        if args.language:
            select_language(config)
            save_config(config)
            print(tr("Settings saved.", "設定已儲存。"))
            return 0

        if args.location:
            screen(tr("Device location", "設備地點"))
            select_location(config)
            save_config(config)
            print(tr("Settings saved.", "設定已儲存。"))
            return 0

        if config["setup_complete"] and not args.force:
            print(tr("AION setup is already complete.", "AION 已完成設定。"))
            return 0

        return 0 if wizard(config) else 1

    except (OSError, ValueError, KeyError):
        print(tr("Unable to read or save settings.", "無法讀取或儲存設定。"), file=sys.stderr)
        return 1

    except (KeyboardInterrupt, EOFError):
        print("\n" + tr("Setup cancelled.", "已取消設定。"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
