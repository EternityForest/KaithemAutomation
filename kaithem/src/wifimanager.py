
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
wifi.min=-1
wifi.max=100

wifi. description = "The strongest current WiFi connection, excluding AP mode. 1 to 100, -1 is never connected"
wifiClaim = wifi.claim(-1, "NetworkManager", 70)

#/if the value has ever been set, the signal is weak, and we don't have an ethernet connection.
#However, if there IS an ethernet connection, we still sound the alarm if the signal is weak but not nonexistent.
#Because in that case we know it should be connected but isn't
wifi.setAlarm("LowSignal", "(value>-1) and (value < 20) and ((not tv('/system/ethernet')) or value)", autoAck='yes')

ethernet = tagpoints.Tag(
    "/system/ethernet")
ethernet.min=-1
ethernet.max = 1
ethernet. description = "Whether ethernet is connected, -1 is never connected"
ethernetClaim = wifi.claim(-1, "NetworkManager", 70)
#if the value has ever been set, the signal is weak, and we don't have a WiFi connection.
#But even if we do have signal, we still want to warn if there was ethernet before but now is not,
#Because that would probably mean it is using wifi as a fallback and should still have ethernet.
wifi.setAlarm("NoWiredNetwork", "(value>-1) and (value < 1) and not (tv('/system/wifiStrength') or (value > -1))", autoAck='yes')

def getConnectionStatus():

    d = {}
    import NetworkManager
    try:
        devs = NetworkManager.NetworkManager.GetAllDevices()
        print("Err getting devices, using fallback")
    except:
        devs = NetworkManager.NetworkManager.GetDevices()

    strongest = 0
    eth = 0
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
                    eth=1

                else:
                    d[device.Udi] = (device.Interface, 0, "UNKNOWN")

            else:
                d[device.Udi] = ("NOT_WIFI", 100, "UNKNOWN")
        except:
            logging.exception("Err in wifi manager")


    #Don't overwrite "never connected" with a 0
    if (wifi.value>-1) or strongest:
        wifiClaim.set(strongest)

    if (ethernet.value>-1) or eth:
        ethernetClaim.set(eth)
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
