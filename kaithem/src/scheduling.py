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


#unused, unfinished
class Event():
    "Does function at time provided there is a strong referemce to f still by then"
    def __init__(self,function,time):
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

    def unregister(self):
        scheduler.remove(self)
        
class RepeatingEvent():
    "Does function every interval seconds, and stops if you don't keep a reference to function"
    def __init__(self,function,interval):
        self.f = weakref.ref(function, callback=self.unregister())
        self.interval = float(interval)
        self.scheduled = False
        self.errored = False
        self.lock = threading.Lock()
    
    def schedule(self):
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
        t = time.time()+offset
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
        
    def unregister(self):
        scheduler.unregister(self)
            
    def run(self):
        workers.do(self._run)
        
    def _run(self):
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
        finally:
            self.scheduled = False

class SelfSchedulingEvent():
    "Does function every interval seconds, and stops if you don't keep a reference to function"
    def __init__(self,function,interval):
        self.f = weakref.ref(function, callback=self.unregister())
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
        
    def unregister(self):
        scheduler.unregister(self)
            
    def run(self):
        workers.do(self._run)
        
    def _run(self):
        try:
            if self.lock.acquire(False):
                try:
                    f = self.f()
                    if not f:
                        self.unregister()
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
                except Exception as e:
                    print(e)
                finally:
                    self.lock.release()
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
        self.lock = threading.Lock()
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
            
    def remove(self, event):
        "Remove something that has a time and a _run property that wants its _run to not be called at time"
        with self.lock:
            try:
                self.tasks.remove(event)
            except:
                pass

    def register_repeating(self, event):
        "Register a RepeatingEvent class"
        with self.lock:
            self.repeatingtasks.append(event)
            
    def unregister(self, event):
        "unregister a RepeatingEvent"
        with self.lock:
            try:
                self.repeatingtasks.remove(event)
                self.tasks.remove(event)
            except:
                pass

                
    def run(self):
        while 1:
            #Caculate the time until the next UNIX timestamp whole number, with 0.0011s offset to compensate
            #for the time it takes to process 0.9989
            time_till_next_second = max(0,(random.random()+0.5)-(time.time()%1))
            if self.tasks:
                time.sleep(max(min((self.tasks[0].time-time.time()),time_till_next_second),0))
            else:
                time.sleep(time_till_next_second)
                
            #Take all the repeating tasks that aren't already scheduled to happen and schedule them.
            #Normally tasks reschedule themselves, but this check catches any errors in
            #the chain of run>reschedule>run>etc
            for i in self.repeatingtasks:
                if not i.scheduled:
                    i.schedule()
                    
            #This is under lock so it doesn't clobber insertswith the sorted old version or something
            #I don't know if list.sort is atomic so we do this instead.
            with self.lock:
                #Sort the list of tasks from soonest to latest
                self.tasks = sorted(self.tasks, key=lambda x: x.time or -1)
                
            #Run tasks until all remaining ones are in the future
            while self.tasks and (self.tasks[0].time <time.time()):
                i = self.tasks.pop(False)
                try:
                    i.run()
                except:
                    f = i.f()
                    messagebus.postMessage('system/errors/scheduler/time',
                                        {"function":f.__name__,
                                        "module":f.__module__,
                                        "traceback":traceback.format_exc(6)})
                    if not i.errored:
                        m = f.__module__
                        messagebus.postMessage("/system/notifications/errors", "Problem in scheduled event function: "+repr(f)+" in module: "+ m+", check logs for more info.")
                        i.errored = True
                    del f


