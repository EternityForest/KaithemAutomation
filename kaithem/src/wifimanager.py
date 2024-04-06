# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import uuid
import weakref
import logging

from . import widgets, scheduling, tagpoints, workers

by_uuid = weakref.WeakValueDictionary()

log = logging.getLogger("system.wifi")


modes = {3: "AP", 2: "STA"}


wifi = tagpoints.Tag("/system/network/wifi_strength")
wifi.min = -1
wifi.max = 100
wifi.writable = False

wifi.description = "The strongest current WiFi connection, excluding AP mode. 1 to 100, -1 is never connected"
wifiClaim = wifi.claim(-1, "NetworkManager", 70)

# /if the value has ever been set, the signal is weak, and we don't have an ethernet connection.
# However, if there IS an ethernet connection, we still sound the alarm if the signal is weak but not nonexistent.
# Because in that case we know it should be connected but isn't
wifi.setAlarm(
    "LowSignal",
    "(value>-1) and (value < 20) and ((not tv('/system/network/ethernet')) or value)",
    auto_ack="yes",
)

ethernet = tagpoints.Tag("/system/network/ethernet")
ethernet.min = -1
ethernet.max = 1
ethernet.writable = False
ethernet.description = "Whether ethernet is connected, -1 is never connected"
ethernetClaim = ethernet.claim(-1, "NetworkManager", 70)
# if the value has ever been set, the signal is weak, and we don't have a WiFi connection.
# But even if we do have signal, we still want to warn if there was ethernet before but now is not,
# Because that would probably mean it is using wifi as a fallback and should still have ethernet.
wifi.setAlarm(
    "NoWiredNetwork",
    "(value>-1) and (value < 1) and not (tv('/system/network/wifi_strength') or (value > -1))",
    auto_ack="yes",
)

getAllDevicesAttempted = [0]


def get_connectionstatus():
    import nmcli

    nmcli.disable_use_sudo()

    strongest = 0
    eth = 0

    for dev in nmcli.device.wifi():
        if dev.in_use:
            s = dev.signal
            if s > strongest:
                strongest = s

    for dev in nmcli.device.status():
        if dev.device_type == "ethernet":
            if dev.connection:
                eth = 1

    # Don't overwrite "never connected" with a 0
    if (wifi.value > -1) or strongest:
        wifiClaim.set(strongest)

    if (ethernet.value > -1) or eth:
        ethernetClaim.set(eth)


def handleMessage(u, v):
    if v[0] == "refresh":
        api.send(["status", get_connectionstatus()])


try:
    import nmcli

    from . import util

    if not util.which("nmcli"):
        raise RuntimeError("nmcli binary not founfd")

    @scheduling.scheduler.every_minute
    def worker():
        try:
            api.send(["status", get_connectionstatus()])
        except Exception:
            log.exception("Error in WifiManager")

    workers.do(get_connectionstatus)

except Exception:
    log.exception("Could not use NetworkManager client. Network management disabled.")

api = widgets.APIWidget()
api.require("system_admin")
api.attach(handleMessage)
