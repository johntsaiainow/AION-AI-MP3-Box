#!/usr/bin/env python3
"""AION AI MP3 Box Configuration Wizard."""

import argparse
import getpass
import json
import os
from pathlib import Path
import pwd
import re
import sys
import tempfile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aion_local_info import DEFAULT_TIME_ZONE, POSTAL_CODE, TRAFFIC_KEY_PATH, US_ZIP, coordinate_pair, location_label, weather_place_name
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
    "time_zone": DEFAULT_TIME_ZONE,
    "daylight_saving": True,
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


def select_time_zone(config):
    screen(tr("Time zone and daylight saving", "時區與日光節約時間"))
    zones = {
        "1": "America/Los_Angeles",
        "2": "America/Denver",
        "3": "America/Chicago",
        "4": "America/New_York",
        "5": "Asia/Taipei",
        "6": "Asia/Tokyo",
        "7": "UTC",
    }
    current = config["time_zone"]
    picked = choose(tr("Select time zone", "選擇時區"), {
        **zones,
        "8": tr("Enter an IANA time zone", "輸入 IANA 時區"),
        "0": tr("Keep current time zone", "保留目前時區") + f" ({current})",
    }, "0")
    if picked in zones:
        config["time_zone"] = zones[picked]
    elif picked == "8":
        while True:
            name = input(tr("IANA time zone (Enter to keep current): ", "IANA 時區（Enter 保留）：")).strip()
            if not name:
                break
            try:
                ZoneInfo(name)
            except (ValueError, ZoneInfoNotFoundError):
                print(tr("Time zone not found.", "找不到這個時區。"))
            else:
                config["time_zone"] = name
                break
    mode = choose(tr("Daylight saving", "日光節約時間"), {
        "1": tr("Automatic (follow time-zone rules)", "自動（依時區規則切換）"),
        "2": tr("Off (standard time year-round)", "關閉（全年使用標準時間）"),
    }, "1" if config["daylight_saving"] is not False else "2")
    config["daylight_saving"] = mode == "1"


def select_location(config):
    current = location_label(config["device_location"])
    mode = choose(tr("Search location by", "地點查詢方式"), {
        "1": tr("City and region", "城市與地區"),
        "2": tr("Postal code / ZIP code", "郵遞區號／ZIP code"),
        "3": tr("Latitude and longitude", "緯度與經度"),
        "4": tr("Clear saved location", "清除已儲存地點"),
        "0": tr("Keep current location", "保留目前地點") + (f" ({current})" if current else ""),
    }, "0")
    if mode == "0":
        return
    if mode == "4":
        config["device_location"] = ""
        return
    if mode == "3":
        while True:
            point = input(tr("Latitude and longitude (Enter to cancel): ",
                             "緯度與經度（Enter 取消）：")).strip()
            if not point:
                return
            try:
                if coordinate_pair(point) is not None:
                    config["device_location"] = point
                    return
            except ValueError:
                pass
            print(tr("Enter valid coordinates, e.g. 25.03, 121.56.", "請輸入有效經緯度，例如 25.03, 121.56。"))

    country = ""
    while True:
        if mode == "2":
            prompt = tr("Country code, e.g. US or TW (Enter to cancel): ",
                        "國家代碼，例如 US 或 TW（Enter 取消）：")
        else:
            prompt = tr("Country code, e.g. US or TW (Enter to skip): ",
                        "國家代碼，例如 US 或 TW（Enter 略過）：")
        country = input(prompt).strip().upper()
        if not country:
            if mode == "2":
                return
            break
        if len(country) == 2 and country.isascii() and country.isalpha():
            break
        print(tr("Enter a two-letter country code.", "請輸入兩個英文字母的國家代碼。"))

    if mode == "2":
        while True:
            postal_code = input(tr("Postal code / ZIP code (Enter to cancel): ",
                                   "郵遞區號／ZIP code（Enter 取消）：")).strip().upper()
            if not postal_code:
                return
            valid = US_ZIP.fullmatch(postal_code) if country == "US" else POSTAL_CODE.fullmatch(postal_code)
            if valid:
                config["device_location"] = {"postal_code": postal_code, "country": country}
                return
            print(tr("Invalid postal code.", "郵遞區號格式無效。"))

    print(tr("Enter only the city and region for weather. Save street addresses under Commute addresses.",
             "天氣只填城市與地區。門牌地址請存到「通勤地址」。"))
    while True:
        city = input(tr("City name, e.g. Los Angeles (Enter to cancel): ",
                        "城市名，例如 Los Angeles（Enter 取消）：")).strip()
        if not city:
            return
        if weather_place_name(city):
            if not US_ZIP.fullmatch(city):
                break
            print(tr("Choose Postal code / ZIP code for a ZIP code.", "ZIP code 請使用郵遞區號選項。"))
            continue
        print(tr("Enter only the city name.", "請只輸入城市名。"))

    while True:
        region = input(tr("State or region (Enter to skip): ", "州／地區（Enter 略過）：")).strip()
        if not region or weather_place_name(region):
            break
        print(tr("Enter only the state or region.", "請只輸入州或地區名稱。"))

    config["device_location"] = {"city": city, "region": region, "country": country}


