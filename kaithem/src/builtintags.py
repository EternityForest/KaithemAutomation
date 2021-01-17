
from src import kaithemobj, tagpoints
import traceback


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
twilightTag.description = "Unless overridden, 1 if dark, else 0, -1 if no location is set"
twilightTag.value = civilTwilight


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

ipTag = tagpoints.StringTag("/system/network/publicIP")


def publicIP():
    try:
        import requests
        r = requests.get("http://api.ipify.org/", timeout=15)
        r.raise_for_status()
        ipTag.interval = 3600
        return r.text
    except Exception:
        ipTag.interval = 300
        print(traceback.format_exc())
        return ""


ipTag.interval = 3600
ipTag.description = "The current public IP address, as seen by http://api.ipify.org.  If the server is unreachable, will be the empty string. Default interval is dynamic, 1 hour once succeeded."
ipTag.value = publicIP
