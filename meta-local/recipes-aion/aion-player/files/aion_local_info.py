"""Nonblocking local information for the terminal dashboard."""

from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import subprocess
from threading import Thread
from time import monotonic
from typing import NamedTuple
from urllib.parse import quote, urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aion_ui import accent, cell_width, fit_cells, tr
from aion_traffic_map import render_traffic_map, traffic_map

DEFAULT_TIME_ZONE = "America/Los_Angeles"
TRAFFIC_KEY_PATH = Path("/etc/aiy-box-rebirth/tomtom.key")
US_ZIP = re.compile(r"[0-9]{5}(?:-[0-9]{4})?")
POSTAL_CODE = re.compile(r"[0-9A-Z][0-9A-Z -]{1,11}")
STREET_ADDRESS = re.compile(r"^\d+\s|\d+\s*[號号之]|[路街巷弄]\s*\d")
DAILY_WEATHER = (
    "time", "temperature_2m_max", "temperature_2m_min", "weather_code",
    "precipitation_probability_max", "precipitation_sum", "wind_speed_10m_max",
    "wind_gusts_10m_max",
)


def clock_time(zone_name, daylight_saving, instant=None):
    try:
        zone = ZoneInfo(zone_name)
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        zone = timezone(timedelta(hours=-8), "PST")
    now = (instant or datetime.now(timezone.utc)).astimezone(zone)
    if daylight_saving is False and now.dst():
        standard_offset = now.utcoffset() - now.dst()
        standard = (timezone(standard_offset, "PST") if zone_name == DEFAULT_TIME_ZONE
                    else timezone(standard_offset))
        now = now.astimezone(standard)
    return now


def request_json(endpoint, **parameters):
    with urlopen(f"{endpoint}?{urlencode(parameters)}", timeout=5) as response:
        return json.load(response)


class LocationNotFound(ValueError):
    pass


def weather_place_name(value):
    return (0 < len(value) <= 120 and value.isprintable()
            and not any(char in value for char in ",，#＃")
            and STREET_ADDRESS.search(value) is None)


def coordinate_pair(location):
    lat, separator, lon = location.replace("，", ",").partition(",")
    if separator:
        try:
            point = float(lat), float(lon)
        except ValueError:
            pass
        else:
            if -90 <= point[0] <= 90 and -180 <= point[1] <= 180:
                return point
            raise ValueError("Coordinates out of range")
    return None


@lru_cache(maxsize=8)
def coordinates(location, region="", country=""):
    if point := coordinate_pair(location):
        return point
    if not weather_place_name(location):
        raise LocationNotFound
    if region and not weather_place_name(region):
        raise LocationNotFound
    if country and not re.fullmatch(r"[A-Z]{2}", country):
        raise LocationNotFound
    name = location
    if region:
        name = f"{name}, {region}"
    parameters = {"countryCode": country} if country else {}
    matches = request_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        name=name, count=1, language="en", **parameters,
    ).get("results") or []
    if not matches:
        raise LocationNotFound
    place = matches[0]
    return place["latitude"], place["longitude"]


def location_parts(value):
    if isinstance(value, str):
        value = value.strip()
        return (value[:5], "", "US") if len(value) == 10 and US_ZIP.fullmatch(value) else (value, "", "")
    if isinstance(value, dict):
        postal_code, city, region, country = (
            value[field].strip() if isinstance(value.get(field), str) else ""
            for field in ("postal_code", "city", "region", "country")
        )
        country = country.upper()
        if postal_code and POSTAL_CODE.fullmatch(postal_code.upper()):
            return (postal_code[:5] if country == "US" and US_ZIP.fullmatch(postal_code)
                    else postal_code), "", country
        if (country == "US" or not country and len(city) == 10) and US_ZIP.fullmatch(city):
            return city[:5], "", "US"
        return city, region, country
    return "", "", ""


def location_label(value):
    return ", ".join(part for part in location_parts(value) if part)


@lru_cache(maxsize=8)
def commute_point(address, key):
    result = request_json(
        f"https://api.tomtom.com/search/2/geocode/{quote(address, safe='')}.json",
        key=key, limit=1,
    )["results"][0]["position"]
    return float(result["lat"]), float(result["lon"])


