# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import atexit
import logging
import platform
import re
import socket
import threading
import time

import quart
import scullery.workers
import structlog
from scullery import scheduling
from zeroconf import ServiceBrowser, ServiceStateChange

from . import messagebus, unitsofmeasure, util
from .config import config

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
                    tuple(
                        sorted([socket.inet_ntoa(i) for i in info.addresses])
                    ),
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
                        tuple(
                            sorted(
                                [socket.inet_ntoa(i) for i in info.addresses]
                            )
                        ),
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

logger = structlog.get_logger(__name__)

lastsaved = time.time()


def getcfg():
    global saveinterval, dumplogsinterval, lastdumpedlogs
    if not config["autosave_state"] == "never":
        saveinterval = unitsofmeasure.time_interval_from_string(
            config["autosave_state"]
        )

    lastdumpedlogs = time.time()
    if not config["autosave_logs"] == "never":
        dumplogsinterval = unitsofmeasure.time_interval_from_string(
            config["autosave_logs"]
        )


getcfg()

lastgotip = time.time()

lastram = 0
lastramwarn = 0
lastpageviews = 0
pageviewsthisminute = 0
pageviewpublishcountdown = 1
nminutepagecount = 0

logger = structlog.get_logger(__name__)


# This gets called when an HTML request is made.
def aPageJustLoaded():
    global pageviewsthisminute
    pageviewsthisminute = pageviewsthisminute + 1
    if config["log_http"]:
        messagebus.post_message(
            "/system/http/access",
            {"ip": quart.request.remote.ip, "req": quart.request.request_line},
            synchronous=True,
        )


# Acessed by stuff outide this file
pageviewcountsmoother = util.LowPassFiter(0.3)

MemUseWasTooHigh = False
firstrun = True
checked = False


time_last_minute = 0
rhistory = []


@scheduling.scheduler.every_minute
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
                """Kaithem has detected a scheduled event running
                  too soon.  This tasks should run every 60s.
                  This error may indicate a 'catch up' event
                  after high load. History:"""
                + repr(rhistory),
            )
    time_last_minute = time.time()


@scheduling.scheduler.every_minute
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
        logger.info(
            f"Requests per minute: {str(round(nminutepagecount / 30, 2))}"
        )
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
                logger.info(f"Total ram usage: {str(round(usedp * 100, 1))}")
                lastram = time.time()

            if usedp > config["mem_use_warn"]:
                if not MemUseWasTooHigh:
                    MemUseWasTooHigh = True
                    if time.time() - lastramwarn > 3600:
                        messagebus.post_message(
                            "/system/notifications/warnings",
                            "Total System Memory Use rose above "
                            + str(int(config["mem_use_warn"] * 100))
                            + "%",
                        )
                        lastramwarn = time.time()

            if usedp < (config["mem_use_warn"] - 0.08):
                MemUseWasTooHigh = False
        except Exception as e:
            raise e


def stop_workers(*a):
    scullery.workers.stop()


messagebus.subscribe("/system/shutdown", stop_workers)


def sd():
    messagebus.post_message(
        "/system/shutdown", "System about to shut down or restart"
    )
    messagebus.post_message(
        "/system/notifications/important", "System shutting down now"
    )


sd.priority = 25
atexit.register(sd)


if time.time() < 1420070400:
    messagebus.post_message(
        "/system/notifications/errors",
        "System Clock is wrong, some features may not work properly.",
    )

if time.time() < util.min_time:
    messagebus.post_message(
        "/system/notifications/errors",
        """System Clock may be wrong, or time has been set backwards at some point.""",
    )
