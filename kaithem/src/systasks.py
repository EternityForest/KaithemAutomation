# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import time
import atexit
import sys
import platform
import re
import datetime
import threading
import weakref
import signal
import logging
import socket
import gc
import subprocess
import random
import cherrypy
from . import newevt, messagebus, unitsofmeasure, util, messagelogging, scheduling
from .kaithemobj import kaithem
from .config import config

from zeroconf import ServiceBrowser, ServiceStateChange


# very much not thread safe, doesn't matter, it's only for one UI page
httpservices = []
httplock = threading.Lock()


def on_service_state_change(zeroconf, service_type, name, state_change):
    with httplock:
        info = zeroconf.get_service_info(service_type, name)
        if not info:
            return
        if state_change is ServiceStateChange.Added:
            httpservices.append(
                (
                    tuple(sorted([socket.inet_ntoa(i) for i in info.addresses])),
                    service_type,
                    name,
                    info.port,
                )
            )
            if len(httpservices) > 2048:
                httpservices.pop(0)
        elif state_change is ServiceStateChange.Removed:
            try:
                httpservices.remove(
                    (
                        tuple(sorted([socket.inet_ntoa(i) for i in info.addresses])),
                        service_type,
                        name,
                        info.port,
                    )
                )
            except Exception:
                logging.exception("???")


# Not common enough to waste CPU all the time on
# browser = ServiceBrowser(util.zeroconf, "_https._tcp.local.", handlers=[ on_service_state_change])

browser2 = ServiceBrowser(
    util.zeroconf, "_http._tcp.local.", handlers=[on_service_state_change]
)


# Can't think of anywhere else to put this thing.
systemStarted = time.time()

logger = logging.getLogger("system")

lastsaved = time.time()


def getcfg():
    global saveinterval, dumplogsinterval, lastdumpedlogs
    if not config["autosave-state"] == "never":
        saveinterval = unitsofmeasure.time_interval_from_string(
            config["autosave-state"]
        )

    lastdumpedlogs = time.time()
    if not config["autosave-logs"] == "never":
        dumplogsinterval = unitsofmeasure.time_interval_from_string(
            config["autosave-logs"]
        )


getcfg()

lastgotip = time.time()

lastram = 0
lastramwarn = 0
lastpageviews = 0
pageviewsthisminute = 0
pageviewpublishcountdown = 1
nminutepagecount = 0


upnpMapping = None
syslogger = logging.getLogger("system")

import os
from . import persist, directories


def doUPnP():
    global upnpMapping
    upnpsettingsfile = os.path.join(
        directories.vardir, "core.settings", "upnpsettings.yaml"
    )

    upnpsettings = persist.getStateFile(upnpsettingsfile)
    p = upnpsettings.get("wan_port", 0)

    if p:
        try:
            lp = config["https-port"]
            from . import upnpwrapper

            upnpMapping = upnpwrapper.addMapping(
                p, "TCP", desc="KaithemAutomation web UI", register=True, WANPort=lp
            )
        except:
            syslogger.exception("Could not create mapping")
    else:
        # Going to let GC handle this
        upnpMapping = None
        gc.collect()


# This gets called when an HTML request is made.
def aPageJustLoaded():
    global pageviewsthisminute
    pageviewsthisminute = pageviewsthisminute + 1
    if config["log-http"]:
        messagebus.post_message(
            "/system/http/access",
            {"ip": cherrypy.request.remote.ip, "req": cherrypy.request.request_line},
            synchronous=True,
        )


# Acessed by stuff outide this file
pageviewcountsmoother = util.LowPassFiter(0.3)

MemUseWasTooHigh = False
firstrun = True
checked = False


# Allocate random chunks of memory, try to detect bit errors.
# We expect this to fire about once a year on normal systems.
# Randomize size so it can fit in fragmented places for max coverage, if ran for a very long time.
ramTestData = b""
lastRamTestValue = 0
bitErrorTestLock = threading.Lock()