class CommuteRoute(NamedTuple):
    travel: int
    delay: int
    points: tuple
    affected: tuple
    incidents: tuple = ()


def traffic_incidents(sections):
    events = {}
    for section in sections:
        if section.get("sectionType") != "TRAFFIC":
            continue
        causes = tuple(cause.get("mainCauseCode") for cause in (section.get("tec") or {}).get("causes", ())
                       if isinstance(cause, dict))
        category = section.get("simpleCategory")
        kind = ("ACCIDENT" if 2 in causes else "ROAD_WORK" if 3 in causes else category or "OTHER")
        event = (kind, section.get("delayInSeconds"), section.get("effectiveSpeedInKmh"))
        identity = section.get("eventId") or (section.get("startPointIndex"), section.get("endPointIndex"), kind)
        events.setdefault(identity, event)
    priority = {"ACCIDENT": 0, "ROAD_CLOSURE": 1, "ROAD_WORK": 2, "JAM": 3}
    return tuple(sorted(events.values(), key=lambda event: priority.get(event[0], 4)))


@lru_cache(maxsize=8)
def commute_route(start, end, key, refresh_slot):
    points = ":".join(f"{lat},{lon}" for lat, lon in (start, end))
    data = request_json(f"https://api.tomtom.com/routing/1/calculateRoute/{points}/json",
                        key=key, traffic="true", travelMode="car", routeRepresentation="polyline",
                        sectionType="traffic")
    route = data["routes"][0]
    summary = route["summary"]
    geometry = tuple((float(point["latitude"]), float(point["longitude"]))
                     for leg in route.get("legs", ()) for point in leg["points"])
    affected = tuple((section["startPointIndex"], section["endPointIndex"], section.get("simpleCategory"))
                     for section in route.get("sections", ())
                     if section.get("sectionType") == "TRAFFIC"
                     and isinstance(section.get("startPointIndex"), int)
                     and isinstance(section.get("endPointIndex"), int))
    return CommuteRoute(int(summary["travelTimeInSeconds"]), int(summary["trafficDelayInSeconds"]),
                        geometry, affected, traffic_incidents(route.get("sections", ())))


CLOCK_DIGITS = {
    "0": ("███", "█ █", "█ █", "█ █", "███"),
    "1": (" █ ", "██ ", " █ ", " █ ", "███"),
    "2": ("███", "  █", "███", "█  ", "███"),
    "3": ("███", "  █", "███", "  █", "███"),
    "4": ("█ █", "█ █", "███", "  █", "  █"),
    "5": ("███", "█  ", "███", "  █", "███"),
    "6": ("███", "█  ", "███", "█ █", "███"),
    "7": ("███", "  █", "  █", "  █", "  █"),
    "8": ("███", "█ █", "███", "█ █", "███"),
    "9": ("███", "█ █", "███", "  █", "███"),
    ":": (" ", "█", " ", "█", " "),
}


def large_clock(time):
    return [" ".join(CLOCK_DIGITS[char][row] for char in time) for row in range(5)]


def weather_display(code):
    if code <= 1:
        return tr("Clear", "晴朗"), (" \\ | / ", "-- O --", " / | \\ "), "1;33", "☀"
    if code <= 3:
        return tr("Cloudy", "多雲"), ("  .--. ", ".:(    )", " `----' "), "1;37", "☁"
    if code in (45, 48):
        return tr("Fog", "有霧"), ("  .--.  ", "========", " ------ "), "1;37", "≈"
    if code in (71, 73, 75, 77, 85, 86):
        return tr("Snow", "下雪"), ("  .--.  ", ".:(____)", "  * * * "), "1;37", "*"
    if code >= 95:
        return tr("Thunderstorms", "雷雨"), ("  .--.  ", ".:(____)", "  /Z/ / "), "1;33", "ϟ"
    return tr("Rain", "降雨"), ("  .--.  ", ".:(____)", "  / / / "), "1;34", "☂"