last_did_minute_tasks = 0
class Scheduler(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.second = set()
        self.minute = set()
        self.hour = set()
        self.sec2 = []
        self.min2=[]
        self.events = []
        self.errored_events = collections.OrderedDict()
        self.events2 = []
        self.daemon = True
        self.running = True
        self.name = 'SchedulerThread'
        self.lock = threading.Lock()

    def everySecond(self,f):
        "Cause f to be executed every second as long as a reference to f exists. Returns f, so may be used as a decorator."
        self.sec2.append(f)
        return f

    def everyMinute(self,f):
        "Cause f to be executed every minute as long as a reference to f exists. Returns f so may be used as a decorator."
        self.min2.append(f)
        return f

    def schedule(self,f,at,exact = 60*3):
        """Cause f to be called at time at, which must be a UNIX timestamp.
        Exact controls how late the function may be called instead of giving up entirely.
        A reference to f must be maintained until then. Returns an object with an unregister()
        method that may also be called to cancel the event.
        """
        class ScheduledEvent():
            def __init__(self,id,parent):
                self.id = id
                self.parent = parent
            def unregister(self):
                self.parent._unschedule(id)

        id = str(time.time())+f.__module__+repr(os.urandom(3))
        self.events2.append((weakref.ref(f),float(at),float(exact),id))
        return ScheduledEvent(id,self)

    def _unschedule(self,id):
        with self.lock:
            for index,i in enumerate(self.events):
                if i[3] == id:
                    self.events.pop(index)

    def at(self,t,exact=60*5, async=True):
        "Decorator to schedule something to happen at an exact time."
        def decorator(f):
            self.schedule(f, time, exact)
        return f

    def handle_error_notification(self,f):
        if repr(f)+str(id(f)) in self.errored_events:
            return
        else:
            try:
                m = f.__module__
            except:
                m = "<unknown>"
            messagebus.postMessage("/system/notifications/errors", "Problem in scheduled event function: "+repr(f) +" in module: "+ m+", check logs for more info.")
            self.errored_events[repr(f)+str(id(f))] = True
            if len(self.errored_events) > 250:
                self.errored_events.popitem(False)
                
    def run(self):
        "This runs in a loop for as long as the program runs and runs the tasks. It works by waking up every second and checking what needs doing"
        global last_did_minute_tasks
        while self.running:
            #We can't let users directly add to the lists, so the users put stuff in staging
            #Areas until we finish iterating. Then we copy all the items to the lists.
            messagebus.postMessage("/system/scheduler/tick", time.time())
            delete_broken = False
            with self.lock:
                for i in self.second:
                    try:
                        f= workers.async(i())
                        if f:
                            f()
                        else:
                            delete_broken = True
                    except:
                        try:
                            messagebus.postMessage('system/errors/scheduler/second/',
                                                    {"function":f.__name__,
                                                    "module":f.__module__,
                                                    "traceback":traceback.format_exc(6)})
                            self.handle_error_notification(f)
                        except Exception as e:
                            pass
                #A tiny bit of variatiion in timing of minutes is allowed, so we don't miss events of something.
                #However, just checking if tm_sec==0 sometimes resulted in double firing, because
                #sometimes the loop would go twice in a second.
                if time.localtime().tm_sec < 2 and time.time()-last_did_minute_tasks > 58:
                    last_did_minute_tasks = time.time()
                    for i in self.minute:
                        try:
                           f= workers.async(i())
                           if f:
                               f()
                           else:
                               delete_broken = True
                        except:
                            try:
                                messagebus.postMessage('system/errors/scheduler/minute',
                                                   {"function":f.__name__,
                                                    "module":f.__module__,
                                                    "traceback":traceback.format_exc(6)})
                                self.handle_error_notification(f)
                            except:
                                pass

                #Iterate over all the events until we get to one that is in the future
                while self.events and (self.events[0][1]<time.time()):
                    #Get the event tuple
                    f = self.events.pop(0)
                    #If the exact parameter is false, or it is less than exact in the past
                    if f[2]==False or f[1]< time.time() + f[2] :
                        #Then we dereference the weak reference and call the function
                        try:
                           f =workers.async(f[0]())
                           if f:
                               f()
                           else:
                               delete_broken = True
                        except:
                            try:
                                messagebus.postMessage('system/errors/scheduler/time',
                                                   {"function":f.__name__,
                                                    "module":f.__module__,
                                                    "traceback":traceback.format_exc(6)})
                                self.handle_error_notification(f)
                            except:
                                pass
                    ##Handle events that we already missed.
                    #elif f[3]:
                        #try:
                            #f[3]()
                        #except:
                            #try:
                                #messagebus.postMessage('system/errors/scheduler/time',
                                                   #{"function":f.__name__,
                                                    #"module":f.__module__,
                                                    #"traceback":traceback.format_exc(6)})
                                #self.handle_error_notification(f)
                            #except:
                                #pass
                            
                        
                if delete_broken:
                    for i in self.second.copy():
                        if not i():
                            self.second.remove(i)
                    for i in self.minute.copy():
                        if not i():
                            self.minute.remove(i)
                #Don't make there be a reference hanging around to screw up the weakref garbage collection
                try:
                    del f
                except:
                    pass
                
                #Sleep until beginning of the next second. We do this before the 
                time.sleep(1-(time.time()%1))
      
                #We do this first because we want to do it right before the actual running the stuff or else we
                #will have old versions.
                for i in self.sec2:
                    self.second.add(weakref.ref(i))
                for i in self.min2:
                    self.minute.add(weakref.ref(i))
                for i in self.events2:
                    self.events.append(i)
                self.events = sorted(self.events,key = lambda i:i[1])
                self.events2 = []

            self.min2=[]
            self.sec2 = []
                

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

def get_next_run(s,start = None, after=None):
    s = s.replace("every second",'every 1 seconds')
    if start==None:
        start = datetime.datetime.now().replace(minute=0,second=0,microsecond=0)
    r = recurrent.RecurringEvent()
    dt = r.parse(s)
    if 'DTSTART' in r.get_RFC_rrule():
       raise ValueError("Values containing DSTART are likely to misbehave, consume CPU time, or work unpredictably and are not allowed. Avoid time specifiers that have a specific beginning date.")
    if isinstance(dt,str):
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
        EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
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

