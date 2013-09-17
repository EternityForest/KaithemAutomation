import astral,pytz,datetime,time,calendar
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

    return calendar.timegm(a.dawn_utc(date,lat,lon).timetuple())

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
    return not(sunrise(lat,lon) < time.time() < sunset(lat,lon))

def isDay(lat,lon):
    return (sunrise(lat,lon) < time.time() < sunset(lat,lon))

def isDark(lat,lon):
    return not(dawn(lat,lon) < time.time() < dusk(lat,lon))

def isLight(lat,lon):
    return (dawn(lat,lon) < time.time() < dusk(lat,lon))

def isRahu(lat,lon):
        return (rahu(lat,lon)[0] < time.time() < rahu(lat,lon)[1])

def moon():
    """
        return 0 to 21 depending on current moon phase..
                | 0  = New moon
                | 7  = First quarter
                | 14 = Full moon
                | 21 = Last quarter
   """
    return a.moon_phase(datetime.date.today(),pytz.UTC)