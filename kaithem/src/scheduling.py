#Copyright Daniel Dunn 2015
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

import threading,sys,re,time,datetime,weakref,re,recurrent,dateutil,os,traceback, collections,random
from . import messagebus,workers

class BaseEvent():
    def __init__(self):
        self.exact = 0

#unused, unfinished
class Event(BaseEvent):
    "Does function at time provided there is a strong referemce to f still by then"
    def __init__(self,function,time):
        BaseEvent.__init__(self)
        self.f = weakref.ref(function)
        self.time = time
        self.errored = False

    def schedule(self):
        scheduler.insert(self)

    def run(self):
        workers.do(self._run)

    def _run(self):
        f = self.f()
        if not f:
            self.unregister()
        else:
            f()

    def _unregister(self):
        scheduler.remove(self)

    #We want to use the worker pool to unregister so that we know which thread the scheduler.unregister call is
    #going to be in to prevent deadlocks. Also, we take a dummy var so we can use this as a weakref callback
    def unregister(self,dummy=None):
        workers.do(self._unregister)

def shouldSkip(priority,interval,lateby,lastran):
    t = {'realtime':200, 'interactive':0.8, 'high':0.5, 'medium':0.3, 'low':0.2, "verylow":0.1}
    maxlatency = {'realtime':0, 'interactive':0.2, 'high':2, 'medium':3, 'low':10, "verylow":60}
    if lateby>t[priority]:
        if ((time.time()-lastran)+interval)<maxlatency[priority]:
            return True

class RepeatingEvent(BaseEvent):
    "Does function every interval seconds, and stops if you don't keep a reference to function"
    def __init__(self,function,interval,priority="realtime"):
        BaseEvent.__init__(self)
        self.f = weakref.ref(function, self.unregister)
        self.interval = float(interval)
        self.scheduled = False
        self.errored = False
        self.lock = threading.Lock()
        self.lastrun = None
        del function

    def schedule(self):
        "Insert self into the scheduler. "
        with self.lock:
            if self.scheduled:
                return
            if not self.lastrun:
                self.lastrun = time.time()
            """Calculate next runtime and put self into the queue.
            Currently should only every be called from the loop in the scheduler."""
            #We want to schedule to the multiple of local time.
            #Things on the hour should be on the local hour.

            #adapted from J.F. Sebastian of Stack Overflow
            #We should really just recheck the schedule every n seconds
            millis = 1288483950000
            ts = millis * 1e-3
            # local time == (utc time + utc offset)
            offset =(datetime.datetime.fromtimestamp(ts) - datetime.datetime.utcfromtimestamp(ts)).total_seconds()

            #Convert to local time
            t = self.lastrun+offset
            #This is important in the next step. Here we add a fraction of the interval to pust times like 59.95 over
            #otherwise it will schedule it for 60 when clearly a minute in the future should be 120
            t += self.interval/10.0
            #Calculate the last modulo of the interval. We do this by doing the module to see how far past it we are
            #then subtracting.
            last = t-(t%self.interval)

            #Get the time after last
            t = last+ self.interval
            #Convert back to UTC/UNIX
            self.time = t-offset

            scheduler.insert(self)
            self.scheduled = True


    def register(self):
        scheduler.register_repeating(self)

    def _unregister(self):
        scheduler.unregister(self)

    #We want to use the worker pool to unregister so that we know which thread the scheduler.unregister call is
    #going to be in to prevent deadlocks. Also, we take a dummy var so we can use this as a weakref callback
    def unregister(self,dummy=None):
        try:
            workers.do(self._unregister)
        except:
            pass

    def run(self):
        workers.do(self._run)

    def _run(self):

        self.lastrun = time.time()
        try:
            if self.lock.acquire(False):
                try:
                    f = self.f()
                    if not f:
                        self.unregister()
                    else:
                        f()
                finally:
                    self.lock.release()
                    del f
        finally:
            self.scheduled = False


class SelfSchedulingEvent():
    "Does function every interval seconds, and stops if you don't keep a reference to function"
    def __init__(self,function,interval):
        self.f = weakref.ref(function, self.unregister)
        self.interval = float(interval)
        self.scheduled = False
        self.errored = False
        self.lock = threading.Lock()

    def schedule(self):
        """Put self in queue based on the time already calculated by the function"""
        scheduler.insert(self)
        self.scheduled = True


    def register(self):
        scheduler.register_repeating(self)

    def _unregister(self):
        scheduler.unregister(self)

    def unregister(self,dummy=None):
        try:
            workers.do(self._unregister)
        #Catch nuisiance errors on interpreter shutdown
        except:
            pass

    def run(self):
        workers.do(self._run)

    def _run(self):
        try:
            if self.lock.acquire(False):
                try:
                    f = self.f()
                    if not f:
                        self._unregister()
                    else:
                        self.time = f()
                finally:
                    self.lock.release()
        finally:
            self.scheduled = False




