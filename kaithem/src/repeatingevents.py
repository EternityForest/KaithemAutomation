#Copyright Daniel Dunn 20 15 and 2016
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

import re,recurrent,datetime,dateutil,time,sys

#this class doesn't work yet
class ScheduleCalculator():
    def __init__(s,start = None, initial_position=None):
        s = s.replace("every second",'every 1 seconds')
        if start==None:
            self.start = datetime.datetime.now().replace(minute=0,second=0,microsecond=0)

        if initial_position:
            self.position = initial_position

        else:
            self.position = time.time()

        r = recurrent.RecurringEvent()
        dt = r.parse(s)

        if isinstance(dt,str):
            self.recurring = True
            rr = dateutil.rrule.rrulestr(r.get_RFC_rrule(),dtstart=start)
            if after:
                dt=rr.after(datetime.datetime.fromtimestamp(after))
            else:
                dt=rr.after(datetime.datetime.now())

        tz = re.search(r"(\w\w+/\w+)",s)
        if tz:
            tz = dateutil.tz.gettz(tz.groups()[0])
            if not tz:
                raise ValueError("Invalid Time Zone")
            EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
            dt= dt.replace(tzinfo = tz)
            offset = datetime.timedelta(seconds=0)

        else:
            EPOCH = datetime.datetime(1970, 1, 1)
            offset = dateutil.tz.tzlocal().utcoffset(dt)


        if sys.version_info < (3,0):
            return ((dt-EPOCH)-offset).total_seconds()
        else:
            return ((dt-EPOCH)-offset)/datetime.timedelta(seconds=1)

def get_schedule_string_info(s):
    r = recurrent.RecurringEvent()
    dt = r.parse(s)
    s = r.get_RFC_rrule()
    return s

def get_rrule(s,start = None, after=None):
    s = s.replace("every second",'every 1 seconds')
    if start==None:
        start = datetime.datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)
    r = recurrent.RecurringEvent()
    dt = r.parse(s)
    if 'DTSTART' in r.get_RFC_rrule():
       raise ValueError("Values containing DSTART are likely to misbehave, consume CPU time, or work unpredictably and are not allowed. Avoid time specifiers that have a specific beginning date.")
    if isinstance(dt,str):
        return dateutil.rrule.rrulestr(r.get_RFC_rrule(),dtstart=start)

    if dt == None:
        return None

def get_next_run(s,start = None, after=None,rr=None):
    s = s.replace("every second",'every 1 seconds')
    after = after or time.time()
    if start==None:
        start = datetime.datetime.now().replace(minute=0,second=0,microsecond=0)
    r = recurrent.RecurringEvent()
    dt = r.parse(s)

    if 'DTSTART' in r.get_RFC_rrule():
       raise ValueError("Values containing DSTART are likely to misbehave, consume CPU time, or work unpredictably and are not allowed. Avoid time specifiers that have a specific beginning date.")
    if isinstance(dt,str):
        if not rr:
            rr = dateutil.rrule.rrulestr(r.get_RFC_rrule(),dtstart=start)

        if after:
            dt=rr.after(datetime.datetime.fromtimestamp(after))

        else:
            dt=rr.after(datetime.datetime.now())


    tz = re.search(r"(\w\w+/\w+)",s)

    if dt == None:
        return None
    if tz:
        tz = dateutil.tz.gettz(tz.groups()[0])
        if not tz:
            raise ValueError("Invalid Time Zone")
        EPOCH = datetime.datetime(1970, 1, 1, tzinfo=dateutil.tz.tzutc())
        dt= dt.replace(tzinfo = tz)
        offset = datetime.timedelta(seconds=0)

    else:
        EPOCH = datetime.datetime(1970, 1, 1)
        offset = dateutil.tz.tzlocal().utcoffset(dt)

    if sys.version_info < (3,0):
        x= ((dt-EPOCH)-offset).total_seconds()
    else:
        x= ((dt-EPOCH)-offset)/datetime.timedelta(seconds=1)

    return x
