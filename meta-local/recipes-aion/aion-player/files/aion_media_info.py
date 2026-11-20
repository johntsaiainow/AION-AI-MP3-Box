"""Local and online lyrics and cover lookup for music playback."""

from bisect import bisect_right
from functools import lru_cache
import json
import re
from threading import Lock
from time import monotonic, sleep
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from mutagen import File, MutagenError
from mutagen.id3 import ID3

USER_AGENT = "AIYBoxRebirth/1.0 (https://github.com/johntsaiainow/AION-AI-MP3-Box)"
TIMESTAMP = re.compile(r"\[(\d{1,3}):([0-5]\d)(?:[.:](\d{1,3}))?\]")
OFFSET = re.compile(r"^\[offset:([+-]?\d+)\]", re.IGNORECASE | re.MULTILINE)
MUSICBRAINZ_LOCK = Lock()
next_musicbrainz_request = 0.0


def clean_line(text):
    return "".join(char if char.isprintable() else " " for char in text).strip()


def parse_lyrics(text):
    text = text.removeprefix("\ufeff")
    match = OFFSET.search(text)
    offset = int(match[1]) / 1000 if match else 0
    timed, plain = [], []
    for line in text.splitlines():
        prefix = re.match(r"(?:\[\d{1,3}:[0-5]\d(?:[.:]\d{1,3})?\])+", line)
        if prefix:
            lyric = clean_line(line[prefix.end():])
            for stamp in TIMESTAMP.finditer(prefix[0]):
                minute, second, fraction = stamp.groups()
                time = int(minute) * 60 + int(second) + float("0." + (fraction or "0"))
                timed.append((time + offset, lyric))
        elif not re.fullmatch(r"\[[a-zA-Z]+:[^\]]*\]", line.strip()):
            plain.append(clean_line(line))
    return tuple(sorted(timed, key=lambda row: row[0])), tuple(plain)


def lyric_at(timed, position):
    index = bisect_right(timed, float(position), key=lambda row: row[0]) - 1
    return timed[index][1] if index >= 0 else ""


def read_audio(track):
    try:
        return File(track)
    except (OSError, MutagenError):
        return None


def track_metadata(audio):
    tags = audio.tags if audio is not None else None
    if isinstance(tags, ID3):
        names = ("TIT2", "TPE1", "TALB", "TPE2")
        values = [str(tags.get(name, "")).strip() for name in names]
        release = str(tags.get("TXXX:MusicBrainz Album Id", "")).strip()
    elif tags is not None:
        names = ("title", "artist", "album", "albumartist")
        values = [next(iter(tags.get(name, ())), "").strip() for name in names]
        release = next(iter(tags.get("musicbrainz_albumid", ())), "").strip()
    else:
        values, release = [""] * 4, ""
    title, artist, album, album_artist = values
    duration = round(getattr(getattr(audio, "info", None), "length", 0) or 0)
    return title, artist, album, album_artist or artist, release, duration


def read_local_lyrics(track, audio):
    plain = ()
    for suffix in (".lrc", ".lyrics", ".txt"):
        try:
            with track.with_suffix(suffix).open(encoding="utf-8-sig", errors="replace") as stream:
                timed, lines = parse_lyrics(stream.read(65536))
        except OSError:
            continue
        if timed:
            return timed, ()
        if any(lines) and not plain:
            plain = lines

    tags = audio.tags if audio is not None else None
    if isinstance(tags, ID3):
        for frame in tags.getall("SYLT"):
            if frame.format == 2 and frame.type == 1 and frame.text:
                return tuple(sorted((timestamp / 1000, clean_line(text)) for text, timestamp in frame.text)), ()
        embedded = (frame.text for frame in tags.getall("USLT"))
    elif tags is not None:
        embedded = (text for field in ("syncedlyrics", "unsyncedlyrics", "lyrics") for text in tags.get(field, ()))
    else:
        embedded = ()
    for text in embedded:
        timed, lines = parse_lyrics(text)
        if timed:
            return timed, ()
        if any(lines) and not plain:
            plain = lines
    return (), plain


def download(endpoint, max_bytes, **parameters):
    url = f"{endpoint}?{urlencode(parameters)}" if parameters else endpoint
    with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=5) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Media response exceeded size limit")
    return data


