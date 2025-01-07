# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import datetime
import re
import time

import pytz
from scullery.units import *  # noqa

from . import auth, pages

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

import functools

time_as_seconds = {
    "year": 60 * 60 * 24 * 365,
    # A "month" as commonly used is a vauge unit. is it 28 days? 30? 31?
    # To solve that, I define it as 1/12th of a solar year.
    "month": 60 * 60 * 24 * 30.4368333333,
    "week": 60 * 60 * 24 * 7,
    "day": 60 * 60 * 24,
    "hour": 60 * 60,
    "minute": 60,
    "second": 1,
    "millisecond": 0.001,
    "microsecond": 0.000001,
    "nanosecond": 0.000000001,
    "picosecond": 0.000000000001,
    "femtosecond": 0.000000000000001,
}


time_as_seconds_abbr = {
    "yr": 60 * 60 * 24 * 365,
    # A "month" as commonly used is a vauge unit. is it 28 days? 30? 31?
    # To solve that, I define it as 1/12th of a solar year.
    "month": 60 * 60 * 24 * 30.4368333333,
    "w": 60 * 60 * 24 * 7,
    "d": 60 * 60 * 24,
    "h": 60 * 60,
    "m": 60,
    "s": 1,
    "ms": 0.001,
    "us": 0.000001,
    "ns": 0.000000001,
    "ps": 0.000000000001,
    "fs": 0.000000000000001,
}


def time_interval_from_string(s):
    """Take a string like '10 hours' or 'five minutes 32 milliseconds'
    or '1 year and 1 day' to a number of seconds"""
    regex = (
        r"([0-9]*)\D*?(year|month|week|day|hour|minute|second|millisecond)s?"
    )
    r = re.compile(regex)
    m = r.finditer(s)
    total = 0
    for i in m:
        multiplier = time_as_seconds[i.group(2).strip()]
        number = float(i.group(1))
        total += number * multiplier
    return total


def format_time_interval_abbr(t, max_units, clock=False):
    """Take a length of time t in seconds, and return a nicely formatted string
    like "2 hours, 4 minutes, 12 seconds".
    max_units is the maximum number of units to use in the string(7 will add a milliseconds field to times in years)

    """
    if clock:
        frac = t % 1
        t -= frac
        seconds = t % 60
        t -= seconds
        minutes = (t - (int(t / 3600) * 3600)) / 60
        t -= t % 3600
        hours = t / 3600

        s = "%02d:%02d" % (hours, minutes)
        if max_units > 2:
            s += ":%02d" % (seconds)
        if max_units > 3:
            # Adding 0.01 seems to help with some kind of obnoxious rounding bug thing. Prob a better way to do things.
            s += ":%03d" % (0.01 + frac * 1000)

        return s
    s = ""
    for i in sorted(
        time_as_seconds_abbr.items(), key=lambda x: x[1], reverse=True
    ):
        if max_units == 0:
            return s[:-1]
        x = t % i[1]
        b = t - x
        y = (t - x) / i[1]

        t = t - b
        if y > 1:
            if i[0] == "month":
                s += str(int(round(y))) + i[0] + "s "
            else:
                s += str(int(round(y))) + i[0] + " "
            max_units -= 1
        elif y:
            s += str(int(round(y))) + i[0] + " "
            max_units -= 1
    return s[:-1]


format_time_interval = format_time_interval_abbr


def str_to_int_si_multipliers(s):
    """Take a string of the form number[k|m|g] or just number and convert to an actual number
    '0'-> 0, '5k'->5000 etc. Does not do division!!!! m is mega not milli!!!"""
    s = s.lower()
    # This piece of code interprets a string like 89m or 50k as a number like 89 millon or 50,000
    if s.endswith("k"):
        return int(s[:-1]) * 1000
    elif s.endswith("m"):
        return int(s[:-1]) * 1000_000
    elif s.endswith("g"):
        return int(s[:-1]) * 1000_000_000
    else:
        return int(s[:-1])


def iround(number, digits):
    if (number - int(number) == 0) or (digits == 0):
        return int(number)
    else:
        return round(number, digits)


# Thanks OP and fdemmer
# https://gist.github.com/Morreski/c1d08a3afa4040815eafd3891e16b945
def lru_cache(timeout: int, maxsize: int = 128, typed: bool = False):
    def wrapper_cache(func):
        func = functools.lru_cache(maxsize=maxsize, typed=typed)(func)
        func.delta = timeout * 10**9
        func.expiration = time.monotonic_ns() + func.delta

        @functools.wraps(func)
        def wrapped_func(*args, **kwargs):
            if time.monotonic_ns() >= func.expiration:
                func.cache_clear()
                func.expiration = time.monotonic_ns() + func.delta
            return func(*args, **kwargs)

        wrapped_func.cache_info = func.cache_info
        wrapped_func.cache_clear = func.cache_clear
        return wrapped_func

    return wrapper_cache


# This is cached because it has slow data file lookup stuff happening
@lru_cache(300, 48)
def getZone(s):
    try:
        tz = ZoneInfo(s)
    except Exception:
        tz = pytz.timezone(s)
    return tz


def strftime(*arg) -> str:
    tz = getZone(auth.getUserSetting(pages.getAcessingUser(), "timezone"))
    if arg:
        d = datetime.datetime.fromtimestamp(*arg, tz=datetime.UTC).replace(
            tzinfo=pytz.utc
        )
    else:
        d = datetime.datetime.fromtimestamp(
            time.time(), tz=datetime.UTC
        ).replace(tzinfo=pytz.utc)
    if not ZoneInfo:
        return tz.normalize(d.astimezone(tz)).strftime(
            auth.getUserSetting(pages.getAcessingUser(), "strftime")
        )
    else:
        return d.astimezone(tz).strftime(
            auth.getUserSetting(pages.getAcessingUser(), "strftime")
        )
