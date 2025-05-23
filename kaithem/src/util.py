# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-or-later

import datetime
import difflib
import getpass
import hashlib
import os
import re
import reprlib
import stat
import struct
import sys
import threading
import time
import types
import weakref
from typing import Iterable, List
from urllib.parse import quote
from urllib.parse import unquote as unurl  # noqa
from urllib.request import urlopen  # noqa

import dateutil.rrule
import recurrent
import structlog
import zeroconf


def align_dtsart_for_rrule(dt: datetime.datetime, rrule: str):
    """Get rid of stuff in the dt that is't in the rrule, so 2:30pm starts at exactly 2:30 not
    some seconds after"""

    if "BYSECOND" not in rrule:
        dt = dt.replace(second=0, microsecond=0)

    if "BYMINUTE" not in rrule:
        dt = dt.replace(minute=0)

    if "BYHOUR" not in rrule:
        dt = dt.replace(hour=0)

    if "BYDAY" not in rrule:
        dt = dt.replace(day=1)

    if "BYMONTH" not in rrule:
        dt = dt.replace(month=1)

    return dt


def validate_selector(rule: dateutil.rrule.rrule):
    for i in [
        "easter",
        "hour",
        "minute",
        "month",
        "monthday",
        "weekday",
        "year",
        "second",
        "weekno",
        "yearday",
        "nweekday",
        "nmonthday",
    ]:
        propname = "_by" + i
        if hasattr(rule, propname):
            val = getattr(rule, propname)
            if val is not None:
                return True

    raise ValueError("Invalid selector, it might cause an infinite loop")


def get_rrule_selector(s: str, ref: datetime.datetime | None = None):
    """
    Given a natural expression like every tuesday get a dateutil rrule obj.
    Has the old recur behavior or something like ir
    """

    if "second" in s.lower():
        raise ValueError("Seconds not supported due to slowing down the sys")
    s = s.replace("noon", "12pm")
    s = s.replace("midnight", "12am")

    if re.search(r"\d\d:\d\d:\d\d", s):
        raise ValueError(
            "Times with seconds would not work right with parser library."
        )

    ref = ref or datetime.datetime.now()

    r = recurrent.RecurringEvent(now_date=ref)
    r.parse(s)

    if not r.is_recurring:
        try:
            r = recurrent.RecurringEvent(now_date=ref)
            for i in ("every day at ", "every year on "):
                r.parse(i + s)
                rule = r.get_RFC_rrule()
                if rule:
                    d = datetime.datetime.now()
                    # Something was an issue where without this it didn't
                    # Return correct vals...
                    d -= datetime.timedelta(weeks=52 + 3)  # noqa

                    d = align_dtsart_for_rrule(d, rule)

                    selector = dateutil.rrule.rrulestr(rule, dtstart=d)
                    validate_selector(selector)
                    return selector
            raise Exception()

        except Exception:
            # Couldn't get it to give us a valid rule,
            # Must be a one time event selector
            r = recurrent.RecurringEvent(now_date=ref)
            dt = r.parse(s)
            selector = dateutil.rrule.rrule(
                freq=dateutil.rrule.YEARLY, dtstart=dt, count=1
            )
            selector._dtstart -= datetime.timedelta(weeks=52 + 3)  # noqa
            validate_selector(selector)

            return selector

    rule = r.get_RFC_rrule()
    selector = dateutil.rrule.rrulestr(rule)
    selector._dtstart -= datetime.timedelta(weeks=52 + 3)  # noqa
    validate_selector(selector)
    return selector


zeroconf = zeroconf.Zeroconf()

logger = structlog.get_logger(__name__)

min_time = 0


savelock = threading.RLock()

# Normally we run from one folder. If it's been installed, we change the paths a bit.
dn = os.path.dirname(os.path.realpath(__file__))
if "/usr/lib" in dn:
    datadir = "/usr/share/kaithem"
else:
    datadir = os.path.join(dn, "../data")

bip39: List[str] = [s.strip() for s in open(os.path.join(datadir, "bip39.txt"))]

assert len(bip39) == 2048


def memorableHash(x: bytes | str, num: int = 3, separator: str = "") -> str:
    "Use the diceware list to encode a hash. This IS meant to be secure"
    o: str = ""

    if isinstance(x, str):
        x = x.encode("utf8")

    x = hashlib.sha256(x).digest()

    for i in range(num):
        # 4096 is an even divisor of 2**16
        n = struct.unpack("<H", x[:2])[0] % 2048
        o += bip39[n] + separator
        x = x[2:]
    return o[: -len(separator)] if separator else o


