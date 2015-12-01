#Copyright Daniel Dunn 2013
#This file is part of Kaithem Automation.

#Kaithem Automation is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#Kaithem Automation is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

"""This file is an wrapper around some of the astral library, a pure python
library providing all of kaithem's astronomical functions"""

import astral, pytz,datetime,time,calendar
a = astral.Astral()

def dawn(lat,lon,date=None):
    "Given a latitude and longitude, return civil dawn time for any given date object as a unix timestamp(default to today)"
    if date==None:
        date= datetime.datetime.utcnow().date()

    return calendar.timegm(a.dawn_utc(date,lat,lon).timetuple())

def dusk(lat,lon,date=None):
    "Given a latitude and longitude, return civil dusk time for any given date object as a unix timestamp(default to today)"
    if date==None:
        date= datetime.datetime.utcnow().date()

    return calendar.timegm(a.dusk_utc(date,lat,lon).timetuple())

def sunrise(lat,lon,date=None):
    "Given a latitude and longitude, return sunrise time for any given date object as a unix timestamp(default to today)"
    if date==None:
        date= datetime.datetime.utcnow().date()

    return calendar.timegm(a.sunrise_utc(date,lat,lon).timetuple())

def sunset(lat,lon,date=None):
    "Given a latitude and longitude, return sunrise time for any given date object as a unix timestamp(default to today)"
    if date==None:
        date= datetime.datetime.utcnow().date()

    return calendar.timegm(a.sunset_utc(date,lat,lon).timetuple())

def rahu(lat,lon,date=None):
    "Given a latitude and longitude, return a tuple of the start and end timestamps of the given date's rahukalaam period"
    if date==None:
        date= datetime.datetime.utcnow().date()
    r = a.rahukaalam_utc(date,lat,lon)
    return (calendar.timegm(r['start'].timetuple()) , calendar.timegm(r['end'].timetuple()))


def isNight(lat,lon):
    return not(sunrise(lat,lon) <= time.time() <= sunset(lat,lon))

def isDay(lat,lon):
    return (sunrise(lat,lon) <= time.time() <= sunset(lat,lon))

def isDark(lat,lon):
    return not(dawn(lat,lon) <= time.time() <= dusk(lat,lon))

def isLight(lat,lon):
    return (dawn(lat,lon) <= time.time() <= dusk(lat,lon))

def isRahu(lat,lon):
        return (rahu(lat,lon)[0] <= time.time() <= rahu(lat,lon)[1])

def moon():
    """
        return 0 to 21 depending on current moon phase..
                | 0  = New moon
                | 7  = First quarter
                | 14 = Full moon
                | 21 = Last quarter
   """
    return a.moon_phase(datetime.date.today(),pytz.UTC)

seasons= {"spring": 0, "summer":1, "fall":2,"autumn":2, "winter": 3, 1:1, 2:2, 3:3, 4:4, 5:5}
seasonnames = ["spring","summer","autumn","winter"]

class Season():
    def init(self, season):
        self.season = seasons(season)

    def __str__(self,other):
        return seasonnames[self.season]

    def __int__(self,other):
        return self.season

    def __eq__(self, other):
        if self.season == seasons[other]:
            return True
        return False

def season(self, lat, long):
    HEMISPHERE = 'north' if lat>0 else 'south'
    date = self.now()
    md = date.month * 100 + date.day

    if ((md > 320) and (md < 621)):
        s = 0 #spring
    elif ((md > 620) and (md < 923)):
        s = 1 #summer
    elif ((md > 922) and (md < 1223)):
        s = 2 #fall
    else:
        s = 3 #winter

    if not HEMISPHERE == 'north':
        s = (s + 2) % 3
    return Season(s)
