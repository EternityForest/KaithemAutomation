
import uuid
import weakref
import logging

from .import widgets, scheduling, tagpoints

by_uuid = weakref.WeakValueDictionary()

log = logging.getLogger("system.wifi")


modes = {
    3: 'AP',
    2: 'STA'
}


wifi = tagpoints.Tag(
    "/system/wifiStrength")
wifi. description = "The strongest current WiFi connection, excluding AP mode. -1 if never connected, 100 full strength"
wifiClaim = wifi.claim(-1, "NetworkManager", 70)
wifi.setAlarm("LowSignal", "value < 20 and value > -1", autoAck='yes')


def getConnectionStatus():
    d = {}
    import NetworkManager
    try:
        devs = NetworkManager.NetworkManager.GetAllDevices()
        print("Err getting devices, using fallback")
    except:
        devs = NetworkManager.NetworkManager.GetDevices()

    strongest = 0
    for device in devs:
        try:
            if device.DeviceType == NetworkManager.NM_DEVICE_TYPE_WIFI:
                ap = device.ActiveAccessPoint
                if ap:
                    # 2=WiFi STA
                    d[device.Udi] = (ap.Ssid, 100 if (
                        not device.Mode == 2) else ap.Strength, modes.get(device.Mode, "UNKNOWN"))

                    if device.Mode == 2:
                        s = ap.Strength
                        if s > strongest:
                            strongest = s

                else:
                    d[device.Udi] = ("", 0, "DISCONNECTED")

            elif device.DeviceType == NetworkManager.NM_DEVICE_TYPE_ETHERNET:
                if device.State == NetworkManager.NM_DEVICE_STATE_DISCONNECTED:
                    d[device.Udi] = (device.Interface, 0, "DISCONNECTED")

                if device.State == NetworkManager.NM_DEVICE_STATE_ACTIVATED:
                    d[device.Udi] = (device.Interface, 0, "CONNECTED")

                else:
                    d[device.Udi] = (device.Interface, 0, "UNKNOWN")

            else:
                d[device.Udi] = ("NOT_WIFI", 100, "UNKNOWN")
        except:
            logging.exception("Err in wifi manager")

    wifiClaim.set(strongest)

    return d


def handleMessage(u, v):
    if v[0] == 'refresh':
        api.send(['status', getConnectionStatus()])


@scheduling.scheduler.everyMinute
def worker():

    # Don't bother if not configured
    try:
        import NetworkManager
    except:
        log.exception(
            "Could not import NetworkManager. Network management disabled.")
        return

    try:
        api.send(['status', getConnectionStatus()])
    except:
        log.exception("Error in WifiManager")


api = widgets.APIWidget()
api.require("/admin/settings.edit")
api.attach(handleMessage)
