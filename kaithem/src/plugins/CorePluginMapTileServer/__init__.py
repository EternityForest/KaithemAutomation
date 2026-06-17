# SPDX-License-Identifier: GPL-3.0-or-later

import io
import json
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


# Default layer configurations
DEFAULT_LAYERS = {
    "mapterhorn": {
        "type": "raster-dem",
        "tilejson": "3.0.0",
        "scheme": "xyz",
        "tiles": ["https://tiles.mapterhorn.com/{z}/{x}/{y}.webp"],
        "attribution": "<a href='https://mapterhorn.com/attribution'>© Mapterhorn</a>",  # noqa: E501
        "bounds": [-180, -85.0511287, 180, 85.0511287],
        "center": [0, 0, 6],
        "encoding": "terrarium",
        "tileSize": 512,
    },
    "openstreetmap": {
        "type": "raster",
        "name": "OpenStreetMap",
        "attribution": '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',  # noqa: E501
        "tiles": ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        "max_zoom": 19,
        "min_zoom": 0,
    },
    "opentopomap": {
        "type": "raster",
        "name": "OpenTopoMap",
        "attribution": '&copy; <a href="https://opentopomap.org">OpenTopoMap</a>',
        "tiles": [
            "https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
            "https://b.tile.opentopomap.org/{z}/{x}/{y}.png",
            "https://c.tile.opentopomap.org/{z}/{x}/{y}.png",
        ],
        "max_zoom": 17,
        "min_zoom": 0,
    },
    "usgs": {
        "type": "raster",
        "name": "USGS Imagery/Topo",
        "attribution": 'Tiles courtesy of the <a href="https://usgs.gov/">U.S. Geological Survey</a>',  # noqa: E501
        "tiles": [
            "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryTopo/MapServer/tile/{z}/{y}/{x}",
            "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}",
        ],
        "max_zoom": 16,
        "min_zoom": 0,
        "max_zoom_fallback": 16,
        "min_zoom_fallback": 9,
        "fallback_tiles": [
            "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}"
        ],
    },
}


def get_layers_config() -> dict:
    """Load layers config from file or return defaults."""
    config_path = os.path.join(directories.vardir, "maptiles", "layers.json")

    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass

    # Create default config if it doesn't exist
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(DEFAULT_LAYERS, f, indent=2)

    return DEFAULT_LAYERS


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


def _get_tile_urls_for_zoom(map_name: str, z: int) -> list[str]:
    """Get the appropriate tile URLs for a given zoom level."""
    layers = get_layers_config()
    layer = layers.get(map_name, DEFAULT_LAYERS.get("openstreetmap"))

    z = int(z)

    # Check for zoom-specific fallback
    max_zoom_fallback = layer.get("max_zoom_fallback", -1)
    min_zoom_fallback = layer.get("min_zoom_fallback", -1)

    # If we're in the fallback zoom range, use fallback URLs
    if min_zoom_fallback <= z <= max_zoom_fallback:
        fallback_urls = layer.get("fallback_tiles")
        if fallback_urls:
            return fallback_urls

    # Return primary URLs, shuffled for random load balancing
    urls = layer.get("tiles", [])
    random.shuffle(urls)
    return urls


async def get_tile(x, y, z, map="openstreetmap"):
    global approximate_tile_cache_size

    if os.path.isfile(get_fn(x, y, z, map)):
        return

    if os.path.isfile(get_avif_fn(x, y, z, map)):
        return

    if pages.canUserDoThis("system_admin", pages.getAcessingUser()):
        os.makedirs(os.path.dirname(get_fn(x, y, z, map)), exist_ok=True)

        # Get URLs to try (shuffled for random fallback order)
        urls = _get_tile_urls_for_zoom(map, z)

        # Try each URL in order until one works
        r = None
        last_error = None
        for url_template in urls:
            try:
                url = url_template.format(z=z, x=x, y=y)
                r = await fetch(url)
                break
            except Exception as e:
                last_error = e
                continue

        if r is None:
            raise last_error or ValueError(
                f"Failed to fetch tile from any URL for map {map}"
            )

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


@quart_app.app.route("/maptiles/tilejson")
async def serve_tilejson():
    """Serve TileJSON fragments for all configured layers."""

    layers = get_layers_config()
    result = {}

    for map_name, layer_config in layers.items():
        # Replace {z}/{x}/{y} in tile URLs with our internal tile server URL
        internal_tiles = [f"/maptiles/tile/{{z}}/{{x}}/{{y}}?map={map_name}"]

        tilejson = {
            "tilejson": "2.1.0",
            "name": layer_config.get("name", map_name),
            "attribution": layer_config.get("attribution", ""),
            "tiles": internal_tiles,
            "minzoom": layer_config.get("min_zoom", 0),
            "maxzoom": layer_config.get("max_zoom", 19),
            "type": layer_config.get("type", "raster"),
        }

        result[map_name] = tilejson

    return quart.jsonify(result)
