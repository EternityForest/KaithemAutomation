import logging
from . import kaithemobj, tagpoints, alerts, messagebus
import traceback
import time
import json
import os


refs = []

log = logging.getLogger("system")

def create():
    def civilTwilight():
        try:
            if kaithemobj.kaithem.time.isDark():
                return 1
            else:
                return 0
        except Exception:
            return -1

    twilightTag = tagpoints.Tag("/sky/civilTwilight")
    twilightTag.min = -1
    twilightTag.max = 1
    twilightTag.interval = 60
    twilightTag.description = (
        "Unless overridden, 1 if dark, else 0, -1 if no location is set"
    )
    twilightTag.value = civilTwilight
    refs.append(twilightTag)

    alertTag = tagpoints.Tag("/system/alerts.level")
    alertTag.description = (
        "The level of the highest priority alert that is currently not acknowledged"
    )
    alertTag.writable = False
    alertTag.min = 0
    alertTag.max = alerts.priorities["critical"]
    refs.append(alertTag)

    def atm(t, v):
        alertTag.value = alerts.priorities[v]

    refs.append(atm)

    messagebus.subscribe("/system/alerts/level", atm)
    alertTag.value = alerts.priorities[alerts._highestUnacknowledged()]

    def night():
        try:
            if kaithemobj.kaithem.time.isNight():
                return 1
            else:
                return 0
        except Exception:
            return -1

    nTag = tagpoints.Tag("/sky/night")
    nTag.min = -1
    nTag.max = 1
    nTag.interval = 60
    nTag.description = "Unless overridden, 1 if night, else 0, -1 if no location is set"
    nTag.value = night
    refs.append(night)
    refs.append(nTag)

    ipTag = tagpoints.StringTag("/system/network/publicIP")
    refs.append(ipTag)

    def publicIP():
        try:
            # This is here for development, where one might be rapidly starting and stopping
            try:
                if os.path.exists("/dev/shm/KaithemCachedPublicIP.json"):
                    with open("/dev/shm/KaithemCachedPublicIP.json") as f:
                        j = json.load(f)
                        if j["time_monotonic"] > time.monotonic() - 1800:
                            return j["ip"]
            except Exception:
                log.exception("Err loading cache file")

            import requests

            r = requests.get("http://api.ipify.org/", timeout=15)
            r.raise_for_status()

            try:
                with open("/dev/shm/KaithemCachedPublicIP.json", "w") as f:
                    json.dump({"ip": r.text, "time_monotonic": time.monotonic()}, f)
            except Exception:
                log.exception("Err saving cache file")

            ipTag.interval = 3600
            return r.text

        except Exception:
            ipTag.interval = 300
            print(traceback.format_exc())
            return ""

    refs.append(publicIP)

    ipTag.interval = 3600
    ipTag.description = "The current public IP address, as seen by http://api.ipify.org.  If the server is unreachable, will be the empty string. Default interval is dynamic, 1 hour once succeeded."
    ipTag.value = publicIP


# Probably best not to automatically do anything that could cause IP traffic?
# ipTag.setAlarm("NoInternetAccess", condition="not value")