@scheduling.scheduler.everyHour
def checkBitErrors():
    global ramTestData, lastRamTestValue
    with bitErrorTestLock:
        if not lastRamTestValue:
            for i in ramTestData:
                if not i == 0:
                    messagebus.post_message(
                        "/system/notifications/errors",
                        "RAM Bitflip 0>1 detected: val" + str(i),
                    )

            ramTestData = b"\xff" * int(1024 * 2048 * random.random())
            lastRamTestValue = 255

        else:
            for i in ramTestData:
                if not i == 255:
                    messagebus.post_message(
                        "/system/notifications/errors",
                        "RAM Bitflip 1>0 detected: val" + str(i),
                    )

            ramTestData = b"\0" * int(1024 * 2048 * random.random())
            lastRamTestValue = 0


try:
    monotonic = time.monotonic()
except:

    def monotonic():
        return "monotonic time not available"


time_last_minute = 0
rhistory = []


@scheduling.scheduler.everyMinute
def check_scheduler():
    "This is a continual built in self test for the scheduler"
    global rhistory
    rhistory.append((time.time(), time.monotonic()))
    rhistory = rhistory[-10:]
    global time_last_minute
    if time_last_minute:
        if time.time() - (time_last_minute) < 58:
            messagebus.post_message(
                "/system/notifications/warnings",
                "Kaithem has detected a scheduled event running too soon.  This tasks should run every 60s.  This error may indicate a 'catch up' event after high load. History:"
                + repr(rhistory),
            )
    time_last_minute = time.time()


@scheduling.scheduler.everyMinute
def logstats():
    global pageviewsthisminute, firstrun, checked
    global pageviewpublishcountdown, lastpageviews
    global MemUseWasTooHigh
    global lastram, nminutepagecount
    global lastramwarn
    # Do the page count
    nminutepagecount += pageviewsthisminute

    pageviewcountsmoother.sample(pageviewsthisminute)
    pageviewsthisminute = 0

    # Only log page views every ten minutes
    if (time.time() > lastpageviews + (60 * 30)) and nminutepagecount > 0:
        logger.info("Requests per minute: " + str(round(nminutepagecount / 30, 2)))
        lastpageviews = time.time()
        nminutepagecount = 0

    if platform.system() == "Linux":
        try:
            f = util.readfile("/proc/meminfo")
            total = int(re.search("MemTotal.*?([0-9]+)", f).group(1))
            free = int(re.search("MemFree.*?([0-9]+)", f).group(1))
            cache = int(re.search("Cached.*?([0-9]+)", f).group(1))

            usedp = round((1 - (free + cache) / float(total)), 3)
            total = round(total / 1024.0, 2)
            if (time.time() - lastram > (60 * 60)) or (
                (time.time() - lastram > 600) and usedp > 0.8
            ):
                logger.info("Total ram usage: " + str(round(usedp * 100, 1)))
                lastram = time.time()

            if usedp > config["mem-use-warn"]:
                if not MemUseWasTooHigh:
                    MemUseWasTooHigh = True
                    if time.time() - lastramwarn > 3600:
                        messagebus.post_message(
                            "/system/notifications/warnings",
                            "Total System Memory Use rose above "
                            + str(int(config["mem-use-warn"] * 100))
                            + "%",
                        )
                        lastramwarn = time.time()

            if usedp < (config["mem-use-warn"] - 0.08):
                MemUseWasTooHigh = False
        except Exception as e:
            raise e


def sd():
    messagebus.post_message("/system/shutdown", "System about to shut down or restart")
    messagebus.post_message(
        "/system/notifications/important", "System shutting down now"
    )


sd.priority = 25
atexit.register(sd)
cherrypy.engine.subscribe("stop", sd)


if time.time() < 1420070400:
    messagebus.post_message(
        "/system/notifications/errors",
        "System Clock is wrong, some features may not work properly.",
    )

if time.time() < util.min_time:
    messagebus.post_message(
        "/system/notifications/errors",
        "System Clock may be wrong, or time has been set backwards at some point. If system clock is correct and this error does not go away, you can fix it manually be correcting folder name timestamps in the var dir.",
    )
