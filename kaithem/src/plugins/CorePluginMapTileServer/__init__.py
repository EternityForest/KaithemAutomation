# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import io
import os
import random
import threading
import time

import niquests
import PIL
import quart
from scullery import scheduling

from kaithem.api import settings
from kaithem.src import directories, pages, quart_app


def get_fn(x, y, z, map="openstreetmap"):
    return os.path.join(directories.vardir, "maptiles", map, z, x, f"{y}.png")


def get_avif_fn(x, y, z, map="openstreetmap"):
    return os.path.join(directories.vardir, "maptiles", map, z, x, f"{y}.avif")


async def fetch(f) -> bytes:
    async with niquests.AsyncSession() as s:
        r = await s.get(f)
        r.raise_for_status()
    assert r.content
    return r.content


approximate_tile_cache_size = 0


def get_tile_cache_size() -> int:
    global approximate_tile_cache_size
    total = 0

    for root, dirs, files in os.walk(
        os.path.join(directories.vardir, "maptiles")
    ):
        for f in files:
            full = os.path.join(root, f)
            total += os.path.getsize(full)

    approximate_tile_cache_size = total
    return total


def delete_old_tiles(days, max_cache_size=10**9):
    """Delete tiles that are older than days, stopping
    when the cache size is less than max_cache_size.
    """
    global approximate_tile_cache_size
    get_tile_cache_size()

    for root, dirs, files in os.walk(
        os.path.join(directories.vardir, "maptiles"), topdown=False
    ):
        for f in files:
            full = os.path.join(root, f)
            if os.path.getatime(full) < time.time() - days * 24 * 60 * 60:
                approximate_tile_cache_size -= os.path.getsize(full)
                os.remove(full)

                if approximate_tile_cache_size < max_cache_size:
                    break
        for d in dirs:
            full = os.path.join(root, d)
            if not os.listdir(full):
                os.rmdir(full)


def clean():
    cache_size = (
        settings.get_val("core_plugin_map_tile_server/cache_size_mb") or 1024
    )
    max_age = (
        settings.get_val("core_plugin_map_tile_server/max_age_days") or 100
    )
    cache_size = int(cache_size)

    # Can't do any less because we use 3 month relatime resolution
    max_age = max(int(max_age), 100)

    delete_old_tiles(max_age, cache_size * 1024 * 1024)


t = threading.Thread(target=clean, daemon=True, name="CleanOldMapTiles")
t.start()

# Run every 3 months
schedule = scheduling.scheduler.every(clean, 60 * 60 * 24 * 30 * 3)


async def get_tile(x, y, z, map="openstreetmap"):
    global approximate_tile_cache_size

    if os.path.isfile(get_fn(x, y, z, map)):
        return

    if os.path.isfile(get_avif_fn(x, y, z, map)):
        return

    if pages.canUserDoThis("system_admin", pages.getAcessingUser()):
        os.makedirs(os.path.dirname(get_fn(x, y, z, map)), exist_ok=True)

        if map == "opentopomap":
            if random.random() > 0.5:
                r = fetch(f"https://b.tile.{map}.org/{z}/{x}/{y}.png")
            else:
                r = fetch(f"https://a.tile.{map}.org/{z}/{x}/{y}.png")
            r = await r

        elif map == "usgs":
            if int(z) > 16:
                raise ValueError("USGS only supports up to zoom level 16")
            if int(z) < 9:
                r = fetch(
                    f"https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}"
                )
                r = await r

            else:
                try:
                    r = fetch(
                        f"https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryTopo/MapServer/tile/{z}/{y}/{x}"
                    )
                    r = await r
                except Exception:
                    r = fetch(
                        f"https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}"
                    )
                    r = await r

        else:
            r = fetch(f"https://tile.openstreetmap.org/{z}/{x}/{y}.png")
            r = await r

        fn = get_fn(x, y, z, map)
        if os.path.exists(fn):
            approximate_tile_cache_size -= os.path.getsize(fn)

        with open(get_fn(x, y, z, map), "wb") as f:
            f.write(r)
            approximate_tile_cache_size += len(r)


@quart_app.app.route("/maptiles/tile/<z>/<x>/<y>")
@quart_app.app.route("/maptiles/tile/<z>/<x>/<y>.png")
async def serve_map_tile(z, x, y):
    map = quart.request.args.get("map", "openstreetmap")

    if pages.canUserDoThis("/users/maptiles.view", pages.getAcessingUser()):
        if os.path.exists(get_fn(x, y, z, map)):
            return await quart.send_file(get_fn(x, y, z, map))

        if os.path.exists(get_avif_fn(x, y, z, map)):
            img = PIL.Image.open(get_avif_fn(x, y, z, map))
            b = io.BytesIO()
            img.save(b, format="png")
            return quart.Response(b.getvalue(), mimetype="image/png")

        if os.path.exists(
            os.path.join(
                os.path.expanduser(f"~/.local/share/marble/maps/earth/{map}"),
                z,
                x,
                y,
            )
        ):
            return await quart.send_file(
                os.path.join(
                    os.path.expanduser(
                        f"~/.local/share/marble/maps/earth/{map}"
                    ),
                    z,
                    x,
                    y,
                )
            )

        if os.path.exists(
            os.path.join(
                f"/home/pi/.local/share/marble/maps/earth/{map}", z, x, y
            )
        ):
            return await quart.send_file(
                os.path.join(f"/home/pi/share/marble/maps/earth/{map}", z, x, y)
            )

        await get_tile(x, y, z, map)

        fn = get_fn(x, y, z, map)
        if os.path.exists(get_fn(x, y, z, map)):
            # Assume a noatime system, so update times every three months
            three_months = 60 * 60 * 24 * 30 * 3
            if os.path.getatime(fn) < time.time() - three_months:
                mtime = os.path.getmtime(fn)
                os.utime(fn, times=(time.time(), mtime))

            return await quart.send_file(get_fn(x, y, z, map))
    raise RuntimeError("No Tile Found")
