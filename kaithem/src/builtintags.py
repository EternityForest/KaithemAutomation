
from src import kaithemobj, tagpoints


def civilTwilight():
    try:
        if kaithemobj.kaithem.isDark():
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
        if kaithemobj.kaithem.isNight():
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


def publicIP():
    try:
        import requests
        r = requests.get("http://api.ipify.org/", timeout=1)
        r.raise_for_status()
        return r.text
    except Exception:
        print(traceback.format_exc())
        return ""


ipTag = tagpoints.StringTag("/system/network/publicIP")
ipTag.interval = 3600
ipTag.description = "The current public IP address, as seen by http://api.ipify.org.  If the server is unreachable, will be the empty string."
ipTag.value = publicIP
