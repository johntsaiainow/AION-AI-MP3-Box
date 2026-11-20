#!/usr/bin/env python3
"""AION AI MP3 Box v0.4.0 interactive terminal player.

Only playlist .m3u8 files are written or removed. Audio files are never modified.
"""
import json
import math
import select
import socket
import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from queue import Empty, SimpleQueue
import random
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import tty

from aion_ui import (
    accent, dashboard, fit_cells, options, playback_cover_size, playback_frame, screen, selection, set_language, tr,
)
from aion_local_info import DEFAULT_TIME_ZONE, LocalInformation
from aion_media_info import load_media, lyric_at
from aion_voice_button import open_voice_button, set_voice_lamp

try:
    from mutagen import MutagenError
    from mutagen.flac import FLAC
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, APIC, PictureType
except ImportError:
    FLAC = MP3 = ID3 = APIC = PictureType = None
    MutagenError = OSError

LOCAL_INFORMATION = LocalInformation()
MEDIA_LOOKUPS = ThreadPoolExecutor(max_workers=2)
SUPPORTED_EXTS = ('.flac', '.mp3')
PLAYLIST_NAME = re.compile(r'^[^/\\\x00-\x1f]{1,100}$')
RADIO_STATIONS = (
    ("KAZN AM 1300", "KAZN AM 1300 中文廣播電臺",
     "http://video1.getstreamhosting.com:8308/stream"),
    ("RTI Mandarin", "央廣 Rti 華語",
     "http://streamak0138.akamaized.net/live0138lh-mbm9/_definst_/rti3/chunklist.m3u8"),
    ("BCC News Radio", "中廣新聞網",
     "http://stream.rcs.revma.com/78fm9wyy2tzuv"),
    ("News98 FM 98.1", "九八新聞台 FM 98.1",
     "http://stream.rcs.revma.com/pntx1639ntzuv"),
    ("BCC i Radio", "中廣音樂網 i Radio",
     "http://stream.rcs.revma.com/ndk05tyy2tzuv"),
    ("UFO Radio FM 92.1", "飛碟電台 FM 92.1",
     "http://stream.rcs.revma.com/em90w4aeewzuv"),
    ("AsiaFM FM 92.7", "亞洲電台 FM 92.7",
     "http://stream.rcs.revma.com/xpgtqc74hv8uv"),
    ("ICRT FM 100.7", "ICRT 國際社區廣播 FM 100.7",
     "http://stream.rcs.revma.com/nkdfurztxp3vv"),
    ("IC Radio FM 97.5", "IC 之音竹科廣播 FM 97.5",
     "http://stream.rcs.revma.com/7mnq8rt7k5zuv.mp3"),
)