def set_traffic_key():
    if not sys.stdin.isatty():
        print(tr("Use an interactive terminal to set the key.", "請在互動式主控台設定金鑰。"), file=sys.stderr)
        return 1
    configured = TRAFFIC_KEY_PATH.is_file() or bool(os.environ.get("TOMTOM_API_KEY", "").strip())
    screen(tr("TomTom traffic key", "TomTom 路況金鑰"),
           tr("Configured", "已設定") if configured else tr("Not set", "未設定"))
    print(tr("Press Enter to keep the saved key. Enter - to remove the local key.",
             "按 Enter 保留金鑰。輸入 - 可移除本機金鑰。"))
    if os.environ.get("TOMTOM_API_KEY", "").strip():
        print(tr("TOMTOM_API_KEY takes precedence over the local key.",
                 "目前優先使用 TOMTOM_API_KEY 環境變數。"))
    while True:
        key = getpass.getpass(tr("TomTom API key: ", "TomTom API 金鑰：")).strip()
        if not key:
            return 0
        if key == "-":
            TRAFFIC_KEY_PATH.unlink(missing_ok=True)
            return 0
        if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", key):
            break
        print(tr("Invalid key format. Paste the key from TomTom.", "金鑰格式無效，請貼上 TomTom 提供的金鑰。"))

    TRAFFIC_KEY_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".tomtom-", dir=TRAFFIC_KEY_PATH.parent)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as stream:
            stream.write(key + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, TRAFFIC_KEY_PATH)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return 0


def select_commute(config):
    screen(tr("Commute addresses", "通勤地址"))
    print(tr("TomTom uses these addresses to calculate both driving directions. Enter - to clear a field.",
             "TomTom 會使用這兩個地址計算雙向開車路況。輸入 - 可清除該欄。"))
    saved = config.get("commute")
    saved = saved.copy() if isinstance(saved, dict) else {}
    for field, title in (("home", tr("Home address", "住家地址")), ("work", tr("Work address", "公司地址"))):
        while True:
            status = tr("saved", "已設定") if saved.get(field) else tr("not set", "未設定")
            value = input(f"{title} ({status}, Enter) › ").strip()
            if not value:
                break
            if value == "-" or len(value) <= 250 and value.isprintable():
                saved[field] = "" if value == "-" else value
                break
            print(tr("Enter a complete address up to 250 characters.", "請輸入 250 字元以內的完整地址。"))
    config["commute"] = saved


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
    location = location_label(config["device_location"]) or tr("Not set", "未設定")
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
    parser.add_argument("--commute", action="store_true", help="Set home and work addresses")
    parser.add_argument("--traffic-key", action="store_true", help="Set the TomTom traffic API key")
    parser.add_argument("--timezone", action="store_true", help="Change time zone and daylight saving")
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

        if args.traffic_key:
            return set_traffic_key()

        if args.commute:
            select_commute(config)
            save_config(config)
            print(tr("Settings saved.", "設定已儲存。"))
            return 0

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

        if args.timezone:
            select_time_zone(config)
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
