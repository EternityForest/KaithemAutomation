# Copyright Daniel Dunn 2018
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


from . import workers, config, util
from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf
import zeroconf
import socket

import time


import logging
import socket
import sys
import collections
import time
import ntplib
import re
import ntpserver

syslogger = logging.getLogger("system")


r = util.zeroconf

ntp_port = ntpserver.runServer(port=0)[1]

# Register an NTP service
desc = {}
localserver_name = "ntp"+str(config.config['ntpserver-priority'])+"_"+str(
    int(time.time()*1000000))+"-kaithem._ntp._udp.local."
info = zeroconf.ServiceInfo("_ntp._udp.local.",
                            localserver_name,
                            [None], ntp_port, 0, 0, desc)
r.register_service(info)


local_ntp_servers = collections.OrderedDict()
selected_server = None

time_ref = time.time()-time.monotonic()
ref_ts = time.time()
c = ntplib.NTPClient()

# Prioritize NTP servers in "ntp5500_1234567890-kaithem" style format.
# Otherwise sorting becomes less meaningful.


def sortkey(i):
    return (not re.match(r"ntp\d\d\d\d_\d*\-.*", i), i)


def on_service_state_change(zeroconf, service_type, name, state_change):
    global selected_server
    if state_change is ServiceStateChange.Added or ServiceStateChange.Updated:
        info = zeroconf.get_service_info(service_type, name)

        # Don't sync to servers that are lower priority than us,
        # we'll just continue using our local time.
        try:
            if info:
                # No excessive cache sizes
                if len(local_ntp_servers) > 8192:
                    local_ntp_servers.popitem(False)
                # Assume only one addr
                local_ntp_servers[name] = (socket.inet_ntoa(
                    info.addresses[0]), info.port, name)

                s = local_ntp_servers[sorted(
                    local_ntp_servers.keys(), key=sortkey)[0]]
                if sortkey(s[2]) < sortkey(localserver_name):
                    # Don't sync with ourself
                    if not s[0].startswith("127.0.0.1"):
                        if selected_server:
                            syslogger.warning(
                                "Selecting lantime server at " + str(s[0]) + ":"+str(s[1]))
                        else:
                            syslogger.info(
                                "Selecting lantime server at " + str(s[0]) + ":"+str(s[1]))
                        selected_server = s

        except:
            logging.exception("")

    elif state_change is ServiceStateChange.Removed:
        # we'll just continue using our local time.
        try:
            if info:
                # No excessive cache sizes
                if len(local_ntp_servers) > 8192:
                    local_ntp_servers.popitem(False)
                # Assume only one addr
                del local_ntp_servers[name]

                # Time to find another server
                # The rac condition doesn't matter that much really,
                # even if it was multithreaded.
                if selected_server:
                    if selected_server[2] == name:
                        if len(local_ntp_servers):
                            s = local_ntp_servers[sorted(
                                local_ntp_servers.keys(), key=sortkey)[0]]
                            if sortkey(s[2]) < sortkey(localserver_name):
                                selected_server = s
                                syslogger.warning(
                                    "Selected new lantime server at " + str(s[0]) + ":"+str(s[1]))
                                return
                # Couldn't select one
                selected_server = None
        except:
            logging.exception("")


browser = ServiceBrowser(r, "_ntp._udp.local.", handlers=[
                         on_service_state_change])


# Is using MDNS like this secure? Nope. Is it a whole lot worse than what you can already do by spoofing
# pool.ntp.org? Probably not. Don't let bad guys on your LAN and it's fine.

def sync(f=0.1):
    global time_ref, ref_point

    if selected_server:
        # Presend to wake up the device if it's in sleep mode
        c.request(socket.inet_ntoa(
            selected_server[0]), port=selected_server[1], version=3)
        t1 = time.monotonic()
        r = c.request(socket.inet_ntoa(
            selected_server[0]), port=selected_server[1], version=3)
        t2 = time.monotonic()
        # This is a LAN, so we expect tight tolerances here
        if (t2-t1) > 0.02:
            # At the halfway point between message and response, the time was the tx_timestamp.
            # Calculate a new time ref, and do some filtering.
            time_ref = time_ref*(1-f) + (r.tx_timestamp-(t2+t1)/2.0)*f
            ref_point = time.time()
        return time.monotonic()+time_ref


def getTime():
    "Gets the current network consenseus time."
    # If our time value is old, do a sync right away,
    # but do it in a background thread.
    if selected_server:
        if ref_point < time.time()-600:
            workers.do(sync)
        return time.monotonic()+time_ref
    else:
        # If no selected server, use time.time() directly
        # for the best accuracy.
        return time.time()


def getTimeOrLocal():
    # Try to use LAN time. But if that for some reason is off, then we use
    # local time
    t = getTime()
    tl = time.time()

    if abs(tl-t) > 100:
        return t
    else:
        return tl


def initial_sync():
    for i in range(1, 10):
        # Sync quickly at first, and progressively refine with more filtering
        sync(1.0/i)


# Don't mess up boot time too much
workers.do(initial_sync)
