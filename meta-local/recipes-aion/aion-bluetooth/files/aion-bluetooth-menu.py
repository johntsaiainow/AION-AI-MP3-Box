#!/usr/bin/env python3
"""AION Bluetooth Management v0.4.0."""

from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import types

try:
    from aion_ui import tr, use_saved_language
except ImportError:
    def tr(english, traditional):
        return english

    def use_saved_language():
        return None

backend = Path(__file__).with_name("aion-bluetooth")
if not backend.exists():
    backend = Path(__file__).with_name("aion-bluetooth.py")

bt = types.ModuleType("aion_bluetooth")
SourceFileLoader("aion_bluetooth", str(backend)).exec_module(bt)

ADDRESS_LABEL = re.compile(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}")
SCAN_SECONDS = 25


def style(text, color):
    if sys.stdout.isatty() and os.environ.get("TERM", "dumb") != "dumb" and "NO_COLOR" not in os.environ:
        return f"\033[{color}m{text}\033[0m"
    return text


def heading(title):
    width = min(48, shutil.get_terminal_size((48, 24)).columns)
    print(f"\n  {style('AION', '1;36')}  {style(title, '1')}")
    print(style("─" * width, "36"))


def row(key, label, detail=None):
    print(f"  {style(f'[{key}]', '1;93')}  {label}")
    if detail:
        print(f"       {style(detail, '2')}")


def pause():
    input(tr('\nPress Enter to continue...', '\n按 Enter 繼續…'))


def device_info(mac):
    result = bt.device_action("info", mac)
    data = {}

    for line in result.splitlines():
        if ":" in line:
            key, value = line.strip().split(":", 1)
            data[key.strip()] = value.strip()

    return data


def device_name(info, listed_name):
    for candidate in (info.get("Alias", ""), info.get("Name", ""), listed_name):
        name = "".join(char for char in candidate if char.isprintable()).strip()
        if name and not ADDRESS_LABEL.fullmatch(name):
            return name
    if info.get("Icon") == "phone":
        return tr('Phone (name unavailable)', '手機（未取得名稱）')
    return tr('Name unavailable', '未取得名稱')


def device_list(paired=False):
    kind = "paired-devices" if paired else "devices"
    rows = bt.devices(kind)

    heading(tr('Paired devices', '已配對裝置') if paired else tr('Nearby devices', '附近裝置'))

    if not rows:
        print(tr('No devices found.', '找不到裝置。'))
        if not paired:
            print(tr('Put your headphones or speaker in pairing mode.', '請讓耳機或喇叭進入配對模式。'))
        return []

    for number, (mac, name) in enumerate(rows, 1):
        try:
            info = device_info(mac)
        except bt.BluetoothError:
            info = {}

        display_name = device_name(info, name)

        connected = info.get("Connected") == "yes"
        is_paired = info.get("Paired") == "yes"

        status = (
            tr('Connected', '已連線') if connected
            else tr('Paired', '已配對') if is_paired
            else tr('Available', '可連線')
        )

        status_color = "32" if connected else "2"
        row(number, display_name, f"{style(status, status_color)} · {mac}")

    return rows


def select_device(paired=False):
    rows = device_list(paired)

    if not rows:
        return None

    answer = input(tr('\nDevice number (Enter to cancel): ', '\n裝置編號（按 Enter 取消）：')).strip()

    if not answer:
        return None

    if not answer.isdecimal():
        print(tr('Invalid selection.', '選項無效。'))
        return None

    number = int(answer)

    if not 1 <= number <= len(rows):
        print(tr('Invalid device number.', '裝置編號無效。'))
        return None

    return rows[number - 1][0]


def connect_audio_device():
    print(tr('\nPut your headphones or speaker in pairing mode.', '\n請讓耳機或喇叭進入配對模式。'))
    print(tr('Scanning for {seconds} seconds...', '掃描中，約需 {seconds} 秒…').format(seconds=SCAN_SECONDS), flush=True)
    bt.power(True)
    bt.scan(SCAN_SECONDS, transport="bredr")
    mac = select_device()
    if mac is None:
        return

    info = device_info(mac)
    if info.get("Paired") != "yes" or info.get("Bonded") != "yes":
        print(tr('\nPairing...', '\n正在配對…'), flush=True)
        bt.device_action("pair", mac)
        info = device_info(mac)
        if info.get("Paired") != "yes" or info.get("Bonded") != "yes":
            raise bt.BluetoothError(
                tr('The headset did not save the pairing. Enable pairing mode on the headset and try again.', '未儲存耳機配對。請讓耳機進入配對模式後再試。')
            )
        bt.device_action("trust", mac)
        print(tr('Pairing saved.', '已儲存配對。'))

    if info.get("Connected") != "yes":
        print(tr('\nConnecting...', '\n正在連線…'), flush=True)
        print(bt.device_action("connect", mac))
        info = device_info(mac)
    if info.get("Connected") != "yes":
        raise bt.BluetoothError(tr('The device is still disconnected.', '裝置仍未連線。'))
    print(tr('\nConnected to {name}.', '\n已連線至 {name}。').format(name=device_name(info, mac)))
    print(tr('Use Audio Output to select where music plays.', '請在音訊輸出選擇播放裝置。'))


