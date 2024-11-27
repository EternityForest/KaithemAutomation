# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import os
import random

import niquests
import quart

from kaithem.src import directories, pages, quart_app


def get_fn(x, y, z, map="openstreetmap"):
    return os.path.join(directories.vardir, "maptiles", map, z, x, f"{y}.png")


async def fetch(f) -> bytes:
    async with niquests.AsyncSession() as s:
        r = await s.get(f)
        r.raise_for_status()
    assert r.content
    return r.content


async def get_tile(x, y, z, map="openstreetmap"):
    if pages.canUserDoThis("system_admin", pages.getAcessingUser()):
        if os.path.isfile(get_fn(x, y, z)):
            return

        os.makedirs(os.path.dirname(get_fn(x, y, z)), exist_ok=True)

        if map == "opentopomap":
            if random.random() > 0.5:
                r = fetch(f"https://b.tile.{map}.org/{{z}}/{{x}}/{{y}}.png")
            else:
                r = fetch(f"https://a.tile.{map}.org/{{z}}/{{x}}/{{y}}.png")
        else:
            r = fetch(f"https://tile.openstreetmap.org/{z}/{x}/{y}.png")

        r = await r
        with open(get_fn(x, y, z), "wb") as f:
            f.write(r)


@quart_app.app.route("/maptiles/tile/<z>/<x>/<y>.png")
async def serve_map_tile(z, x, y):
    map = quart.request.args.get("map", "openstreetmap")

    if pages.canUserDoThis("/users/maptiles.view", pages.getAcessingUser()):
        if os.path.exists(get_fn(x, y, z, map)):
            return await quart.send_file(get_fn(x, y, z, map))

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

        if os.path.exists(get_fn(x, y, z, map)):
            return await quart.send_file(get_fn(x, y, z, map))
    raise RuntimeError("No Tile Found")
