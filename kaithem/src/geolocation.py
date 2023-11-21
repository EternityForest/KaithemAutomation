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
from . import directories, messagebus, config
from scullery import persist
from urllib.request import urlopen
import time
import json

import iot_devices.host


def ip_geolocate():
    # Block for a bit if its been less than a second since the last time we did this
    u = urlopen("http://ip-api.com/json", timeout=60)
    try:
        return (json.loads(u.read().decode('utf8')))
    finally:
        u.close()


fn = os.path.join(directories.vardir, "core.settings", "locations.toml")

if os.path.exists(fn):
    file = persist.load(fn)
else:
    file = {}

if config.config['location']:
    if not 'default' in file:
        file['default'] = {}
    latlon = config.config['location'].split(",")
    file['default']['lat'] = float(latlon[0].strip())
    file['default']['lon'] = float(latlon[1].strip())


def use_api_if_needed():
    if not 'default' in file:
        file['default'] = {}

    if not file['default'].get('lat', None) and not file['default'].get('lon', None):
        try:
            l = ip_geolocate()
            messagebus.post_message("/system/notifications/important",
                                    "Got server location by IP geolocation.  You can change this in settings.")
            file['default'] = l

            try:
                persist.save(file, fn, private=True)
            except Exception:
                logging.exception("Save fail")
        except Exception:
            logging.exception("IP Geolocation failed")


def getCoords():
    return file['default']['lat'], file['default']['lon']


def getLocation(l='default'):
    file['default'] = file.get('default', {})
    file['default']['lat'] = file['default'].get('lat', None)
    file['default']['lon'] = file['default'].get('lon', None)
    file['default']['city'] = file['default'].get('city', '')
    file['default']['timezone'] = file['default'].get('timezone', '')
    file['default']['regionName'] = file['default'].get('regionName', '')
    file['default']['countryCode'] = file['default'].get('countryCode', '')

    return file[l]


def setDefaultLocation(lat, lon, city='', timezone='', region='', country=''):
    if len(country) > 2:
        raise RuntimeError("not a valid ISO country code")
    country = country.upper()

    file['default'].clear()

    file['default']['lat'] = float(lat)
    file['default']['lon'] = float(lon)
    file['default']['city'] = str(city)
    file['default']['timezone'] = str(timezone)
    file['default']['countryCode'] = str(country)
    file['default']['regionName'] = str(region)

    persist.save(file, fn, private=True)


def deviceLocationGetter():
    return (file['default']['lat'], file['default']['lon'])


iot_devices.host.api['get_site_coordinates'] = deviceLocationGetter