def manage_paired_device():
    mac = select_device(paired=True)
    if mac is None:
        return

    info = device_info(mac)
    connected = info.get("Connected") == "yes"
    heading(device_name(info, mac))
    row(1, tr('Disconnect', '中斷連線') if connected else tr('Connect', '連線'))
    row(2, tr('Forget device', '取消配對'))
    row(0, tr('Back', '返回'))
    choice = input(tr('\n  Select › ', '\n  請選擇 ›')).strip()
    if choice == "1":
        print(bt.device_action("disconnect" if connected else "connect", mac))
    elif choice == "2":
        if input(tr('Type REMOVE to confirm: ', '輸入 REMOVE 確認：')).strip() == "REMOVE":
            print(bt.device_action("remove", mac))
    elif choice not in ("", "0"):
        print(tr('Invalid selection.', '選項無效。'))


def audio_sinks():
    listing = bt.sinks()
    rows = []

    for line in listing.splitlines():
        columns = line.split()

        if len(columns) >= 2:
            rows.append(columns[1])

    heading(tr('Audio output', '音訊輸出'))

    if not rows:
        print(tr('No audio outputs available.', '沒有可用的音訊輸出。'))
        return []

    default = bt.pactl("get-default-sink")
    for number, name in enumerate(rows, 1):
        label = tr('Voice HAT speaker', 'Voice HAT 喇叭') if name == "alsa_output.platform-soc_sound.stereo-fallback" else name
        row(number, label, tr('Current output', '目前輸出') if name == default else None)

    return rows


def select_audio():
    rows = audio_sinks()

    if not rows:
        return

    answer = input(tr('\nOutput number (Enter to cancel): ', '\n輸出編號（按 Enter 取消）：')).strip()

    if not answer:
        return

    if not answer.isdecimal() or not 1 <= int(answer) <= len(rows):
        print(tr('Invalid selection.', '選項無效。'))
        return

    name = rows[int(answer) - 1]

    bt.set_sink(name)
    print(tr('\nDefault audio output: {name}', '\n預設音訊輸出：{name}').format(name=name))
    print(tr('Note: existing playback streams may need restarting.', '目前的播放可能需要重新啟動。'))


def pair_phone(speakerphone=False):
    if speakerphone:
        heading(tr('Phone speakerphone', '手機免持通話'))
        print(tr('Enable phone calls for the box if your phone shows that setting.', '若手機顯示「通話音訊」選項，請為本機啟用。'))
        print(tr('Answer or place a call on your phone and select the box as the call audio output.', '請在手機上接聽或撥號，並選擇本機作為通話音訊輸出。'))
    else:
        heading(tr('Play music from a phone', '從手機播放音樂'))
        print(tr("Select the box as your phone's media output and start playback.", '將手機的媒體輸出設為本機，再開始播放。'))
    print(tr('Open Bluetooth settings on your phone and select {name}.',
             '在手機的藍牙設定中選擇 {name}。').format(name=socket.gethostname()))
    print(tr('At the Bluetooth prompt, type default-agent before starting a new pairing.', '開始新配對前，請在藍牙提示符號下輸入 default-agent。'))
    print(tr('Confirm a matching code on both devices. Type yes here if prompted.', '確認兩台裝置的配對碼相同。若出現提示，請輸入 yes。'))
    print(tr('Type exit to return. Pairing mode closes after two minutes.', '輸入 exit 返回。配對模式會在兩分鐘後關閉。'), flush=True)
    bt.phone_pairing()


def phone_sms():
    mac = select_device(paired=True)
    if mac is None:
        return
    client = Path(__file__).with_name("aion-bluetooth-sms")
    python = sys.executable or "/usr/bin/python3"
    subprocess.run(["dbus-run-session", "--", python, str(client), mac], check=False)


def bluetooth_menu():
    actions = {
        "1": pair_phone,
        "2": lambda: pair_phone(speakerphone=True),
        "3": phone_sms,
        "4": connect_audio_device,
        "5": manage_paired_device,
        "6": select_audio,
    }
    while True:
        heading(tr('Bluetooth', '藍牙'))
        row(1, tr('Play music from a phone', '從手機播放音樂'), tr('Phone → AION', '手機 → AION'))
        row(2, tr('Phone speakerphone', '手機免持通話'), tr('Phone ↔ Voice HAT', '手機 ↔ Voice HAT'))
        row(3, tr('Phone SMS', '手機簡訊'))
        row(4, tr('Connect headphones or a speaker', '連接耳機或喇叭'), tr('AION → Bluetooth audio', 'AION → 藍牙音訊'))
        print()
        row(5, tr('Manage paired devices', '管理已配對裝置'))
        row(6, tr('Audio output', '音訊輸出'))
        print()
        row(0, tr('Back', '返回'))

        try:
            choice = input(tr('\n  Select › ', '\n  請選擇 ›')).strip()
            if choice == "0":
                return
            action = actions.get(choice)
            if action is None:
                print(tr('Invalid selection.', '選項無效。'))
                continue
            action()
            pause()

        except (bt.BluetoothError, OSError) as exc:
            print(tr('\nERROR: ', '\n錯誤：') + str(exc))
            pause()

        except (EOFError, KeyboardInterrupt):
            return


if __name__ == "__main__":
    use_saved_language()
    bluetooth_menu()