def log_event(message, priority="info"):
    try:
        subprocess.run(
            ["systemd-cat", "--identifier=aion-player", f"--priority={priority}"],
            input=message + "\n", text=True, timeout=2, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def load_aion_settings():
    path = Path(os.environ.get(
        'AION_CONFIG_PATH',
        '/var/lib/aion-audio/config.json'
    ))
    try:
        with path.open(encoding='utf-8') as stream:
            settings = json.load(stream)
        return settings if isinstance(settings, dict) else {}
    except (OSError, ValueError):
        return {}


def music_root():
    settings = load_aion_settings()
    directory = os.environ.get(
        'AION_MUSIC_DIR',
        settings.get('music_directory', '/mnt/music')
    )
    return Path(directory).expanduser().resolve()


def playlist_dir(root):
    return root / 'Playlists'


def audio_files(folder):
    if not folder.is_dir():
        return []
    return sorted((p for p in folder.iterdir()
                   if p.is_file() and not p.is_symlink()
                   and p.suffix.lower() in SUPPORTED_EXTS), key=lambda p: p.name.casefold())


def albums(root):
    if not root.is_dir():
        return []
    found = []
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted((d for d in dirs if d != 'Playlists'
                          and not (Path(base) / d).is_symlink()), key=str.casefold)
        if any(Path(f).suffix.lower() in SUPPORTED_EXTS and
               (Path(base) / f).is_file() and not (Path(base) / f).is_symlink()
               for f in files):
            found.append(Path(base))
    return found


def safe_song(root, candidate):
    """Reject symlink traversal and files outside music root."""
    candidate = Path(candidate)
    if not candidate.is_absolute():
        candidate = root / candidate
    if not candidate.is_file() or candidate.suffix.lower() not in SUPPORTED_EXTS:
        return None
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return None
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return None
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        return None
    return resolved


def playlist_path(root, name):
    name = name.strip()
    if name.lower().endswith('.m3u8'):
        name = name[:-5]
    if name in ('.', '..') or not PLAYLIST_NAME.fullmatch(name) or name.startswith('.'):
        raise ValueError(tr('Invalid playlist name', '播放清單名稱無效'))
    return playlist_dir(root) / (name + '.m3u8')


def playlist_names(root):
    folder = playlist_dir(root)
    if not folder.is_dir() or folder.is_symlink():
        return []
    return sorted((p for p in folder.glob('*.m3u8') if p.is_file() and not p.is_symlink()),
                  key=lambda p: p.name.casefold())


def read_playlist(root, path):
    if path.is_symlink() or path.parent != playlist_dir(root):
        raise ValueError(tr('Unsafe playlist path', '播放清單路徑無效'))
    result = []
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # Paths in our M3U8 files are relative to /mnt/music, not the playlist folder.
        song = safe_song(root, line)
        if song:
            result.append(song)
    return result


def write_playlist(root, path, tracks):
    folder = playlist_dir(root)
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ValueError(tr('Unsafe playlist directory', '播放清單目錄無效'))
    if path.parent != folder or path.is_symlink():
        raise ValueError(tr('Unsafe playlist destination', '播放清單儲存路徑無效'))
    folder.mkdir(mode=0o755, parents=False, exist_ok=True)
    valid = []
    for song in tracks:
        checked = safe_song(root, song)
        if not checked:
            raise ValueError(tr('Invalid or missing audio file: {song}', '音訊檔案無效或不存在：{song}').format(song=song))
        valid.append(checked.relative_to(root).as_posix())
    content = '#EXTM3U\n' + ''.join(s + '\n' for s in valid)
    fd, tmp = tempfile.mkstemp(prefix='.aion-', suffix='.tmp', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def menu_page(title, entries, subtitle=None, *, group_break=None, status=None):
    settings = load_aion_settings()
    LOCAL_INFORMATION.configure(
        settings.get("device_location"),
        settings.get("time_zone") or DEFAULT_TIME_ZONE,
        settings.get("daylight_saving", True),
        settings.get("commute"),
    )
    return dashboard(title, subtitle, entries, group_break, status, LOCAL_INFORMATION.lines)


def choose(items, heading):
    if not items:
        print(tr('No items available.', '沒有可用項目。'))
        return None
    entries = [*enumerate(items, 1), (0, tr('Back', '返回'))]
    answer = menu_page(heading, entries)
    if not answer.isdecimal() or not 1 <= int(answer) <= len(items):
        return None
    return int(answer) - 1


def choose_album(root):
    folders = albums(root)
    i = choose([str(p.relative_to(root)) for p in folders], tr('Albums', '專輯'))
    return folders[i] if i is not None else None


def choose_playlist(root):
    paths = playlist_names(root)
    i = choose([p.stem for p in paths], tr('Playlists', '播放清單'))
    return paths[i] if i is not None else None


def choose_song(root):
    album = choose_album(root)
    if album is None:
        return None
    tracks = audio_files(album)
    i = choose([p.name for p in tracks], album.name)
    return tracks[i] if i is not None else None


def embedded_cover(song):
    try:
        if song.suffix.lower() == ".flac" and FLAC is not None:
            pictures = FLAC(str(song)).pictures
        elif song.suffix.lower() == ".mp3" and MP3 is not None:
            tags = MP3(str(song), ID3=ID3).tags or {}
            pictures = [tag for tag in tags.values() if isinstance(tag, APIC)]
        else:
            return None
    except (OSError, MutagenError):
        return None
    front = next((picture for picture in pictures if picture.type == PictureType.COVER_FRONT), None)
    picture = front or (pictures[0] if pictures else None)
    return picture.data if picture is not None else None


def cover(song, downloaded=None):
    if not sys.stdout.isatty() or os.environ.get("TERM", "dumb") == "dumb":
        return ()
    chafa = shutil.which("chafa")
    if not chafa:
        return ()

    columns, rows = shutil.get_terminal_size((80, 24))
    width, height = playback_cover_size(columns, rows)
    colors = "none" if "NO_COLOR" in os.environ else "256"
    command = [chafa, "--format=symbols", f"--colors={colors}", "--animate=off", "--probe=off", "--polite=on",
               f"--size={width}x{height}"]

    def render(path):
        result = subprocess.run([*command, str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=5, check=False, encoding="utf-8", errors="replace")
        return tuple(result.stdout.splitlines()) if result.returncode == 0 else ()

    try:
        song = Path(song)
        if data := (downloaded if downloaded is not None else embedded_cover(song)):
            with tempfile.NamedTemporaryFile(prefix="aion-cover-") as image:
                image.write(data)
                image.flush()
                if lines := render(image.name):
                    return lines
        if downloaded is not None:
            return ()

        names = {entry.name.casefold(): entry for entry in song.parent.iterdir()}
        for stem in ("cover", "folder", "front", "album"):
            for suffix in (".jpg", ".jpeg", ".png"):
                path = names.get(stem + suffix)
                if path is not None and path.is_file():
                    if lines := render(path):
                        return lines
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ()


def mpv_ipc(socket_path, command):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        sock.connect(socket_path)
        sock.sendall(
            (json.dumps({"command": command, "request_id": 1}) + "\n").encode("utf-8")
        )
        with sock.makefile("rb") as stream:
            for line in stream:
                result = json.loads(line)
                if result.get("request_id") != 1:
                    continue
                if result.get("error") != "success":
                    raise OSError("MPV IPC error: " + str(result.get("error")))
                return result.get("data")
        raise OSError("MPV IPC disconnected")


def sound_bar(volume, muted):
    volume = max(0, min(100, round(float(volume))))
    filled = volume // 5
    bar = "█" * filled + "░" * (20 - filled)
    status = tr('MUTE', '靜音') if muted else f"{volume}%"
    print(f"{tr('Volume', '音量')} [{bar}] {status}", flush=True)


_aion_volume = 65


# Bass, midrange and treble gains in dB.
MUSIC_PRESETS = (
    ("Neutral", "原音", (0, 0, 0)),
    ("Speech", "人聲", (-5, 4, -2)),
    ("Bass Boost", "低音增強", (6, 0, 0)),
    ("Treble Boost", "高音增強", (0, 0, 5)),
    ("Smooth", "柔和", (2, 0, -4)),
    ("Energize", "活力", (4, -2, 4)),
)
_music_preset = 0

SPECTRUM_RATE = 16000
SPECTRUM_SIZE = 1024
SPECTRUM_BANDS = (63, 125, 250, 500, 1000, 2000, 4000, 6300)


def preset_filter(preset):
    gains = MUSIC_PRESETS[preset][2]
    filters = [
        f"equalizer=f={frequency}:t=o:w=1.5:g={gain}"
        for frequency, gain in zip((120, 1400, 5000), gains)
        if gain
    ]
    headroom = sum(gain for gain in gains if gain > 0)
    if headroom:
        filters.insert(0, f"volume=-{headroom}dB")
    return "lavfi=[" + ",".join(filters) + "]" if filters else ""


def start_spectrum(env):
    try:
        sink = subprocess.check_output(
            ["pactl", "get-default-sink"], text=True, env=env,
            timeout=1, stderr=subprocess.DEVNULL,
        ).strip()
        return subprocess.Popen(
            ["parec", f"--device={sink}.monitor", "--raw", "--format=s16le",
             f"--rate={SPECTRUM_RATE}", "--channels=1", "--latency-msec=80"],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def spectrum_bars(pcm):
    samples = struct.unpack(f"<{SPECTRUM_SIZE}h", pcm)
    windowed = [
        sample * (0.5 - 0.5 * math.cos(math.tau * index / (SPECTRUM_SIZE - 1)))
        for index, sample in enumerate(samples)
    ]
    bars = []
    for center in SPECTRUM_BANDS:
        power = 0
        for frequency in (center * 0.82, center, center * 1.22):
            bin_index = round(frequency * SPECTRUM_SIZE / SPECTRUM_RATE)
            coefficient = 2 * math.cos(math.tau * bin_index / SPECTRUM_SIZE)
            previous = older = 0
            for sample in windowed:
                previous, older = sample + coefficient * previous - older, previous
            power = max(power, previous ** 2 + older ** 2 - coefficient * previous * older)
        amplitude = math.sqrt(power) * 4 / (32768 * SPECTRUM_SIZE)
        db = 20 * math.log10(max(amplitude, 1e-6))
        bars.append("▁▂▃▄▅▆▇█"[max(0, min(7, int((db + 60) / 7.5)))])
    return " ".join(bars)


def playback_display_available():
    return (sys.stdin.isatty() and sys.stdout.isatty()
            and os.environ.get("TERM", "dumb") != "dumb"
            and shutil.get_terminal_size((80, 24)).columns >= 34
            and shutil.get_terminal_size((80, 24)).lines >= 14)


def playback_progress(position, duration):
    def timestamp(seconds):
        minutes, seconds = divmod(max(0, int(seconds)), 60)
        return f"{minutes:02d}:{seconds:02d}"

    if not duration:
        return timestamp(position)
    filled = max(0, min(12, int(position / duration * 12)))
    return "━" * filled + "─" * (12 - filled) + f"  {timestamp(position)} / {timestamp(duration)}"


def playback_controls(process, socket_path, env, tracks=(), station=None):
    global _aion_volume, _music_preset
    terminal = sys.stdin.isatty() and sys.stdout.isatty()
    display = playback_display_available()
    if not display:
        screen(tr("Playback controls", "播放控制"), station)
        print(tr("+/− Volume · M Mute · V Volume · P Pause · Q Stop",
                 "+/− 音量 · M 靜音 · V 音量 · P 暫停 · Q 停止"))
        options((key, tr(english, chinese))
                for key, (english, chinese, _) in enumerate(MUSIC_PRESETS, 1))

    capture = start_spectrum(env) if display else None
    button = open_voice_button() if display else None
    last_button_event = -150_000_000
    terminal_settings = termios.tcgetattr(sys.stdin) if terminal else None
    pcm = b""
    current_track = None
    lookup = lookup_token = None
    media = SimpleQueue()
    timed = plain = ()
    title = station or ""
    artist_album = ""
    artwork = ()
    downloaded_art = None
    cover_status = ""
    position = duration = 0.0
    next_query = next_frame = 0.0
    paused = muted = False
    notice = ""
    lyrics_open = False
    first_line = 0
    old_frame = ()
    last_size = None

    def query(property_name):
        return mpv_ipc(socket_path, ["get_property", property_name])

    def select_track(index):
        nonlocal current_track, lookup, lookup_token, timed, plain, position, duration
        nonlocal title, artist_album, artwork, downloaded_art, cover_status, first_line
        if lookup is not None:
            lookup.cancel()
        current_track = index
        timed = plain = ()
        position = duration = 0.0
        first_line = 0
        track = Path(tracks[index])
        title, artist_album = track.stem, ""
        downloaded_art = None
        artwork = cover(track)
        needs_cover = bool(shutil.which("chafa")) and not artwork
        cover_status = (tr("Looking up artwork…", "正在查找封面…") if needs_cover
                        else tr("Artwork unavailable", "沒有可用封面"))
        token = lookup_token = object()
        lookup = MEDIA_LOOKUPS.submit(load_media, track, needs_cover,
                                      lambda kind, data: media.put((token, kind, data)))

    def draw():
        nonlocal old_frame, last_size, artwork, first_line
        columns, rows = shutil.get_terminal_size((80, 24))
        if columns < 34 or rows < 14:
            return
        size = columns, rows
        if size != last_size:
            old_frame = ()
            if last_size and current_track is not None:
                artwork = cover(tracks[current_track], downloaded=downloaded_art)
            last_size = size
        lyrics = plain or tuple(text for _, text in timed)
        if lyrics_open:
            first_line = min(first_line, max(0, len(lyrics) - rows + 6))
        state = tr("Paused", "已暫停") if paused else (tr("Live radio", "電台直播") if station else tr("Playing", "播放中"))
        volume = tr("Muted", "靜音") if muted else f"{_aion_volume:.0f}%"
        audio = f"{tr('Volume', '音量')} {volume}  ·  {tr(*MUSIC_PRESETS[_music_preset][:2])}"
        lyric = lyric_at(timed, position) if timed else tr("L · Lyrics (no timestamps)", "L · 查看未同步歌詞") if plain else ""
        view = {
            "title": title or tr("Loading…", "載入中…"),
            "artist_album": artist_album,
            "state": state,
            "progress": playback_progress(position, duration),
            "audio": audio,
            "cover": artwork,
            "cover_status": cover_status,
            "spectrum": spectrum_bars(pcm) if len(pcm) == 2 * SPECTRUM_SIZE else "",
            "lyric": lyric,
            "notice": notice,
            "music": bool(tracks),
        }
        lyrics_page = lyrics or (tr("No lyrics available.", "找不到歌詞。"),)
        frame = playback_frame(columns, rows, view, lyrics_page if lyrics_open else None, first_line)
        changes = []
        for row, line in enumerate(frame, 1):
            if not old_frame or line != old_frame[row - 1]:
                changes.append(f"\033[{row};1H\033[2K{line}")
        if changes:
            sys.stdout.write("".join(changes))
            sys.stdout.flush()
        old_frame = frame

    try:
        if display:
            print("\033[?1049h\033[?25l\033[2J", end="", flush=True)
            if tracks:
                select_track(0)
            if button:
                set_voice_lamp(button, True)
        if terminal_settings is not None:
            tty.setcbreak(sys.stdin)
        while process.poll() is None:
            readers = [sys.stdin]
            if capture and capture.stdout:
                readers.append(capture.stdout)
            if button:
                readers.append(button.fd)
            ready, _, _ = select.select(readers, [], [], 0.15)
            if capture and capture.stdout in ready:
                packet = os.read(capture.stdout.fileno(), 8192)
                if packet:
                    pcm = (pcm + packet)[-2 * SPECTRUM_SIZE:]
                else:
                    capture.stdout.close()
                    capture.wait()
                    capture = None
                    pcm = b""
            now = time.monotonic()
            if display and now >= next_query:
                next_query = now + 0.35
                try:
                    if tracks:
                        index = int(query("playlist-pos"))
                        if 0 <= index < len(tracks) and index != current_track:
                            select_track(index)
                    position = float(query("time-pos"))
                    if tracks and not duration:
                        duration = float(query("duration") or 0)
                except (OSError, TypeError, ValueError):
                    pass
            while True:
                try:
                    token, kind, data = media.get_nowait()
                except Empty:
                    break
                if token is not lookup_token:
                    continue
                if kind == "metadata":
                    name, artist, album = data
                    title = name or title
                    artist_album = "  ·  ".join(value for value in (artist, album) if value)
                elif kind == "lyrics":
                    timed, plain = data
                elif kind == "cover":
                    downloaded_art = data
                    artwork = cover(tracks[current_track], downloaded=data) if data else ()
                    cover_status = tr("Artwork unavailable", "沒有可用封面")
            if display and now >= next_frame:
                draw()
                next_frame = now + 0.15
            key = ""
            if button and button.fd in ready:
                try:
                    for event in button.read_edge_events():
                        if event.timestamp_ns - last_button_event >= 150_000_000:
                            last_button_event = event.timestamp_ns
                            key = "p"
                except OSError:
                    button.release()
                    button = None
            if not key and sys.stdin not in ready:
                continue
            if not key:
                key = (os.read(sys.stdin.fileno(), 1).decode("ascii", "ignore")
                       if terminal else sys.stdin.readline())
            if not key:
                if terminal:
                    continue
                break
            key = key.strip().lower()
            if not key:
                continue
            notice = ""
            try:
                if key in ("+", "-", "v"):
                    current = float(query("volume"))
                    if key != "v":
                        delta = 5 if key == "+" else -5
                        mpv_ipc(socket_path, ["set_property", "volume", max(0, min(100, current + delta))])
                        current = float(query("volume"))
                    _aion_volume = current
                    muted = bool(query("mute"))
                    if display:
                        notice = tr("Muted", "已靜音") if muted else f"{tr('Volume', '音量')} {current:.0f}%"
                    else:
                        sound_bar(current, muted)
                elif key == "m":
                    muted = not bool(query("mute"))
                    mpv_ipc(socket_path, ["set_property", "mute", muted])
                    if not display:
                        sound_bar(query("volume"), muted)
                elif key == "p":
                    paused = not bool(query("pause"))
                    mpv_ipc(socket_path, ["set_property", "pause", paused])
                    if button:
                        set_voice_lamp(button, not paused)
                    if not display:
                        print(tr("Paused", "已暫停") if paused else tr("Playing", "播放中"))
                elif key == "q":
                    break
                elif display and key == "l" and tracks:
                    lyrics_open = not lyrics_open
                    first_line = 0
                elif lyrics_open and key in ("j", "k"):
                    first_line = max(0, first_line + (1 if key == "j" else -1))
                elif key in "123456" and len(key) == 1:
                    preset = int(key) - 1
                    mpv_ipc(socket_path, ["af", "set", preset_filter(preset)])
                    _music_preset = preset
                    if not display:
                        print(tr("Selected:", "目前使用："), tr(*MUSIC_PRESETS[preset][:2]), flush=True)
            except (OSError, ValueError, TypeError) as exc:
                if display:
                    notice = tr("Playback control unavailable", "無法控制播放")
                else:
                    print(tr("Playback control unavailable:", "無法控制播放："), exc)
            if display:
                draw()
    finally:
        if button:
            set_voice_lamp(button, False)
            button.release()
        if lookup is not None:
            lookup.cancel()
        if terminal_settings is not None:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, terminal_settings)
        if display:
            print("\033[0m\033[?25h\033[?1049l", end="", flush=True)
        if capture:
            capture.terminate()
            try:
                capture.wait(timeout=1)
            except subprocess.TimeoutExpired:
                capture.kill()
                capture.wait()


def play(tracks, *, shuffle=False, repeat=False, station=None):
    tracks = list(tracks)
    if not tracks:
        print(tr('No playable tracks.', '沒有可播放的曲目。'))
        return

    if shuffle:
        random.shuffle(tracks)

    backend = os.environ.get("AION_AUDIO_BACKEND", "alsa").lower()
    if backend not in ("alsa", "pulse"):
        print(tr('Unsupported audio backend; using ALSA.', '不支援指定的音訊後端，改用 ALSA。'))
        backend = "alsa"

    env = os.environ.copy()
    env.setdefault("PULSE_SERVER", "unix:/run/aion-pulse/pulse/native")
    env.setdefault("PULSE_COOKIE", "/var/lib/aion-audio/.config/pulse/cookie")

    if station is not None:
        screen(tr("Internet radio", "網路電台"), station)
        print(tr("Connecting to the live stream…", "正在連線至直播串流…"), flush=True)
    else:
        repeat_label = tr("On", "開啟") if repeat else tr("Off", "關閉")
        print(tr(
            "Playing {count} track(s) · Output {output} · Repeat {repeat}",
            "播放 {count} 首曲目 · 輸出 {output} · 循環 {repeat}",
        ).format(count=len(tracks), output=backend, repeat=repeat_label))

    with tempfile.TemporaryDirectory(prefix="aion-mpv-") as temp:
        ipc_path = str(Path(temp) / "mpv.sock")

        command = [
            "mpv",
            "--vid=no",
            "--vo=null",
            "--ao=" + backend,
            "--sub-font-provider=none",
            "--input-terminal=no",
            "--msg-level=statusline=no",
            "--input-ipc-server=" + ipc_path,
            "--volume=" + str(_aion_volume),
            "--volume-max=100",
        ]

        audio_filter = preset_filter(_music_preset)
        if audio_filter:
            command.append("--af=" + audio_filter)

        if playback_display_available():
            command.append("--terminal=no")

        if repeat:
            command.append("--loop-playlist=inf")

        if station is not None:
            command.append("--network-timeout=10")

        command += ["--", *map(str, tracks)]

        try:
            process = subprocess.Popen(
                command,
                env=env,
                stdin=subprocess.DEVNULL
            )
        except FileNotFoundError:
            log_event("Playback unavailable: mpv is missing", "err")
            print(tr('mpv not installed.', '尚未安裝 mpv。'))
            return

        medium = "internet radio" if station is not None else f"{len(tracks)} local track(s)"
        log_event(f"Playback requested: {medium}; output={backend}")
        try:
            for _ in range(30):
                if process.poll() is not None:
                    break
                if Path(ipc_path).exists():
                    break
                time.sleep(0.1)

            if process.poll() is None:
                playback_controls(process, ipc_path, env, tracks=tracks if station is None else (), station=station)
        except KeyboardInterrupt:
            print("\n" + tr("Stopping playback.", "正在停止播放。"))
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        if process.returncode > 0:
            log_event(f"Playback failed: {medium}; mpv exit={process.returncode}", "warning")
            if station is not None:
                print(tr("The live stream could not be played.", "無法播放電台直播。"))
            else:
                print(tr("The selected music could not be played.", "無法播放選取的音樂。"))
            if playback_display_available():
                input(tr("Press Enter to return.", "按 Enter 返回。"))


def radio_menu():
    while True:
        entries = [(i, tr(english, chinese))
                   for i, (english, chinese, _) in enumerate(RADIO_STATIONS, 1)]
        entries.append((0, tr("Back", "返回")))
        choice = menu_page(tr("Internet radio", "網路電台"), entries)
        if choice in ('', '0'):
            return
        if not choice.isdecimal() or not 1 <= int(choice) <= len(RADIO_STATIONS):
            print(tr("Invalid selection.", "選項無效。"))
            continue
        english, chinese, stream = RADIO_STATIONS[int(choice) - 1]
        play([stream], station=tr(english, chinese))


def browse_remote_music(root):
    folder = root
    while True:
        tracks = audio_files(folder)
        directories = sorted(
            (entry for entry in folder.iterdir() if not entry.is_symlink() and entry.is_dir()),
            key=lambda path: path.name.casefold(),
        )
        entries = []
        if tracks:
            entries.extend(((1, tr("Play a track", "播放單首曲目")),
                            (2, tr("Play all tracks in this folder", "播放此資料夾的所有曲目"))))
        entries.extend((index, directory.name + "/") for index, directory in enumerate(directories, 3))
        entries.append((0, tr("Back", "返回")))
        choice = menu_page(tr("Remote music", "遠端音樂"), entries, folder.relative_to(root).as_posix())
        if choice in ("", "0"):
            if folder == root:
                return
            folder = folder.parent
        elif choice == "1" and tracks:
            index = choose([track.name for track in tracks], tr("Tracks", "曲目"))
            if index is not None:
                play([tracks[index]])
        elif choice == "2" and tracks:
            play(tracks)
        elif choice.isdecimal() and 3 <= int(choice) < len(directories) + 3:
            folder = directories[int(choice) - 3]
        else:
            print(tr("Invalid selection.", "選項無效。"))


def open_remote_music():
    result = subprocess.run(
        ["rclone", "listremotes"], text=True, capture_output=True, timeout=10, check=False,
    )
    if result.returncode:
        raise OSError(tr("Unable to list rclone connections.", "無法列出 rclone 連線。"))
    remotes = [line for line in result.stdout.splitlines() if line.endswith(":")]
    if not remotes:
        print(tr("Set up an SMB or Google Drive connection first.", "請先設定 SMB 或 Google Drive 連線。"))
        return
    index = choose([remote[:-1] for remote in remotes], tr("Music connections", "音樂連線"))
    if index is None:
        return
    folder = input(tr(
        "Folder path (Enter for the remote root): ",
        "資料夾路徑（按 Enter 使用遠端根目錄）：",
    )).strip().strip("/")
    if any(not char.isprintable() for char in folder) or ".." in folder.split("/"):
        raise ValueError(tr("Invalid folder path.", "資料夾路徑無效。"))

    mount = Path(tempfile.mkdtemp(prefix="aion-music-", dir="/run"))
    try:
        print(tr("Opening the music folder…", "正在開啟音樂資料夾…"), flush=True)
        result = subprocess.run(
            ["rclone", "mount", remotes[index] + folder, str(mount), "--read-only",
             "--daemon", "--daemon-timeout=20s", "--contimeout=5s", "--timeout=15s",
             "--low-level-retries=2"],
            timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        if result.returncode:
            raise OSError(tr(
                "Unable to open the folder. Check connectivity and the remote path.",
                "無法開啟資料夾。請檢查網路和遠端路徑。",
            ))
        browse_remote_music(mount)
    finally:
        # An app-owned mount can be safely detached even when the server is offline.
        mounted = any(
            line.split()[4] == str(mount)
            for line in Path("/proc/self/mountinfo").read_text().splitlines()
        )
        if mounted:
            subprocess.run(["fusermount3", "-uz", str(mount)], check=True, timeout=5)
        mount.rmdir()


def remote_music_menu():
    if not shutil.which("rclone") or not shutil.which("fusermount3"):
        print(tr("Remote storage tools are missing from this image.", "此映像缺少遠端儲存工具。"))
        input(tr("Press Enter to return.", "按 Enter 返回。"))
        return
    while True:
        choice = menu_page(tr("Network & cloud music", "網路與雲端音樂"), (
            (1, tr("Browse a music connection", "瀏覽音樂連線")),
            (2, tr("Set up SMB or Google Drive", "設定 SMB 或 Google Drive")),
            (0, tr("Back", "返回")),
        ))
        try:
            if choice in ("", "0"):
                return
            if choice == "1":
                open_remote_music()
            elif choice == "2":
                subprocess.run(["rclone", "config"], check=True)
            else:
                print(tr("Invalid selection.", "選項無效。"))
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            print(tr("Unable to open remote music:", "無法開啟遠端音樂："), exc)
            input(tr("Press Enter to return.", "按 Enter 返回。"))

def album_menu(root):
    album = choose_album(root)
    if album is None:
        return
    tracks = audio_files(album)
    while True:
        choice = menu_page(tr('Album', '專輯'), (
            (1, tr('Play entire album', '播放整張專輯')),
            (2, tr('Play a track', '播放單首曲目')),
            (3, tr('Shuffle album', '隨機播放專輯')),
            (4, tr('Repeat album', '循環播放專輯')),
            (5, tr('Add album to playlist', '將專輯加入播放清單')),
            (0, tr('Back', '返回')),
        ), str(album.relative_to(root)))
        if choice == '0':
            return
        if choice == '1':
            play(tracks)
        elif choice == '2':
            i = choose([p.name for p in tracks], tr('Tracks', '曲目'))
            if i is not None:
                play([tracks[i]])
        elif choice == '3':
            play(tracks, shuffle=True)
        elif choice == '4':
            play(tracks, repeat=True)
        elif choice == '5':
            add_to_playlist(root, tracks)
        else:
            print(tr('Invalid selection.', '選項無效。'))


def create_playlist(root):
    name = input(tr('New playlist name (Enter to cancel): ', '新播放清單名稱（按 Enter 取消）：')).strip()
    if not name:
        return
    path = playlist_path(root, name)
    if path.exists() or path.is_symlink():
        print(tr('Playlist already exists.', '播放清單已存在。'))
        return
    write_playlist(root, path, [])
    print(tr('Created:', '已建立：'), path.name)


def add_to_playlist(root, tracks=None):
    path = choose_playlist(root)
    if path is None:
        return
    if tracks is None:
        song = choose_song(root)
        if song is None:
            return
        tracks = [song]
    existing = read_playlist(root, path)
    additions = [p for p in tracks if p not in existing]
    write_playlist(root, path, existing + additions)
    print(tr(
        'Added {count} song(s) to {name}.', '已將 {count} 首歌曲加入「{name}」。',
    ).format(count=len(additions), name=path.stem))


def remove_from_playlist(root):
    path = choose_playlist(root)
    if path is None:
        return
    tracks = read_playlist(root, path)
    i = choose([str(p.relative_to(root)) for p in tracks], tr('Remove playlist entry', '移除播放清單項目'))
    if i is None:
        return
    removed = tracks.pop(i)
    write_playlist(root, path, tracks)
    print(tr(
        'Removed {name} from playlist. Audio file kept.',
        '已從播放清單移除 {name}，並保留音訊檔案。',
    ).format(name=removed.name))


def rename_or_delete(root):
    path = choose_playlist(root)
    if path is None:
        return
    action = input(tr('[r] Rename / [d] Delete playlist / Enter cancel: ', '[r] 重新命名／[d] 刪除播放清單／按 Enter 取消：')).strip().lower()
    if action == 'r':
        name = input(tr('New name: ', '新名稱：')).strip()
        if not name:
            return
        new = playlist_path(root, name)
        if new.exists() or new.is_symlink():
            print(tr('Destination already exists.', '該名稱已存在。'))
            return
        path.rename(new)
        print(tr('Renamed to', '已重新命名為'), new.name)
    elif action == 'd':
        print(tr('This removes only the .m3u8 playlist, never audio files.', '只會刪除 .m3u8 播放清單，音訊檔案會保留。'))
        command = f'DELETE {path.stem}'
        prompt = tr('Type {command} to confirm: ', '輸入 {command} 確認：')
        if input(prompt.format(command=command)).strip() == command:
            path.unlink()
            print(tr('Playlist deleted.', '已刪除播放清單。'))


def playlist_menu(root):
    path = choose_playlist(root)
    if path is None:
        return
    while True:
        tracks = read_playlist(root, path)
        choice = menu_page(tr('Playlist', '播放清單'), (
            (1, tr('Play all', '播放全部')),
            (2, tr('Shuffle', '隨機播放')),
            (3, tr('Repeat', '循環播放')),
            (4, tr('Play a track', '播放單首曲目')),
            (0, tr('Back', '返回')),
        ), path.stem)
        if choice == '0':
            return
        if choice == '1':
            play(tracks)
        elif choice == '2':
            play(tracks, shuffle=True)
        elif choice == '3':
            play(tracks, repeat=True)
        elif choice == '4':
            i = choose([str(p.relative_to(root)) for p in tracks], tr('Tracks', '曲目'))
            if i is not None:
                play([tracks[i]])
        else:
            print(tr('Invalid selection.', '選項無效。'))


def bluetooth_menu():
    try:
        subprocess.run(['aion-bluetooth-menu'], check=False)
    except FileNotFoundError:
        print(tr('aion-bluetooth-menu is not installed.', '尚未安裝藍牙管理工具。'))


def audio_menu():
    screen(tr('Audio output settings', '音訊輸出設定'))
    print(tr('Current output:', '目前輸出：'), os.environ.get('AION_AUDIO_BACKEND', 'alsa'))
    options((
        (1, tr('ALSA · Local', 'ALSA · 本機')),
        (2, tr('PulseAudio · Bluetooth', 'PulseAudio · 藍牙')),
        (0, tr('Back', '返回')),
    ))
    choice = selection()
    if choice in ('1', '2'):
        backend = 'alsa' if choice == '1' else 'pulse'
        os.environ['AION_AUDIO_BACKEND'] = backend
        print(tr('Selected:', '已選擇：'), backend, tr('(for this player session)', '（本次播放工作階段）'))
        if backend == 'pulse':
            print(tr('Choose an output sink in Bluetooth Management; device access must be configured.', '請在藍牙管理中選擇音訊輸出裝置，並確認裝置存取權限。'))



def run_management_command(candidates, label):
    import shutil

    for command in candidates:
        executable = shutil.which(command)
        if executable:
            try:
                subprocess.run([executable], check=False)
            except OSError as exc:
                print(f'{label} · ' + tr('Failed:', '執行失敗：'), exc)
            return

    print(f'{label} · ' + tr('Management tool unavailable.', '管理工具無法使用。'))
    print(tr('Available candidates:', '可用的指令名稱：'), ', '.join(candidates))


def event_log_menu():
    views = {"1": [], "2": ["--priority=warning"], "3": ["--boot=-1"]}
    while True:
        screen(tr("System event log", "系統事件記錄"))
        options((
            (1, tr("Recent events", "最近事件")),
            (2, tr("Warnings and errors", "警告與錯誤")),
            (3, tr("Previous boot", "上次開機")),
            (0, tr("Back", "返回")),
        ))
        choice = selection()
        if choice in ("", "0"):
            return
        if choice not in views:
            print(tr("Invalid selection.", "選項無效。"))
            continue
        result = subprocess.run(
            ["journalctl", "--system", "--no-pager", "--lines=45",
             "--output=short-iso", *views[choice]],
            check=False,
        )
        if result.returncode:
            print(tr("The selected journal is unavailable.", "無法取得所選的事件記錄。"))
        input(tr("\nPress Enter to return.", "\n按 Enter 返回。"))


def hardware_menu():
    while True:
        choice = menu_page(tr('Hardware & system', '硬體與系統'), (
            (1, tr('Wi-Fi management', 'Wi-Fi 管理')),
            (2, tr('Bluetooth management', '藍牙管理')),
            (3, tr('Storage management', '儲存裝置管理')),
            (4, tr('Import music', '匯入音樂')),
            (5, tr('Audio output settings', '音訊輸出設定')),
            (6, tr('System information', '系統資訊')),
            (7, tr('Configuration wizard', '設定精靈')),
            (8, tr('System event log', '系統事件記錄')),
            (9, tr('Language', '語言')),
            (10, tr('Time zone and daylight saving', '時區與日光節約時間')),
            (11, tr('Device location', '設備地點')),
            (12, tr('TomTom traffic key', 'TomTom 路況金鑰')),
            (13, tr('Commute addresses', '通勤地址')),
            (0, tr('Back to music', '返回音樂選單')),
        ))

        if choice == '0':
            return
        elif choice == '1':
            run_management_command(
                ['aion-wifi-menu', 'aion-wifi', 'nmtui'],
                tr('Wi-Fi Management', 'Wi-Fi 管理'))
        elif choice == '2':
            bluetooth_menu()
        elif choice == '3':
            run_management_command(
                ['aion-storage-menu', 'aion-storage'],
                tr('Storage Management', '儲存裝置管理'))
        elif choice == '4':
            run_management_command(
                ['aion-music-copy', 'aion-library-copy'],
                tr('Music Library Copy', '匯入音樂'))
        elif choice == '5':
            audio_menu()
        elif choice == '6':
            import platform
            print(tr('System:', '系統：'), platform.platform())
            print('Python:', platform.python_version())
            print(tr('Music root:', '音樂目錄：'), music_root())
            input(tr("Press Enter to return.", "按 Enter 返回。"))
        elif choice == '7':
            subprocess.run(
                ['/usr/bin/python3', '/usr/bin/aion-setup', '--force'],
                check=False
            )
            set_language(load_aion_settings().get('language'))
        elif choice == '8':
            event_log_menu()
        elif choice == '9':
            subprocess.run(['/usr/bin/python3', '/usr/bin/aion-setup', '--language'], check=False)
            set_language(load_aion_settings().get('language'))
        elif choice == '10':
            subprocess.run(['/usr/bin/python3', '/usr/bin/aion-setup', '--timezone'], check=False)
        elif choice == '11':
            subprocess.run(['/usr/bin/python3', '/usr/bin/aion-setup', '--location'], check=False)
        elif choice == '12':
            subprocess.run(['/usr/bin/python3', '/usr/bin/aion-setup', '--traffic-key'], check=False)
        elif choice == '13':
            subprocess.run(['/usr/bin/python3', '/usr/bin/aion-setup', '--commute'], check=False)
        else:
            print(tr('Invalid selection.', '選項無效。'))


def playlist_management_menu(root):
    while True:
        choice = menu_page(tr('Playlist management', '播放清單管理'), (
            (1, tr('Browse and play playlists', '瀏覽與播放清單')),
            (2, tr('Create a playlist', '建立播放清單')),
            (3, tr('Add a song', '加入歌曲')),
            (4, tr('Remove a song', '移除歌曲')),
            (5, tr('Rename or delete a playlist', '重新命名或刪除播放清單')),
            (0, tr('Back to music', '返回音樂選單')),
        ))

        if choice == '0':
            return
        elif choice == '1':
            playlist_menu(root)
        elif choice == '2':
            create_playlist(root)
        elif choice == '3':
            add_to_playlist(root)
        elif choice == '4':
            remove_from_playlist(root)
        elif choice == '5':
            rename_or_delete(root)
        else:
            print(tr('Invalid selection.', '選項無效。'))


def interactive(root):
    status = None
    while True:
        root = music_root()
        settings = load_aion_settings()
        os.environ['AION_AUDIO_BACKEND'] = settings.get(
            'audio_backend', 'alsa'
        )
        set_language(settings.get('language'))
        entries = (
            (1, tr('Browse and play albums', '瀏覽與播放專輯')),
            (2, tr('Playlists', '播放清單')),
            (3, tr('Shuffle all music', '隨機播放所有音樂')),
            (4, tr('Internet radio', '網路電台')),
            (5, tr('Hardware & system', '硬體與系統')),
            (6, tr('Network & cloud music', '網路與雲端音樂')),
            (0, tr('Exit', '離開')),
        )

        try:
            choice = menu_page(tr('Main menu', '主選單'), entries, str(root), group_break=5, status=status)
            status = None

            if choice == '0':
                answer = input(tr('Exit to the console prompt? [y/N] ',
                                  '確定離開並回到 Console？[y/N] ')).strip().casefold()
                if answer in ('y', 'yes', '是', '確定'):
                    print(tr('To reopen the main menu, run aion-player-console.',
                             '要回到主選單，請輸入 aion-player-console 並按 Enter。'), flush=True)
                    return
            elif choice == '1':
                album_menu(root)
            elif choice == '2':
                playlist_management_menu(root)
            elif choice == '3':
                tracks = [song for album in albums(root) for song in audio_files(album)]
                play(tracks, shuffle=True)
            elif choice == '4':
                radio_menu()
            elif choice == '5':
                hardware_menu()
            elif choice == '6':
                remote_music_menu()
            else:
                status = tr('Invalid selection.', '選項無效。')
        except (ValueError, OSError, UnicodeError) as exc:
            status = f"{tr('Operation failed:', '操作失敗：')} {exc}"
        except (EOFError, KeyboardInterrupt):
            print('\n' + tr('Cancelled.', '已取消。'))
            return


def main():
    parser = argparse.ArgumentParser(description='AION AI MP3 Box Player')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--standby', action='store_true')
    mode.add_argument('--interactive', action='store_true')
    args = parser.parse_args()
    settings = load_aion_settings()
    os.environ.setdefault(
        'AION_AUDIO_BACKEND',
        settings.get('audio_backend', 'alsa')
    )
    root = music_root()
    if args.standby:
        print('AION Player: standby mode', flush=True)
        print(f'Music directory: {root}', flush=True)
        running = True
        def stop(signum, frame):
            nonlocal running
            running = False
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        while running:
            time.sleep(1)
        print('AION Player: stopped', flush=True)
        return 0
    set_language(settings.get('language'))
    if not sys.stdin.isatty():
        print('ERROR: Interactive mode requires a terminal.', file=sys.stderr)
        return 1
    log_event("Interactive console started")
    interactive(root)
    return 0


if __name__ == '__main__':
    sys.exit(main())
