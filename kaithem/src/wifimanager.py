
import uuid
import weakref
import threading
import logging

from .import registry, widgets, scheduling, messagebus

by_uuid = weakref.WeakValueDictionary()

log = logging.getLogger("system.wifi")


modes = {
    3: 'AP',
    2: 'STA'
}


def matchIface(a, pattern):
    if pattern.endswith("*"):
        if a.startswith(pattern[:-1]):
            return True
    else:
        if a == pattern:
            return True


def getConnectionStatus():
    d = {}
    import NetworkManager
    try:
        devs = NetworkManager.NetworkManager.GetAllDevices()
        print("Err getting devices, using fallback")
    except:
        devs = NetworkManager.NetworkManager.GetDevices()

    for device in devs:
        if device.DeviceType == NetworkManager.NM_DEVICE_TYPE_WIFI:
            ap = device.ActiveAccessPoint
            if ap:
                # 2=WiFi STA
                d[device.Udi] = (ap.Ssid, 100 if (
                    not device.Mode == 2) else ap.Strength, modes.get(device.Mode, "UNKNOWN"))
            else:
                d[device.Udi] = ("", 0, "DISCONNECTED")
        else:
            d[device.Udi] = ("NOT_WIFI", 0, "UNKNOWN")

    return d

# def scanWeak():
#     d = {}
#     import NetworkManager
#     for device in NetworkManager.NetworkManager.GetAllDevices():
#         if  device.DeviceType ==  NetworkManager.NM_DEVICE_TYPE_WIFI:
#             ap = device.ActiveAccessPoint
#             if device.mode == 2:
#                 if ap.Strength< 30:
#                     pass
#     return d


class Connection():
    def __init__(self, ssid, psk, interface='', mode="sta", priority=50, id=None, addrs=''):
        import NetworkManager

        self.ssid = ssid
        self.psk = psk
        self.mode = mode
        self.priority = priority
        self.uuid = id or str(uuid.uuid4())
        self.interface = interface
        self.addrs = addrs

        try:
            NetworkManager.Settings.GetConnectionByUuid(self.uuid).Delete()
        except:
            pass

        if mode == 'adhoc':
            keymgt = 'wpa-none'
        if mode == 'ap' or mode == 'sta':
            keymgt = 'wpa-psk'

        authalg = ''
        if not psk:
            keymgt = 'none'
            authalg = "open"

        modes = {
            'ap': 'ap',
            'sta': 'infrastructure',
            'adhoc': 'adhoc'
        }

        def parseAddresses(a):
            v6 = []
            v4 = []

            for i in a.split(","):
                i = i.strip()
                if not i:
                    continue

                i = i.split("/")
                if len(i) > 1:
                    snlen = int(i[1])
                    addr = i[0]
                else:
                    addr = i[0]
                    snlen = 24
                if ":" in addr:
                    v6.append({"address": addr, "prefix": snlen})
                else:
                    v6.append({"address": addr, "prefix": snlen})
            return v4, v6

        v4, v6 = parseAddresses(addrs)

        # Give it a default address, so it actually works
        if mode == "ap" and not v4:
            v4 = [{"address": "10.0.0.1", "prefix": 24}]

        connection = {
            '802-11-wireless': {'mode': modes[mode],
                                'ssid': ssid},
            '802-11-wireless-security': {'key-mgmt': keymgt,
                                         'psk': psk,
                                         'group': ['ccmp'] if psk else [],
                                         },

            'connection': {'id': "temp:"+ssid,
                           'type': '802-11-wireless',
                           'uuid': self.uuid,
                           # Need this to make autoconnect work
                           'timestamp': 1234
                           },
            'ipv4': {'method': 'auto', "address-data": v4, 'dns': registry.get("system.wifi/v4_dns", [])},
            'ipv6': {'method': 'auto', 'address-data': v6, 'dns': registry.get("system.wifi/v6_dns", [])},
        }
        NetworkManager.Settings.AddConnection(connection)


def handleMessage(u, v):
    if v[0] == 'refresh':
        api.send(['connections', registry.get('system.wifi/connections', [])])
        api.send(['status', getConnectionStatus()])

    if v[0] == 'setConnectionParam':
        x = registry.get('system.wifi/connections', [])
        for i in x:
            if i['uuid'] == v[1]:
                i[v[2]] = v[3]
        x = list(reversed(sorted(x, key=lambda c: (
            c['priority'], c['interface'], c['uuid']))))
        registry.set('system.wifi/connections', x)
        api.send(['connections', registry.get('system.wifi/connections', [])])

    if v[0] == 'addConnection':
        c = {
            'ssid': '', 'mode': 'sta', 'psk': '', 'interface': '', 'priority': 50,
            'uuid': str(uuid.uuid4()), 'addrs': ''
        }
        x = registry.get('system.wifi/connections', [])
        x.append(c)
        registry.set('system.wifi/connections', x)
        api.send(['connections', registry.get('system.wifi/connections', [])])

    if v[0] == 'deleteConnection':
        x = registry.get('system.wifi/connections', [])
        x = [i for i in x if not i['uuid'] == v[1]]
        registry.set('system.wifi/connections', x)
        api.send(['connections', registry.get('system.wifi/connections', [])])


@scheduling.scheduler.everyMinute
def worker():

    # Don't bother if not configured
    if not registry.get('system.wifi/connections', []):
        return
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
