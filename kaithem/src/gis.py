import os
import random
import sqlite3
import threading
import time
import uuid
from typing import Optional

from . import widgets

api = widgets.APIWidget()
api.require("/users/map.view")
api.require_to_write("/users/map.edit")


def on_message(user, m):
    if m[0] == "get_all_points":
        con = get_con()
        cur = con.cursor()
        cur.execute("SELECT * FROM obj")

        rv = {}

        for i in cur:
            rv[i["id"]] = {
                "lat": i["lat"],
                "lon": i["lon"],
                "id": i["id"],
                "name": i["name"],
                "layer": i["layer"],
            }

        api.send(["all_points", rv])


api.attach(on_message)


class MapAPI:
    def __init__(self) -> None:
        pass


fn = "/dev/shm/" + os.getlogin() + "_kgis"

con = sqlite3.connect(fn)

cur = con.cursor()

cur.execute(
    "CREATE TABLE IF NOT EXISTS obj(id, layer, lat, lon, timestamp, expire, name, description, data)"
)
con.commit()

connections = threading.local()


def get_con():
    if not hasattr(connections, "con"):
        connections.con = sqlite3.connect(fn)
        connections.con.row_factory = sqlite3.Row

    return connections.con


def clean_old():
    con = get_con()
    con.cursor.execute(
        "DELETE FROM obj WHERE timestamp<?", (time.time() - 3600,)
    )
    con.commit()


class Waypoint:
    def __init__(
        self, lat=0, lon=0, id: Optional[str] = None, name="", layer="default"
    ) -> None:
        self.lat = lat
        self.lon = lon
        self.id = id or uuid


def set_waypoint(
    id: str, location: Optional[tuple], name="", description="", layer="default"
):
    con = get_con()
    if not location:
        con.cursor().execute("DELETE FROM obj WHERE id=?", (id))
    else:
        con.cursor().execute(
            "INSERT INTO obj VALUES (?,?,?,?,?,?,?,?,?)",
            (
                id,
                layer,
                location[0],
                location[1],
                time.time(),
                0,
                name,
                description,
                "{}",
            ),
        )
    con.commit()
    if random.random() > 100:
        clean_old()


set_waypoint("test", (122, 68), "test")
