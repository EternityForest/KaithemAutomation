# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

"""This file is an wrapper around some of the astral library, a pure python
library providing all of kaithem's astronomical functions"""

import datetime
import time
import calendar
from astral import LocationInfo
import astral.sun
import astral.moon


def getLocationInfo(lat, lon):
    return LocationInfo("unknown", "unknown", "Etc/UTC", lat, lon)


def dawn(lat, lon, date=None, elevation=0):
    "Given a latitude and longitude, return civil dawn time for any given date object as a unix timestamp(default to today)"
    if date == None:
        date = datetime.datetime.utcnow().date()

    return calendar.timegm(
        astral.sun.sun(astral.Observer(lat, lon, elevation), date)["dawn"].timetuple()
    )


def dusk(lat, lon, date=None, elevation=0):
    "Given a latitude and longitude, return civil dusk time for any given date object as a unix timestamp(default to today)"
    if date == None:
        date = datetime.datetime.utcnow().date()

    return calendar.timegm(
        astral.sun.sun(astral.Observer(lat, lon, elevation), date)["dusk"].timetuple()
    )


def sunrise(lat, lon, date=None, elevation=0):
    "Given a latitude and longitude, return sunrise time for any given date object as a unix timestamp(default to today)"
    if date == None:
        date = datetime.datetime.utcnow().date()

    return calendar.timegm(
        astral.sun.sun(astral.Observer(lat, lon, elevation), date)[
            "sunrise"
        ].timetuple()
    )


def sunset(lat, lon, date=None, elevation=0):
    if date == None:
        date = datetime.datetime.utcnow().date()
    return calendar.timegm(
        astral.sun.sun(astral.Observer(lat, lon, elevation), date)["sunset"].timetuple()
    )


def rahu(lat, lon, date=None, elevation=0):
    "Given a latitude and longitude, return a tuple of the start and end timestamps of the given date's rahukalaam period"
    if date == None:
        date = datetime.datetime.utcnow().date()
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
    return astral.moon.phase(datetime.datetime.utcnow())


seasons = {
    "spring": 0,
    "summer": 1,
    "fall": 2,
    "autumn": 2,
    "winter": 3,
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    5: 5,
}
seasonnames = ["spring", "summer", "autumn", "winter"]


class Season:
    def init(self, season):
        self.season = seasons[season]

    def __str__(self):
        return seasonnames[self.season]

    def __int__(self):
        return self.season

    def __eq__(self, other):
        if self.season == seasons[other]:
            return True
        return False


def season(self, lat, long):
    HEMISPHERE = "north" if lat > 0 else "south"
    date = self.now()
    md = date.month * 100 + date.day

    if (md > 320) and (md < 621):
        s = 0  # spring
    elif (md > 620) and (md < 923):
        s = 1  # summer
    elif (md > 922) and (md < 1223):
        s = 2  # fall
    else:
        s = 3  # winter

    if not HEMISPHERE == "north":
        s = (s + 2) % 3
    return Season(s)
