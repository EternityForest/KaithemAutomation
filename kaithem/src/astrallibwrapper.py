# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

"""This file is an wrapper around some of the astral library, a pure python
library providing all of kaithem's astronomical functions"""

import calendar
import datetime
import time

import astral.moon
import astral.sun
from astral import LocationInfo


def getLocationInfo(lat, lon):
    return LocationInfo("unknown", "unknown", "Etc/UTC", lat, lon)


def dawn(lat, lon, date=None, elevation=0):
    "Given a latitude and longitude, return civil dawn time for any given date object as a unix timestamp(default to today)"
    if date is None:
        date = datetime.datetime.now(datetime.UTC).date()

    return calendar.timegm(astral.sun.sun(astral.Observer(lat, lon, elevation), date)["dawn"].timetuple())


def dusk(lat, lon, date=None, elevation=0):
    "Given a latitude and longitude, return civil dusk time for any given date object as a unix timestamp(default to today)"
    if date is None:
        date = datetime.datetime.now(datetime.UTC).date()

    return calendar.timegm(astral.sun.sun(astral.Observer(lat, lon, elevation), date)["dusk"].timetuple())


def sunrise(lat, lon, date=None, elevation=0):
    "Given a latitude and longitude, return sunrise time for any given date object as a unix timestamp(default to today)"
    if date is None:
        date = datetime.datetime.now(datetime.UTC).date()

    return calendar.timegm(astral.sun.sun(astral.Observer(lat, lon, elevation), date)["sunrise"].timetuple())


def sunset(lat, lon, date=None, elevation=0):
    if date is None:
        date = datetime.datetime.now(datetime.UTC).date()
    return calendar.timegm(astral.sun.sun(astral.Observer(lat, lon, elevation), date)["sunset"].timetuple())


def rahu(lat, lon, date=None, elevation=0):
    "Given a latitude and longitude, return a tuple of the start and end timestamps of the given date's rahukalaam period"
    if date is None:
        date = datetime.datetime.now(datetime.UTC).date()
    r = astral.rahukaalam(astral.Observer(lat, lon, elevation), date)
    return (
        calendar.timegm(r["start"].timetuple()),
        calendar.timegm(r["end"].timetuple()),
    )


def is_night(lat, lon):
    return not (sunrise(lat, lon) <= time.time() <= sunset(lat, lon))


def is_day(lat, lon):
    return sunrise(lat, lon) <= time.time() <= sunset(lat, lon)


def is_dark(lat, lon):
    return not (dawn(lat, lon) <= time.time() <= dusk(lat, lon))


def is_light(lat, lon):
    return dawn(lat, lon) <= time.time() <= dusk(lat, lon)


def isRahu(lat, lon):
    return rahu(lat, lon)[0] <= time.time() <= rahu(lat, lon)[1]


def moon():
    """
    return 0 to 28 depending on current moon phase..
            | 0  = New moon
            | 7  = First quarter
            | 14 = Full moon
            | 21 = Last quarter
    """
    return astral.moon.phase(datetime.datetime.now(datetime.timezone.utc))
