# SPDX-FileCopyrightText: Copyright 2019 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

# This file runs a self test when python starts. Obviously we do
# Not want to clutter up the rraw

import logging
import os
import sys
import threading
import time
import traceback

import structlog
from scullery import messagebus


def memtest():
    "Test a small segment of memory. Possibly enought to know if it's really messed up"
    for i in range(5):
        x = os.urandom(128)

        x1 = list(x * 1024 * 128)
        x2 = list(x * 1024 * 128)
        # Wait a bit, in case it's a time retention thing
        time.sleep(1)
        if not x1 == x2:
            messagebus.post_message("/system/notifications/errors", "Memory may be corrupt")


def mathtest():
    import random

    old = -1
    for i in range(256):
        if not i > old:
            raise RuntimeError("Numbers appear to have been redefined or something")
        if not i - 1 == old:
            raise RuntimeError("Numbers appear to have been redefined or something")

        old = i

    for i in range(1, 1024):
        x = 1 / i

        r = max(random.random(), 0.1)
        x2 = ((i * i) / i) * 5000 * r
        x2 = x2 / 5000
        x2 = x2 / r
        x2 = (2 / x2) / 2

        if not abs(x - x2) < 0.001:
            raise RuntimeError("Floating point numbers seem to have an issue")

    if False:
        raise RuntimeError("If False should never run")


def netTest():
    "BUGGY, NOT READY,"
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s2.bind(("", 18552))
    except Exception:
        # Prob just port not free
        s.close()
        s2.close()
        return

    s.settimeout(3)
    x = 1
    while x:
        s.sendto(b"test", ("127.0.0.1", 18552))
        s.sendto(b"test", ("127.0.0.1", 18552))
        s.sendto(b"test", ("127.0.0.1", 18552))
        s.sendto(b"test", ("127.0.0.1", 18552))
        s.sendto(b"test", ("127.0.0.1", 18552))
        s.sendto(b"test", ("127.0.0.1", 18552))
        try:
            x, addr = s.recvfrom()
            if x == b"test":
                s.close()
                s2.close()
                return
        except Exception:
            # Cach timeouts
            x = 0
    s.close()
    s2.close()
    raise RuntimeError("UDP Loopback networking doesn't seem to work")


def runtest():
    from .. import messagebus

    try:
        from . import (
            eventsystem,
            messagebustest,
            statemachinestest,
            tagpointstest,
            testpersist,
        )

        logging.info("Beginning self test")
        eventsystem.eventSystemTest()
        statemachinestest.stateMachinesTest()
        messagebustest.test()
        tagpointstest.testTags()
        testpersist.test()
        mathtest()
        # netTest()
        t = threading.Thread(target=memtest, daemon=True)
        t.daemon = True
        t.start()
        logging.info("Self test was sucessful")
    except Exception:
        messagebus.post_message(
            "/system/notifications/errors",
            "Self Test Error\n" + traceback.format_exc(chain=True),
        )
    finally:
        pass


# Don't add confusion with the real unit tests
if "pytest" not in sys.modules:
    t = threading.Thread(daemon=True, name="KaithemBootSelfTest", target=runtest)
    t.start()
