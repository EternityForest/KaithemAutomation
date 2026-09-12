# SPDX-License-Identifier: GPL-3.0-or-later

import os

import niquests
from scullery import persist

from . import config, directories


def nominatim_geolocate(location):
    """Search for a place by name using OpenStreetMap's Nominatim service.

    Returns the most likely (first) match as a dict using the same keys as
    the rest of this module.
    """
    u = niquests.get(
        "https://nominatim.openstreetmap.org/search",
        params={
            "q": location,
            "format": "json",
            "addressdetails": 1,
            "limit": 1,
        },
        # Nominatim's usage policy requires an identifying User-Agent.
        headers={"User-Agent": "Kaithem (home automation system)"},
        timeout=15,
    )
    u.raise_for_status()

    try:
        results = u.json()

        if not results:
            raise RuntimeError(f"No location found for {location!r}")

        d = results[0]
        address = d.get("address", {})

        r = {}
        r["lat"] = float(d["lat"])
        r["lon"] = float(d["lon"])
        r["city"] = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("hamlet")
            or address.get("municipality")
            or ""
        )
        # Nominatim does not provide a timezone.
        r["timezone"] = ""
        r["regionName"] = (
            address.get("state")
            or address.get("state_district")
            or address.get("county")
            or ""
        )
        r["countryCode"] = (address.get("country_code") or "").upper()

        return r
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
    # Location is no longer guessed automatically. The user is prompted to
    # search for a location from the settings page instead.
    if "default" not in file:
        file["default"] = {}


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
