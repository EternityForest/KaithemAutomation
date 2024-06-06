# SPDX-FileCopyrightText: Copyright 2022 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import json
import logging
import os
from urllib.request import urlopen

import iot_devices.host
from scullery import persist

from . import config, directories, messagebus


def ip_geolocate():
    # Block for a bit if its been less than a second since the last time we did this
    u = urlopen("http://ip-api.com/json", timeout=60)
    try:
        return json.loads(u.read().decode("utf8"))
    finally:
        u.close()


fn = os.path.join(directories.vardir, "core.settings", "locations.toml")

if os.path.exists(fn):
    file = persist.load(fn)
else:
    file = {}

if config.config["location"]:
    if "default" not in file:
        file["default"] = {}
    latlon = config.config["location"].split(",")
    file["default"]["lat"] = float(latlon[0].strip())
    file["default"]["lon"] = float(latlon[1].strip())


def use_api_if_needed():
    if "default" not in file:
        file["default"] = {}

    if not file["default"].get("lat", None) and not file["default"].get("lon", None):
        try:
            location = ip_geolocate()
            messagebus.post_message(
                "/system/notifications/important",
                "Got server location by IP geolocation.  You can change this in settings.",
            )
            file["default"] = location

            try:
                persist.save(file, fn, private=True)
            except Exception:
                logging.exception("Save fail")
        except Exception:
            logging.exception("IP Geolocation failed")


def getCoords():
    return file["default"]["lat"], file["default"]["lon"]


def getLocation(location="default"):
    file["default"] = file.get("default", {})
    file["default"]["lat"] = file["default"].get("lat", None)
    file["default"]["lon"] = file["default"].get("lon", None)
    file["default"]["city"] = file["default"].get("city", "")
    file["default"]["timezone"] = file["default"].get("timezone", "")
    file["default"]["regionName"] = file["default"].get("regionName", "")
    file["default"]["countryCode"] = file["default"].get("countryCode", "")

    return file[location]


def setDefaultLocation(lat, lon, city="", timezone="", region="", country=""):
    if len(country) > 2:
        raise RuntimeError("not a valid ISO country code")
    country = country.upper()

    file["default"].clear()

    file["default"]["lat"] = float(lat)
    file["default"]["lon"] = float(lon)
    file["default"]["city"] = str(city)
    file["default"]["timezone"] = str(timezone)
    file["default"]["countryCode"] = str(country)
    file["default"]["regionName"] = str(region)

    persist.save(file, fn, private=True)


def deviceLocationGetter():
    return (file["default"]["lat"], file["default"]["lon"])


iot_devices.host.api["get_site_coordinates"] = deviceLocationGetter