def forecast_line(day, width):
    date, high, low, code, probability, precipitation, wind, gusts = day
    descriptions = {
        0: ("Clear skies", "晴朗"), 1: ("Mostly clear", "大致晴朗"),
        2: ("Partly cloudy", "晴時多雲"), 3: ("Overcast", "陰天"),
        45: ("Fog", "有霧"), 48: ("Freezing fog", "凍霧"),
        51: ("Light drizzle", "輕微毛毛雨"), 53: ("Drizzle", "毛毛雨"),
        55: ("Heavy drizzle", "較強毛毛雨"), 56: ("Light freezing drizzle", "輕微凍毛毛雨"),
        57: ("Heavy freezing drizzle", "較強凍毛毛雨"), 61: ("Light rain", "小雨"),
        63: ("Moderate rain", "中雨"), 65: ("Heavy rain", "大雨"),
        66: ("Light freezing rain", "微弱凍雨"), 67: ("Heavy freezing rain", "強凍雨"),
        71: ("Light snow", "小雪"), 73: ("Moderate snow", "中雪"),
        75: ("Heavy snow", "大雪"), 77: ("Snow grains", "米雪"),
        80: ("Light showers", "短暫陣雨"), 81: ("Moderate showers", "陣雨"),
        82: ("Heavy showers", "強陣雨"), 85: ("Light snow showers", "短暫陣雪"),
        86: ("Heavy snow showers", "強陣雪"), 95: ("Thunderstorms", "雷雨"),
        96: ("Thunderstorms with hail", "雷雨伴冰雹"),
        99: ("Thunderstorms with heavy hail", "雷雨伴強冰雹"),
    }
    condition = tr(*descriptions.get(code, ("Unknown", "天況未知")))

    def measure(value, unit, precision=0):
        return f"{value:.{precision}f}{unit}" if isinstance(value, (int, float)) else "—"

    _, _, color, glyph = weather_display(code) if isinstance(code, int) else ("", (), "2", "—")
    day_label = str(date)[5:10].replace("-", "/")
    high_low = f"{measure(high, '°')}/{measure(low, '°')}"
    rain = f"{tr('Rain', '雨')} {measure(probability, '%')}/{measure(precipitation, '', 1)}"
    air = f"{tr('Wind', '風')} {measure(wind, '')}/{measure(gusts, '')}"
    prefix = f"{day_label} {glyph} "
    suffix = f" {high_low} {rain} {air}"
    space = width - sum(map(cell_width, prefix + suffix))
    return prefix + fit_cells(condition, max(0, space)).rstrip() + suffix, color


FORECAST_ICONS = {
    "☀": ("#.#.#", ".###.", "#####", ".###.", "#.#.#"),
    "☁": ("..##.", ".####", "#####", ".###.", "....."),
    "≈": (".....", "####.", ".....", ".####", "....."),
    "*": ("#...#", ".#.#.", "#####", ".#.#.", "#...#"),
    "ϟ": ("..###", ".###.", ".##..", "..##.", "..#.."),
    "☂": ("..##.", ".####", "#####", "#.#.#", ".#.#."),
    "—": (".....", ".....", ".###.", ".....", "....."),
}


