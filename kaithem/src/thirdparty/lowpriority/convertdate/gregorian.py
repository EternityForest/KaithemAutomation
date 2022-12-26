# -*- coding: utf-8 -*-
# This file is part of convertdate.
# http://github.com/fitnr/convertdate
# Licensed under the MIT license:
# http://opensource.org/licenses/MIT
# Copyright (c) 2016, fitnr <fitnr@fakeisthenewreal>
"""
The Gregorian calendar was introduced by Pope Gregory XII in October 1582. It reforms
the Julian calendar by adjusting leap year rules to reduce the drift versus solar
year.

The Gregorian calendar, like the Julian, does not include a year 0. However, for dates before 1,
this module uses the astronomical convention of including a year 0 to simplify
mathematical comparisons across epochs. To present a date in the standard convention,
use the :meth:`gregorian.format` function.
"""
from calendar import isleap, monthrange
from datetime import date
from math import floor

from .utils import jwday, monthcalendarhelper

EPOCH = 1721425.5

INTERCALATION_CYCLE_YEARS = 400
INTERCALATION_CYCLE_DAYS = 146097

LEAP_SUPPRESSION_YEARS = 100
LEAP_SUPPRESSION_DAYS = 36524

LEAP_CYCLE_YEARS = 4
LEAP_CYCLE_DAYS = 1461

YEAR_DAYS = 365

HAVE_30_DAYS = (4, 6, 9, 11)
HAVE_31_DAYS = (1, 3, 5, 7, 8, 10, 12)


def legal_date(year, month, day):
    '''Check if this is a legal date in the Gregorian calendar'''
    if month == 2:
        daysinmonth = 29 if isleap(year) else 28
    else:
        daysinmonth = 30 if month in HAVE_30_DAYS else 31

    if not 0 < day <= daysinmonth:
        raise ValueError("Month {} doesn't have a day {}".format(month, day))

    return True


def to_jd2(year, month, day):
    '''Gregorian to Julian Day Count for years between 1801-2099'''
    # http://quasar.as.utexas.edu/BillInfo/JulianDatesG.html
    legal_date(year, month, day)

    if month <= 2:
        year = year - 1
        month = month + 12

    a = floor(year / 100)
    b = floor(a / 4)
    c = 2 - a + b
    e = floor(365.25 * (year + 4716))
    f = floor(30.6001 * (month + 1))
    return c + day + e + f - 1524.5


def to_jd(year, month, day):
    '''Convert gregorian date to julian day count.'''
    legal_date(year, month, day)

    if month <= 2:
        leap_adj = 0
    elif isleap(year):
        leap_adj = -1
    else:
        leap_adj = -2

    return (
        EPOCH
        - 1
        + (YEAR_DAYS * (year - 1))
        + floor((year - 1) / LEAP_CYCLE_YEARS)
        + (-floor((year - 1) / LEAP_SUPPRESSION_YEARS))
        + floor((year - 1) / INTERCALATION_CYCLE_YEARS)
        + floor((((367 * month) - 362) / 12) + leap_adj + day)
    )


def from_jd(jd):
    '''Return Gregorian date in a (Y, M, D) tuple'''
    wjd = floor(jd - 0.5) + 0.5
    depoch = wjd - EPOCH

    quadricent = floor(depoch / INTERCALATION_CYCLE_DAYS)
    dqc = depoch % INTERCALATION_CYCLE_DAYS

    cent = floor(dqc / LEAP_SUPPRESSION_DAYS)
    dcent = dqc % LEAP_SUPPRESSION_DAYS

    quad = floor(dcent / LEAP_CYCLE_DAYS)
    dquad = dcent % LEAP_CYCLE_DAYS

    yindex = floor(dquad / YEAR_DAYS)
    year = quadricent * INTERCALATION_CYCLE_YEARS + cent * LEAP_SUPPRESSION_YEARS + quad * LEAP_CYCLE_YEARS + yindex

    if not (cent == 4 or yindex == 4):
        year += 1

    yearday = wjd - to_jd(year, 1, 1)

    leap = isleap(year)

    if yearday < 58 + leap:
        leap_adj = 0
    elif leap:
        leap_adj = 1
    else:
        leap_adj = 2

    month = floor((((yearday + leap_adj) * 12) + 373) / 367)
    day = int(wjd - to_jd(year, month, 1)) + 1

    return (year, month, day)


def month_length(year, month):
    '''Calculate the length of a month in the Gregorian calendar'''
    return monthrange(year, month)[1]


def monthcalendar(year, month):
    '''
    Return a list of lists that describe the calender for one month. Each inner
    list have 7 items, one for each weekday, starting with Sunday. These items
    are either ``None`` or an integer, counting from 1 to the number of days in
    the month.
    For Gregorian, this is very similiar to the built-in :meth:``calendar.monthcalendar``.
    '''
    start_weekday = jwday(to_jd(year, month, 1))
    monthlen = month_length(year, month)

    return monthcalendarhelper(start_weekday, monthlen)


def format(year, month, day, format_string="%-d %B %y"):
    # pylint: disable=redefined-builtin
    epoch = ''
    if year <= 0:
        year = (year - 1) * -1
        epoch = ' BCE'
    d = date(year, month, day)
    return d.strftime(format_string) + epoch