def universal_weakref(f, cb=None):
    if isinstance(f, types.MethodType):
        return weakref.WeakMethod(f, cb)
    else:
        return weakref.ref(f, cb)


def chmod_private_try(p: str, execute: bool = True) -> None:
    try:
        if execute:
            os.chmod(
                p,
                stat.S_IRUSR
                | stat.S_IWUSR
                | stat.S_IXUSR
                | stat.S_IRGRP
                | stat.S_IWGRP
                | stat.S_IXGRP,
            )
        else:
            os.chmod(
                p, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP
            )
    except Exception as e:
        raise e


def open_private_text_write(p):
    try:
        x = os.open("/path/to/file", os.O_RDWR | os.O_CREAT, 0o0600)
        return os.fdopen(x, "w")
    except Exception:
        try:
            os.close(x)
        except Exception:
            pass
        return open(p, "w")


def url(u: str, safe: str | Iterable[str] = ""):
    safe = "".join(safe)
    return quote(u, safe)


def readfile(f):
    with open(f) as fh:
        r = fh.read()
    return r


# Get the names of all subdirectories in a folder but not full paths


def get_immediate_subdirectories(folder):
    return [
        name
        for name in os.listdir(folder)
        if os.path.isdir(os.path.join(folder, name))
    ]


# Get a list of all filenames but not the full paths


def get_files(folder):
    return [
        name
        for name in os.listdir(folder)
        if not os.path.isdir(os.path.join(folder, name))
    ]


def search_paths(fn: str, paths: List[str]) -> str | None:
    for i in paths:
        if os.path.exists(os.path.join(i, fn)):
            return os.path.join(i, fn)


def disallowSpecialChars(s, allow=""):
    for i in r"""~!@#$%^&*()_+`-=[]\{}|;':"',./<>?""":
        if i in s:
            raise ValueError("String contains " + i)
    for i in "\n\r\t":
        if i in s:
            raise ValueError("String contains tab, newline, or return")


class LowPassFiter:
    "Speed should be 0 to 1 and express by what percentage to approach the new value per sample"

    def __init__(self, speed, startval=0):
        self.value = startval
        self.speed = speed

    def sample(self, x):
        self.value = (self.value * (1 - self.speed)) + ((x) * self.speed)


# Credit to Jay of stack overflow for this function


def which(program):
    "Check if a program is installed like you would do with UNIX's which command."

    # Because in windows, the actual executable name has .exe while the command name does not.
    if sys.platform == "win32" and not program.endswith(".exe"):
        program += ".exe"

    # Find out if path represents a file that the current user can execute.
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    # If the input was a direct path to an executable, return it
    if fpath:
        if is_exe(program):
            return program

    # Else search the path for the file.
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    # If we got this far in execution, we assume the file is not there and return None
    return None


last = time.time()


lastNTP = 0
oldNTPOffset = 30 * 365 * 24 * 60 * 60
hasInternet = False


def diff(a, b):
    x = a.split("\n")
    x2 = []
    for i in x:
        x2.append(i)
    y = b.split("\n")
    y2 = []
    for i in y:
        y2.append(i)
    return "".join(difflib.unified_diff(x2, y2))


# This returns either the current time, or a value that is higher than any
# timestamp in the latest server save
def time_or_increment():
    if time.time() > min_time:
        return time.time()
    else:
        return int(min_time) + 1.234567


def roundto(n, s):
    if not s:
        return n
    if (n % s) > (s / 2):
        return n + (s - (n % s))
    else:
        return n - n % s


numberlock = threading.Lock()
current_number = -1


def unique_number():
    global current_number
    with numberlock:
        current_number += 1
        x = current_number
    return x


def is_private_ip(ip):
    if "." in ip:
        ip = [int(i) for i in ip.split(".")]

        if ip[0] == 10 or ip[0] == 127:
            return True

        elif ip[0] == [172]:
            if ip[1] >= 16 and ip[1] <= 31:
                return True

        elif ip[0] == 192 and ip[1] == 168:
            return True

        return False

    if ip == "::1":
        return True

    elif ip.startswith(("fc", "fd", "fe80")):
        return True

    return False


srepr = reprlib.Repr()

srepr.maxdict = 25
srepr.maxlist = 15
srepr.maxset = 10
srepr.maxlong = 24
srepr.maxstring = 240
srepr.maxother = 240


def saferepr(obj):
    try:
        return srepr.repr(obj)
    except Exception as e:
        return str(e) + " in repr() call"


currentUser = None


def getUser():
    global currentUser
    return currentUser or getpass.getuser()
