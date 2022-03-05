# Copyright Daniel Dunn 2022
# This file is part of Kaithem Automation.

# Kaithem Automation is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.

# Kaithem Automation is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

import logging
import os
from src import directories, registry, messagebus
from scullery import persist
from urllib.request import urlopen
import time
import json

def ip_geolocate():
    # Block for a bit if its been less than a second since the last time we did this
    u = urlopen("http://ip-api.com/json", timeout=60)
    try:
        return(json.loads(u.read().decode('utf8')))

    finally:
        u.close()


fn = os.path.join(directories.vardir, "core.settings", "locations.toml")

if os.path.exists(fn):
    file = persist.load(fn)
else:
    file = {}

# Legacy registry stuff.
lat = registry.get("system/location/lat", None)
lon = registry.get("system/location/lon", None)

if 'default' in file:
    lat = file['default'].get('lat', None)
    lon = file['default'].get('lon', None)

if not lat or not lon:
    try:
        l = ip_geolocate()
        messagebus.postMessage("/system/notifications/important",
                               "Got server location by IP geolocation.  You can change this in settings.")
        file['default'] = l
    except:
        # The location called "default" is to be the main one.
        file['default'] = {
            'lat': lat,
            'lon': lon,
            'city': ''
        }
else:
    # The location called "default" is to be the main one.
    file['default'] = {
        'lat': lat,
        'lon': lon,
        'city': ''
    }

try:
    persist.save(file, fn, private=True)
except:
    logging.exception("Save fail")


def getCoords():
    return file['default']['lat'], file['default']['lon']


def getLocation(l):
    file['default']=file.get('default',{})
    file['default']['lat'] = file['default'].get('lat',None)
    file['default']['lon'] = file['default'].get('lon',None)
    file['default']['city'] = file['default'].get('city','')

    return file['default']

def setDefaultLocation(lat, lon, city=''):
    file['default']['lat'] = float(lat)
    file['default']['lon'] = float(lon)
    file['default']['city'] = str(city)

    persist.save(file, fn, private=True)
