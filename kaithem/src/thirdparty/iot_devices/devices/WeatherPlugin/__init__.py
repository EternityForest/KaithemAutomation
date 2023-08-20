from iot_devices import device
from iot_devices import host

import os
import getpass
import requests
import time
import threading
import json

from urllib.parse import quote


cache = "/dev/shm/wttr.in.cache/" + getpass.getuser()
if not os.path.exists(cache):
    os.makedirs(cache)

# if not os.path.exists(os.path.expanduser("~/wttr.in/cache")):
#     os.makedirs(os.path.expanduser("~/wttr.in/"),exist_ok=True)
#     os.link(os.path.expanduser("~/wttr.in/cache"), d)


def fetch(url, cachetime=1 * 3600):
    fn = quote(url).replace("/", "%2F")
    fn = os.path.join(cache, fn)
    if os.path.exists(fn):
        t = os.stat(fn).st_mtime
        if t > (time.time() - cachetime):
            with open(fn) as f:
                return f.read()

    d = requests.get(url)
    d.raise_for_status()

    with open(fn, 'w') as f:
        f.write(d.text)

    return d.text


def getWeather(place, cachetime=1 * 3600):
    return json.loads(fetch("https://wttr.in/" + place + "?format=j1", cachetime))



class WeatherClient(device.Device):
    device_type = "WeatherClient"

    def __init__(self, name, data, **kw):
        device.Device.__init__(self, name, data, **kw)

        if 'get_site_coordinates' in host.api:
            lat, lon = host.api['get_site_coordinates']()
        else:
            lat, lon = 90, 135

        if lat == None or lon == None:
            lat, lon = 90, 135

        location = str(lat) + "," + str(lon)

        self.shouldRun = True
        self.set_config_default("device.location", location)
        self.set_config_default("device.update_minutes", "180")
        self.config_properties['device.update_interval'] = {
            'description': "Values below 90 minutes are ignored",
            'unit': 'minute'
        }

        def worker():
            while self.shouldRun:
                try:
                    self.update()
                except Exception:
                    self.handle_exception()
                time.sleep(3600)

        self.thread = threading.Thread(
            target=worker, name="WeatherFetcher", daemon=True)

        # Push type data point set by the device
        self.numeric_data_point(
            "temperature", unit="degC", min=-100, max=85, writable=False)
        self.numeric_data_point("humidity", unit="%",
                                min=0, max=100, writable=False)
        self.numeric_data_point("wind", unit="KPH",
                                min=0, max=100, writable=False)
        self.numeric_data_point("pressure", unit="millibar",
                                min=100, max=1100, writable=False)
        self.numeric_data_point("uv_index",
                                min=0, max=20, writable=False)
        self.thread.start()

    def update(self):
        w = getWeather(self.config['device.location'], max(int(self.config['device.update_minutes'].strip()), 90))
        w2 = w['current_condition'][0]
        self.set_data_point('temperature', w2['temp_C'])
        self.set_data_point('humidity', w2['humidity'])
        self.set_data_point('pressure', w2['pressure'])
        self.set_data_point('uv_index', w2['uvIndex'])

    def close(self):
        self.shouldRun = False
        return super().close()