def forecast_icon_rows(forecast, cell, height):
    # One terminal cell is roughly twice as tall as it is wide.
    size = max(1, cell - 1)
    rows = min(height, (size + 1) // 2)
    icons = [weather_display(day[3])[2:] if isinstance(day[3], int) else ("2", "—") for day in forecast]
    lines = []
    for row in range(rows):
        pieces = []
        for color, glyph in icons:
            pixels = FORECAST_ICONS[glyph]
            text = ""
            for column in range(size):
                x = column * 5 // size
                top = pixels[row * 5 // rows][x] == "#"
                bottom = pixels[(2 * row + 1) * 5 // (2 * rows)][x] == "#"
                text += " ▀▄█"[top + 2 * bottom]
            pieces.append(accent(fit_cells(text, cell), color))
        lines.append(("   " + "".join(pieces), None))
    return lines


def host_status():
    details = []
    try:
        temperature = int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
        details.append(f"CPU {temperature:.0f}°C")
    except (OSError, ValueError):
        pass
    try:
        memory = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        total = int(memory["MemTotal"].split()[0])
        available = int(memory["MemAvailable"].split()[0])
        if total > 0:
            details.append(f"{tr('RAM', '記憶體')} {(total - available) / total:.0%}")
    except (OSError, ValueError, KeyError, IndexError):
        pass
    return " · ".join(details) or tr("Unavailable", "暫無資料")


def network_status():
    try:
        routes = subprocess.check_output(["ip", "-4", "route", "show", "default"],
                                         text=True, stderr=subprocess.DEVNULL, timeout=1)
        addresses = subprocess.check_output(["ip", "-o", "-4", "addr", "show", "up", "scope", "global"],
                                            text=True, stderr=subprocess.DEVNULL, timeout=1)
    except (OSError, subprocess.SubprocessError):
        return tr("Unavailable", "暫無資料"), "2"
    interfaces = {}
    for line in addresses.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[2] == "inet":
            interfaces.setdefault(fields[1].split("@")[0], fields[3].split("/")[0])
    for line in routes.splitlines():
        fields = line.split()
        if "dev" in fields and fields[-1] != "linkdown":
            interface = fields[fields.index("dev") + 1]
            if interface in interfaces:
                return f"{interface} · {interfaces[interface]}", "1;32"
    if interfaces:
        interface, address = next(iter(interfaces.items()))
        return f"{interface} · {address} · {tr('Local only', '僅區網')}", "1;33"
    return tr("No IPv4 connection", "無 IPv4 連線"), "1;33"


class LocalInformation:
    def __init__(self):
        self.location = ("", "", "")
        self.key = ""
        self.commute = ("", "")
        self.result = None
        self.next_refresh = 0
        self.worker = None
        self.time_zone = DEFAULT_TIME_ZONE
        self.daylight_saving = True
        self.next_status_refresh = 0
        self.status = ()
        self.page_start = None

    def configure(self, location, time_zone=DEFAULT_TIME_ZONE, daylight_saving=True, commute=None):
        self.time_zone = time_zone
        self.daylight_saving = daylight_saving
        location = location_parts(location)
        commute = commute if isinstance(commute, dict) else {}
        commute = tuple(commute[field].strip() if isinstance(commute.get(field), str) else ""
                        for field in ("home", "work"))
        key = os.environ.get("TOMTOM_API_KEY", "").strip()
        if not key:
            try:
                key = TRAFFIC_KEY_PATH.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError):
                pass
        if (location, key, commute) != (self.location, self.key, self.commute):
            self.location, self.key, self.commute = location, key, commute
            self.result = None
            self.next_refresh = 0

    def refresh(self, location, key, commute):
        current = traffic = None
        forecast = ()
        missing_location = False
        commute_results = ()
        map_points = ()
        try:
            lat, lon = coordinates(*location) if location[0] else (None, None)
        except LocationNotFound:
            missing_location = True
        except (OSError, ValueError, TypeError, KeyError):
            pass
        else:
            if lat is None:
                data = {}
            else:
                try:
                    data = request_json(
                        "https://api.open-meteo.com/v1/forecast",
                        latitude=lat, longitude=lon,
                        current="temperature_2m,weather_code",
                        daily=",".join(DAILY_WEATHER[1:]),
                        forecast_days=8, timezone="auto",
                    )
                except (OSError, ValueError, TypeError, KeyError):
                    data = {}
            try:
                current = (float(data["current"]["temperature_2m"]), int(data["current"]["weather_code"]))
            except (ValueError, TypeError, KeyError):
                pass
            try:
                daily = data["daily"]
                forecast = tuple(
                    (date, *(series[index] if isinstance(series, list) and index < len(series) else None
                             for series in (daily.get(field) for field in DAILY_WEATHER[1:])))
                    for index, date in enumerate(daily["time"][:8])
                )
            except (AttributeError, TypeError, KeyError):
                pass
            if key and lat is not None and not all(commute):
                map_points = ((lat, lon),)
                try:
                    data = request_json(
                        "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json",
                        point=f"{lat},{lon}", unit="kmph", key=key,
                    )["flowSegmentData"]
                    traffic = (int(data["currentSpeed"]), int(data["freeFlowSpeed"]), data["roadClosure"])
                except (OSError, ValueError, TypeError, KeyError):
                    pass
        if key and all(commute):
            try:
                home, work = (commute_point(address, key) for address in commute)
            except (OSError, ValueError, TypeError, KeyError, IndexError):
                pass
            else:
                map_points = (home, work)
                routes = []
                slot = int(monotonic() // 600)
                for start, end in ((home, work), (work, home)):
                    try:
                        routes.append(commute_route(start, end, key, slot))
                    except (OSError, ValueError, TypeError, KeyError, IndexError):
                        routes.append(None)
                commute_results = tuple(routes)
        # Tag the result so a slower request for a previous location is ignored.
        tag = location, key, commute
        if tag == (self.location, self.key, self.commute):
            self.result = (*tag, current, traffic, forecast, missing_location, commute_results, None)
            if location[0] and (not current or not forecast) and not missing_location:
                self.next_refresh = monotonic() + 30
        if map_points and tag == (self.location, self.key, self.commute):
            try:
                image = traffic_map(map_points, key, commute_results)
            except (OSError, ValueError, ImportError):
                return
            if tag == (self.location, self.key, self.commute):
                self.result = (*tag, current, traffic, forecast, missing_location, commute_results, image)

    def start_refresh(self):
        if ((self.location[0] or self.key and all(self.commute)) and monotonic() >= self.next_refresh
                and (self.worker is None or not self.worker.is_alive())):
            self.next_refresh = monotonic() + 600
            self.worker = Thread(target=self.refresh, args=(self.location, self.key, self.commute), daemon=True)
            self.worker.start()

    def traffic_lines(self, width, height, traffic, routes, image, unavailable):
        lines = [(tr("Traffic conditions", "即時路況"), "1;36")]
        if all(self.commute):
            directions = (tr("To work", "上班"), tr("Home", "下班"))
            for index, direction in enumerate(directions):
                route = routes[index] if index < len(routes) else None
                if route is None:
                    description = unavailable if self.key else tr("TomTom key required", "需要 TomTom 金鑰")
                else:
                    if route.delay:
                        delay = max(1, (route.delay + 59) // 60)
                        description = tr("Traffic delay {minutes} min", "路況延誤 {minutes} 分鐘").format(minutes=delay)
                    else:
                        description = tr("No reported delay", "未回報延誤")
                lines.append((f"{direction} · {description}", ("1;36", "1;35")[index]))
            labels = {
                "ACCIDENT": ("Crash", "車禍"), "ROAD_WORK": ("Roadwork", "施工"),
                "JAM": ("Congestion", "壅塞"), "ROAD_CLOSURE": ("Closure", "道路封閉"),
            }
            events = []
            route_events = [tuple((direction, event) for event in route.incidents) if route else ()
                            for direction, route in zip(directions, routes)]
            for ordinal in range(max(map(len, route_events), default=0)):
                events.extend(items[ordinal] for items in route_events if ordinal < len(items))
            capacity = max(0, height - len(lines) - (2 if image else 1))
            for direction, (kind, delay, speed) in events[:capacity]:
                description = tr(*labels.get(kind, ("Traffic incident", "交通事件")))
                if isinstance(delay, int) and delay > 0:
                    description += f" · +{(delay + 59) // 60} {tr('min', '分鐘')}"
                if isinstance(speed, int):
                    description += f" · {speed} km/h"
                lines.append((f"{direction} · {description}", "1;33"))
            if not events and any(routes) and capacity:
                lines.append((tr("No incidents reported on available routes", "已取得的路線暫無事件通報"), "2"))
        elif traffic and traffic[2]:
            lines.append((tr("Nearby road closed", "附近道路封閉"), "1;31"))
        elif traffic and traffic[1] > 0:
            ratio = traffic[0] / traffic[1]
            condition = (tr("Clear", "順暢") if ratio >= 0.8 else tr("Slow", "車速偏慢")
                         if ratio >= 0.5 else tr("Heavy traffic", "壅塞"))
            lines.append((f"{condition} · {traffic[0]} km/h", "1;37"))
        if not all(self.commute):
            lines.append((tr("Set home and work addresses for commute routes", "設定住家與公司地址以顯示通勤路線"), "2"))
            if not self.key:
                lines.append((tr("TomTom key required", "需要 TomTom 金鑰"), "2"))
        art = ()
        if image and height > len(lines) + 1:
            lines.append(("TomTom", "2"))
            art = render_traffic_map(image, width, height - len(lines), "NO_COLOR" not in os.environ)
            lines.extend((line, None) for line in art)
        if not art:
            lines.append((f"{tr('Traffic map', '路況地圖')} · {unavailable}", "2"))
        return lines

    def lines(self, width=57, height=18):
        if monotonic() >= self.next_status_refresh:
            network, color = network_status()
            self.status = ((f"{tr('Host', '主機')} · {host_status()}", "1;37"),
                           (f"{tr('Network', '網路')} · {network}", color))
            self.next_status_refresh = monotonic() + 5
        height -= len(self.status)
        self.start_refresh()
        result = self.result
        current, traffic, forecast, missing_location, commute_results, image = (
            result[3:] if result and result[:3] == (self.location, self.key, self.commute)
            else (None, None, (), False, (), None)
        )
        tick = monotonic()
        if self.page_start is None:
            self.page_start = tick
        loading = self.worker is not None and self.worker.is_alive()
        unavailable = tr("Updating…", "更新中…") if loading else tr("Unavailable", "暫無資料")
        traffic_page = int((tick - self.page_start) // 20) % 2
        forecast = forecast[1:]
        now = clock_time(self.time_zone, self.daylight_saving)
        icon = ("", "", "")
        weather_color = "2"
        weather_text = unavailable
        if current:
            description, icon, weather_color, _ = weather_display(current[1])
            weather_text = f"{current[0]:.0f}°C · {description}"
        if not self.location[0]:
            weather_text = tr("Set device location", "請設定設備地點")
        elif missing_location:
            weather_text = tr("Location not found", "找不到設定的城市")

        date = now.strftime("%Y-%m-%d · %Z")
        time = now.strftime("%H:%M:%S")
        large = height >= 15
        clock = large_clock(time) if large else [time]
        left_width = max(len(line) for line in clock) if large else width // 2 - 1
        right_width = width - left_width - 2
        today = tr("Today's weather", "今日天氣")
        location = ", ".join(part for part in self.location if part)
        weather = [today, *icon, weather_text, location] if large else [today, weather_text]
        lines = []
        for row, left in enumerate([*clock, date]):
            right = weather[row] if row < len(weather) else ""
            left_style = "1;37" if row == len(clock) else "1;36"
            lines.append((accent(fit_cells(left, left_width), left_style) + "  " +
                          accent(fit_cells(right, right_width), weather_color), None))
        if all(self.commute):
            outward, back = (f"{max(1, (route.travel + 59) // 60)} {tr('min', '分鐘')}" if route else "—"
                             for route in (commute_results + (None, None))[:2])
            summary = f"{tr('To work', '上班')} {outward} · {tr('Home', '下班')} {back}"
        else:
            summary = tr("Set commute addresses", "請設定通勤地址")
        lines.append((summary, "1;37"))
        if traffic_page:
            lines.extend(self.traffic_lines(width, height - len(lines), traffic, commute_results, image, unavailable))
            lines.extend([("", "2")] * max(0, height - len(lines)))
            return lines + list(self.status)
        if height - len(lines) > len(forecast):
            lines.append((tr("7-day forecast · °C / mm / km/h", "七天預報 · °C／mm／km/h"), "1;36"))
        if forecast:
            spare_rows = height - len(lines) - len(forecast)
            if spare_rows >= 2:
                lines.extend(forecast_icon_rows(forecast, max(1, (width - 3) // 7), spare_rows))
            for day in forecast:
                text, color = forecast_line(day, width)
                lines.append((text, color))
        else:
            lines.append((weather_text if missing_location or not self.location[0] else unavailable, "2"))
        lines.extend([("", "2")] * max(0, height - len(lines)))
        lines.extend(self.status)
        return lines
