"""Compose TomTom raster map and live traffic tiles for Chafa."""

from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from io import BytesIO
from math import asinh, radians, tan, pi
import os
import re
import subprocess
from urllib.parse import urlencode
from urllib.request import urlopen

TILE_SIZE = 256
SGR = re.compile(r"\x1b\[[0-9;]*m")


def project(point, zoom):
    lat, lon = point
    scale = TILE_SIZE * (1 << zoom)
    lat = min(85.0511, max(-85.0511, lat))
    return (lon + 180) / 360 * scale, (1 - asinh(tan(radians(lat))) / pi) / 2 * scale


def traffic_map(points, key, routes=()):
    from PIL import Image, ImageDraw

    route_points = tuple(point for route in routes if route for point in route.points)
    width, height = TILE_SIZE, 160
    for zoom in range(13, 0, -1):
        pixels = [project(point, zoom) for point in (*points, *route_points)]
        xs, ys = zip(*pixels)
        world = TILE_SIZE * (1 << zoom)
        if max(xs) - min(xs) > world / 2:
            xs = tuple(x + world if x < world / 2 else x for x in xs)
        if max(xs) - min(xs) <= width - 36 and max(ys) - min(ys) <= height - 36:
            break
    left = round((min(xs) + max(xs) - width) / 2)
    top = min(world - height, max(0, round((min(ys) + max(ys) - height) / 2)))
    tiles = [(x, y) for x in range(left // TILE_SIZE, (left + width - 1) // TILE_SIZE + 1)
             for y in range(top // TILE_SIZE, (top + height - 1) // TILE_SIZE + 1)]

    def tile(path):
        with urlopen(f"https://api.tomtom.com/{path}?{urlencode({'key': key})}", timeout=5) as response:
            data = response.read(1_048_577)
        if len(data) > 1_048_576:
            raise ValueError("Oversized map tile")
        with Image.open(BytesIO(data), formats=("PNG",)) as image:
            if image.size != (TILE_SIZE, TILE_SIZE):
                raise ValueError("Unexpected map tile dimensions")
            return image.convert("RGBA")

    def composite(position):
        x, y = position
        suffix = f"{zoom}/{x % (1 << zoom)}/{y}.png"
        base = tile(f"map/1/tile/basic/night/{suffix}")
        flow = tile(f"traffic/map/4/tile/flow/relative/{suffix}")
        return Image.alpha_composite(base, flow)

    image = Image.new("RGBA", (width, height))
    with ThreadPoolExecutor(max_workers=4) as pool:
        for (x, y), layer in zip(tiles, pool.map(composite, tiles)):
            image.paste(layer, (x * TILE_SIZE - left, y * TILE_SIZE - top))
    draw = ImageDraw.Draw(image)
    pixels = [(x - left, y - top) for x, y in zip(xs, ys)]
    colors = ("#52ddff", "#db94ff")
    start = len(points)
    affected_paths = []
    for index, route in enumerate(routes):
        if route is None:
            continue
        path = pixels[start:start + len(route.points)]
        start += len(route.points)
        if len(path) < 2:
            continue
        draw.line(path, fill="#101722", width=8 if index == 0 else 5)
        draw.line(path, fill=colors[index], width=6 if index == 0 else 2)
        affected_paths.extend(path[first:last + 1] for first, last, _ in route.affected
                              if 0 <= first < last < len(path))
    for path in affected_paths:
        draw.line(path, fill="#ffa640", width=4)
    for (x, y), color in zip(pixels[:len(points)], colors):
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color, outline="white")
    output = BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()


@lru_cache(maxsize=4)
def render_traffic_map(image, width, height, color):
    colors = "256" if color else "none"
    try:
        result = subprocess.run(
            ["chafa", "--format=symbols", f"--colors={colors}", "--animate=off",
             "--probe=off", "--polite=on", "--stretch", f"--size={width}x{height}", "-"],
            input=image, capture_output=True, timeout=3, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    lines = result.stdout.decode("utf-8", errors="replace").splitlines()
    # Preserve only generated color sequences and printable glyphs.
    return tuple("".join(part if SGR.fullmatch(part) else "".join(filter(str.isprintable, part))
                         for part in re.split(f"({SGR.pattern})", line)) for line in lines[:height])
