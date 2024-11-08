# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import datetime
import re
import time

import pytz
from scullery.units import *  # noqa

from . import auth, pages
from .config import config

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

import functools


class DayOfWeek(str):
    """This class it a value object that will appear like a string but supports intelligent comparisions like Dow=='Thu' etc.
    supports upper ad lower case and abbreviations and numbers(monday=0).
    If you don't pass it a weekday day when initializing it it will default to today in local time

    """

    def __init__(self, day=""):
        # If no day supplied, default to today
        if day == "":
            day = time.localtime().tm_wday

        self.namestonumbers = {
            "Mon": 0,
            "Monday": 0,
            "M": 0,
            0: 0,
            "Tue": 1,
            "Tuesday": 1,
            "Tues": 1,
            "Tu": 1,
            1: 1,
            "Wed": 2,
            "Wednesday": "2",
            "W": 2,
            2: 2,
            "Thu": 3,
            "Thursday": 3,
            "Th": 3,
            "Thurs": 3,
            "Thur": 3,
            3: 3,
            "Fri": 4,
            "Friday": 4,
            4: 4,
            "Sat": 5,
            "Saturday": 5,
            5: 5,
            "Sun": 6,
            "Sunday": 6,
            6: 6,
        }

        self.numberstonames = [
            ["Monday", "Mon"],
            ["Tuesday", "Tue", "Tu", "Tues"],
            ["Wednesday", "Wed"],
            ["Thursday", "Thu", "Th", "Thurs", "Thur"],
            ["Friday", "Fri"],
            ["Saturday", "Sat"],
            ["Sunday", "Sun"],
        ]
        try:
            if isinstance(day, str):
                day = day.capitalize()
            self.value = self.namestonumbers[day]
        except Exception as e:
            # ValueError('Does not appear to be any valid day of the week')
            raise e

    def __str__(self):
        return self.numberstonames[self.value][0]

    def __int__(self):
        return self.value

    def __repr__(self):
        return self.numberstonames[self.value][0]

    def __eq__(self, other):
        try:
            if isinstance(other, DayOfWeek):
                if self.value == other.value:
                    return True

            if isinstance(other, str):
                other = other.capitalize()

            if self.namestonumbers[other] == self.value:
                return True
            else:
                return False

        except KeyError:
            raise RuntimeError(
                "Invalid to compare day of week to " + repr(other)
            )


class Month(str):
    """This class it a value object that will appear like a string but supports intelligent comparisions like Dow=='Thu' etc.
    supports upper ad lower case and abbreviations and numbers(monday=0).
    If you don't pass it a weekday day when initializing it it will default to today in local time

    """

    def __init__(self, month=None):
        # If no day supplied, default to today
        if month is None:
            self.value = time.localtime().tm_mon

        self.namestonumbers = {
            "Jan": 1,
            "January": 1,
            "Feb": 2,
            "February": 2,
            "Mar": 3,
            "March": 3,
            "Apr": 4,
            "April": 4,
            "May": 5,
            "Jun": 6,
            "June": 6,
            "Jul": 7,
            "July": 7,
            "Aug": 8,
            "August": 8,
            "Sep": 9,
            "September": 9,
            "Oct": 10,
            "October": 10,
            "Nov": 11,
            "November": 11,
            "Dec": 12,
            "December": 12,
            1: 1,
            2: 2,
            3: 3,
            4: 4,
            5: 5,
            6: 6,
            7: 7,
            8: 8,
            9: 9,
            10: 10,
            11: 11,
            12: 12,
        }

        self.numberstonames = [
            ["January"],
            ["February"],
            ["March"],
            ["April"],
            ["May"],
            ["June"],
            ["July"],
            ["August"],
            ["September"],
            ["October"],
            ["November"],
            ["December"],
        ]
        try:
            if isinstance(month, str):
                self.value = month.capitalize()
            elif isinstance(month, int):
                self.value = month
            self.value = self.namestonumbers[self.value]
        except KeyError:
            raise ValueError("Does not appear to be any valid Month")

    def __str__(self):
        return self.numberstonames[self.value][0]

    def __int__(self):
        return self.value

    def __repr__(self):
        return self.numberstonames[self.value][0]

    #     def __cmp__(self,other):
    #          try:
    #             if isinstance(other,Month):
    #                 otherval = other.value
    #             elif isinstance(other,str):
    #                 other=other.capitalize()
    #                 otherval = self.namestonumbers[other]
    #             else:
    #                 otherval = other
    #
    #                 if self.value == otherval:
    #                     return 0
    #                 if self.value > otherval:
    #                     return 1
    #                 return -1
    #
    #          except KeyError:
    #             return -1

    def __eq__(self, other):
        try:
            if isinstance(other, Month):
                if self.value == other.value:
                    return True

            if isinstance(other, str):
                other = other.capitalize()

            if self.namestonumbers[other] == self.value:
                return True
            else:
                return False
        except KeyError:
            return False


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


def format_time_interval_long(t, max_units, clock=False):
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

    for i in sorted(time_as_seconds.items(), key=lambda x: x[1], reverse=True):
        if max_units == 0:
            return s[:-2]
        x = t % i[1]
        b = t - x
        y = (t - x) / i[1]

        t = t - b
        if y > 1:
            s += str(int(round(y))) + " " + i[0] + "s, "
            max_units -= 1
        elif y == 1:
            s += str(int(round(y))) + " " + i[0] + ", "
            max_units -= 1
    return s[:-2]


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


if not config["full_time_intervals"]:
    format_time_interval = format_time_interval_abbr
else:
    format_time_interval = format_time_interval_long


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
