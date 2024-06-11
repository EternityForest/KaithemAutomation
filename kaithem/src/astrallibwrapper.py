# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

"""This file is an wrapper around some of the pyephem library, a pure python
library providing all of kaithem's astronomical functions"""

import datetime

import ephem


def getObserver(lat, lon, date):
    o = ephem.Observer()
    o.lat = str(lat)
    o.lon = str(lon)
    o.date = date
    return o


def toPyEphem(date: datetime.date):
    return date.strftime("%Y/%m/%d %H:%M:%S")


def sun_angle(lat, lon, date=None):
    if date is None:
        date = datetime.datetime.now(datetime.UTC)

    date = date.astimezone(datetime.UTC)

    date = toPyEphem(date)

    o = getObserver(lat, lon, date)

    sun = ephem.Sun(o)
    sun.compute(o)
    sun_angle = float(sun.alt) * 57.2957795  # Convert Radians to degrees

    return sun_angle


def is_sun_above(lat, lon, horizon, date=None):
    return sun_angle(lat, lon, date) > horizon


def is_night(lat, lon):
    return not is_sun_above(lat, lon, -18)


def is_day(lat, lon):
    return is_sun_above(lat, lon, -18)


def is_dark(lat, lon):
    return not is_sun_above(lat, lon, -6)


def is_light(lat, lon):
    return not is_sun_above(lat, lon, -18)


def moon_age():
    """
    return days since new moon
    """

    date = datetime.datetime.now(datetime.UTC)
    date = ephem.Date(date)

    nnm = ephem.next_new_moon(date)
    pnm = ephem.previous_new_moon(date)

    lunation = (date - pnm) / (nnm - pnm)

    return 29.530588853 * lunation


def moon_phase():
    """Returns a floating-point number from 0-1. where 0=new, 0.5=full, 1=new"""

    date = datetime.datetime.now(datetime.UTC)
    date = ephem.Date(date)

    nnm = ephem.next_new_moon(date)
    pnm = ephem.previous_new_moon(date)

    lunation = (date - pnm) / (nnm - pnm)

    # Note that there is a ephem.Moon().phase() command, but this returns the
    # percentage of the moon which is illuminated. This is not really what we want.

    return lunation


def moon_illumination():
    o = getObserver(0, 0, datetime.datetime.now(datetime.UTC))
    moon = ephem.Moon(o)

    return moon.phase