class RepeatWhileEvent(RepeatingEvent):
    "Does function every interval seconds, and stops if you don't keep a reference to function"
    def __init__(self,function,interval):
        self.ended=False
        RepeatingEvent.__init__(self,function,interval)

    def _run(self):
        if self.ended:
            return
        try:
            if self.lock.acquire(False):
                try:
                    f = self.f()
                    if not f:
                        self.unregister()
                    else:
                        r =f()
                        if not r:
                            self.unregister()
                            self.ended = True
                finally:
                    self.lock.release()
                    del f
        finally:
            self.scheduled = False

#class ComplexRecurringEvent():
    #def schedule(self):
        #if self.scheduled:
            #return
        #else:
            #t = self.schedulefunc(self.last)
            #if t<time.time():
                #if self.makeup:
                    #n = self.schedulefunc(t)
                    #x = (t+n)/2
            #self.scheduled = t
            #s

class NewScheduler(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.tasks = []
        self.lock = threading.RLock()
        self.repeatingtasks= []
        self.daemon = True
        self.name = 'SchedulerThread2'

    def everySecond(self,f):
        e = RepeatingEvent(f,1)
        e.register()
        return f

    def everyMinute(self,f):
        e = RepeatingEvent(f,60)
        e.register()
        return f

    def everyHour(self,f):
        e = RepeatingEvent(f,3600)
        e.register()
        return f

    def every(self,f, interval):
        interval = float(interval)
        e = RepeatingEvent(f,interval)
        e.register()
        return f

    def schedule(self, f, t, exact=False):
        t = float(t)
        e = Event(f, t)
        e.schedule()
        return e

    def insert(self, event):
        "Insert something that has a time and a _run property that wants its _run called at time"
        with self.lock:
            self.tasks.append(event)
            self.tasks = sorted(self.tasks, key=lambda x: x.time or -1)

    def remove(self, event):
        "Remove something that has a time and a _run property that wants its _run to not be called at time"
        with self.lock:
            try:
                if event in self.tasks:
                    self.tasks.remove(event)
            except:
                logging.exception("failed to remove event")

    def register_repeating(self, event):
        "Register a RepeatingEvent class"
        with self.lock:
            self.repeatingtasks.append(event)

    def unregister(self, event):
        "unregister a RepeatingEvent"
        with self.lock:
            try:
                if event in self.repeatingtasks:
                    self.repeatingtasks.remove(event)
                if event in self.tasks:
                    self.tasks.remove(event)
            except:
                logging.exception("failed to unregister event")



    def run(self):
        while 1:

            #Caculate the time until the next UNIX timestamp whole number, with 0.0011s offset to compensate
            #for the time it takes to process 0.9989
            time_till_next_second = max(0, 0.9989-(time.time()%1) )
            if self.tasks:
                time.sleep(max(min((self.tasks[0].time-time.time()),time_till_next_second),0))
            else:
                time.sleep(time_till_next_second)

            #Run tasks until all remaining ones are in the future
            while self.tasks and (self.tasks[0].time <time.time()):
                i = self.tasks.pop(False)
                overdueby = time.time()-i.time
                if i.exact and overdueby > i.exact:
                    continue
                try:
                    i.run()
                except:
                    f = i.f()
                    if hasattr(f,"__name__") and hasattr(f,"__module__"):
                        messagebus.postMessage('system/errors/scheduler/time',
                                            {"function":f.__name__,
                                            "module":f.__module__,
                                            "traceback":traceback.format_exc(6)})
                        if not i.errored:
                            m = f.__module__
                            messagebus.postMessage("/system/notifications/errors",
                            "Problem in scheduled event function: "+repr(f)+" in module: "+ m
                                    +", check logs for more info.")
                            i.errored = True
                    del f

            #Take all the repeating tasks that aren't already scheduled to happen and schedule them.
            #Normally tasks would just reschedule themselves, but this way prevents any errors in
            #the chain of run>reschedule>run>etc
            for i in self.repeatingtasks:
                if not i.scheduled:
                    i.schedule()


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


#Newscheduler is a total rewrite and allows intervals less than 1s, probably has less bugs, etc.
#The only problem is that it is totally untested.
scheduler = NewScheduler()
#scheduler = Scheduler()
scheduler.start()