@lru_cache(maxsize=64)
def online_lyrics(title, artist, album, duration):
    if not title or not artist:
        return (), ()
    parameters = {"track_name": title, "artist_name": artist}
    if album:
        parameters["album_name"] = album
    if duration:
        parameters["duration"] = duration
    try:
        data = json.loads(download("https://lrclib.net/api/get", 256 * 1024, **parameters))
        if not isinstance(data, dict):
            data = {}
        timed, _ = parse_lyrics(data.get("syncedLyrics") or "")
        _, plain = parse_lyrics(data.get("plainLyrics") or "")
    except (OSError, ValueError, TypeError, AttributeError):
        data = {}
        timed = plain = ()
    if timed or plain or data.get("instrumental"):
        return timed, plain
    try:
        matches = json.loads(download("https://lrclib.net/api/search", 512 * 1024,
                                      track_name=title, artist_name=artist))
        candidates = [item for item in matches
                      if item["trackName"].casefold() == title.casefold()
                      and item["artistName"].casefold() == artist.casefold()
                      and (not duration or abs(item["duration"] - duration) <= 5)]
        candidates.sort(key=lambda item: ((item.get("albumName") or "").casefold() != album.casefold(),
                                          not item.get("syncedLyrics")))
        for item in candidates:
            timed, _ = parse_lyrics(item.get("syncedLyrics") or "")
            _, plain = parse_lyrics(item.get("plainLyrics") or "")
            if timed or plain:
                return timed, plain
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        pass
    return (), ()


def musicbrainz_search(entity, query):
    global next_musicbrainz_request
    with MUSICBRAINZ_LOCK:
        sleep(max(0, next_musicbrainz_request - monotonic()))
        next_musicbrainz_request = monotonic() + 1
        result = json.loads(download(f"https://musicbrainz.org/ws/2/{entity}/", 256 * 1024,
                                     query=query, fmt="json", limit=5))
    return result.get(f"{entity}s", ())


@lru_cache(maxsize=16)
def online_cover(album, artist, release, title="", track_artist=""):
    try:
        release_id = str(UUID(release))
    except ValueError:
        release_id = None
    if release_id:
        try:
            return download(f"https://coverartarchive.org/release/{release_id}/front-250", 512 * 1024)
        except (OSError, ValueError):
            pass
    album_query, artist_query = (re.sub(r'[\\"]', lambda match: "\\" + match[0], value)
                                 for value in (album, artist))
    for entity, field in (("release-group", "releasegroup"), ("release", "release")):
        if not album or not artist:
            break
        try:
            matches = musicbrainz_search(entity, f'{field}:"{album_query}" AND artist:"{artist_query}"')
            for item in matches:
                if item.get("title", "").casefold() != album.casefold() or int(item.get("score", 0)) < 90:
                    continue
                try:
                    identifier = str(UUID(item["id"]))
                    return download(f"https://coverartarchive.org/{entity}/{identifier}/front-250", 512 * 1024)
                except (OSError, ValueError):
                    continue
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
    if not album and title and track_artist:
        title_query, performer_query = (re.sub(r'[\\"]', lambda match: "\\" + match[0], value)
                                        for value in (title, track_artist))
        try:
            recordings = musicbrainz_search("recording", f'recording:"{title_query}" AND artist:"{performer_query}"')
            for item in recordings:
                if item.get("title", "").casefold() != title.casefold() or int(item.get("score", 0)) < 90:
                    continue
                for match in item.get("releases", ())[:3]:
                    try:
                        identifier = str(UUID(match["id"]))
                        return download(f"https://coverartarchive.org/release/{identifier}/front-250", 512 * 1024)
                    except (OSError, ValueError, KeyError):
                        continue
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            pass
    return None


def load_media(track, needs_cover, publish):
    audio = read_audio(track)
    title, artist, album, album_artist, release, duration = track_metadata(audio)
    file_artist, separator, file_title = track.stem.partition(" - ")
    if separator:
        title = title or file_title.strip()
        artist = artist or file_artist.strip()
        album_artist = album_artist or artist
    publish("metadata", (title, artist, album))
    timed, plain = read_local_lyrics(track, audio)
    if not timed and not plain:
        timed, plain = online_lyrics(title, artist, album, duration)
    publish("lyrics", (timed, plain))
    if needs_cover:
        cover = online_cover(album, album_artist, release) if album else online_cover("", "", release, title, artist)
        publish("cover", cover)
