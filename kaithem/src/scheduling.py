#Copyright Daniel Dunn 2015,2016
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

import threading,sys,re,time,datetime,weakref,os,traceback, collections,random,logging
from . import messagebus,workers
from .repeatingevents import *

enumerate = enumerate
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
    def __init__(self,function,interval,priority="realtime", phase = 0):
        BaseEvent.__init__(self)
        self.f = weakref.ref(function, self.unregister)
        self.interval = float(interval)
        self.scheduled = False
        self.errored = False
        self.lock = threading.Lock()
        self.lastrun = None
        self.phaseoffset = (phase%1)*interval
        del function

    def schedule(self):
        """Insert self into the scheduler.
        Note for subclassing: The responsibility of this function to check if it is already scheduled, return if so,
        if not, if must reschedule itself by setting self.time to some time in the future.
        It must then call scheduler.insert(self)

        This must happen in a threadsafe and atomic way because the scheduler thread will call this every once in a while,
        just to be sure, in case an error occurred in the reschedule process

        We implement this at the moment by having a separate _schedule functinon for when we are already under self.lock
        """
        with self.lock:
            if self.scheduled:
                return
            if not self.lastrun:
                self.lastrun = time.time()
            self._schedule()

    def _schedule(self):
        """Calculate next runtime and put self into the queue.
        Currently should only every be called from the loop in the scheduler."""
        #We want to schedule to the multiple of local time.
        #Things on the hour should be on the local hour.

        #adapted from J.F. Sebastian of Stack Overflow
        millis = 1288483950000
        ts = millis * 1e-3
        # local time == (utc time + utc offset)
        offset =(datetime.datetime.fromtimestamp(ts) - datetime.datetime.utcfromtimestamp(ts)).total_seconds()+self.phaseoffset

        #Convert to local time
        t = self.lastrun+offset
        #This is important in the next step. Here we add a fraction of the interval to push times like 59.95 over
        #otherwise it will schedule it for 60 when clearly a minute in the future should be 120
        t += self.interval/10.0
        #Calculate the last modulo of the interval. We do this by doing the module to see how far past it we are
        #then subtracting.
        last = t-(t%self.interval)

        #Get the time after last
        t = last+ self.interval
        #Convert back to UTC/UNIX and add the phase offset
        self.time = (t-offset)
        scheduler.insert(self)
        self.scheduled = True


    def register(self):
        scheduler.register_repeating(self)

    def _unregister(self):
        scheduler.unregister(self)

    #We want to use the worker pool to unregister so that we know which thread the scheduler.unregister call is
    #going to be in to prevent deadlocks. Also, we take a dummy var so we can use this as a weakref callback
    def unregister(self,dummy=None):
        workers.do(self._unregister)


    def run(self):
        workers.do(self._run)

    def _run(self):

        self.lastrun = time.time()
        #We must have been pulled out of the event queue or we wouldn't be running
        if self.lock.acquire(False):
            try:
                f = self.f()
                if not f:
                    self.unregister()
                else:
                    f()
                self._schedule()
            finally:
                self.lock.release()
                del f

class UnsynchronizedRepeatingEvent(RepeatingEvent):
    def _schedule(self):
        """Calculate next runtime and put self into the queue.
        Currently should only every be called from the loop in the scheduler."""

        t = self.lastrun+self.interval
        self.time = t
        scheduler.insert(self)
        self.scheduled = True

class RepeatWhileEvent(RepeatingEvent):
    "Does function every interval seconds, and stops if you don't keep a reference to function"
    def __init__(self,function,interval):
        self.ended=False
        RepeatingEvent.__init__(self,function,interval)

    def _run(self):
        if self.ended:
            return
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
    """
    represents a thread that constantly runs tasks which are objects having a time property that determins when
    their run method gets called. Inserted tasks use a lockless double buffered scheme.
    """
    def __init__(self):
        threading.Thread.__init__(self)
        self.tasks = []
        #Input buffer for lock free task insert. Depends
        #on pop and append being atomic operations.
        self.task_queue = []
        self.lock = threading.RLock()
        self.repeatingtasks= []
        self.daemon = True
        self.name = 'SchedulerThread'
        self.lastrecheckedschedules = time.time()
        self.lf = time.time()

    def everySecond(self,f):
        e = RepeatingEvent(f,1)
        e.register()
        e.schedule()
        return f

    def everyMinute(self,f):
        e = RepeatingEvent(f,60)
        e.register()
        e.schedule()
        return f

    def everyHour(self,f):
        e = RepeatingEvent(f,3600)
        e.register()
        e.schedule()
        return f

    def every(self,f, interval):
        interval = float(interval)
        e = RepeatingEvent(f,interval)
        e.register()
        e.schedule()
        return f

    def schedule(self, f, t, exact=False):
        t = float(t)
        e = Event(f, t)
        e.schedule()
        return e


    def insert(self, event):
        "Insert something that has a time and a run property that wants its run called at time"

        #Soft rate limit to prevent filling memory in really bizzare cases.
        if len(self.task_queue)>3000:
            time.sleep(max(0,(len(self.task_queue)-3000)/2000.0))
            print("rate limiting engaged for function")
        self.task_queue.append(event)


    def remove(self, event):
        "Remove something that has a time and a run property that wants its run to be called at time"
        with self.lock:
            try:
                if event in self.tasks:
                    self.tasks.remove(event)
                if event in self.task_queue:
                    self.task_queue.remove(event)
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
        lmin = min
        lmax = max
        lhasattr = hasattr
        ltime = time
        need_sort = False
        global lastframe
        while 1:
            #Caculate the time until the next UNIX timestamp whole number, with 0.0011s offset to compensate
            #for the time it takes to process 0.9989
            lastframe = time.time()

            time_till_next = lmax(0, 0.1-(time.time()%0.1) )

            #Transfer the contents of one list to the other without using a lock or
            #replacing lists which might let something get lost.

            #We use the double buffer to avoid using a lock when we insert tasks.

            while self.task_queue:
                need_sort=True
                self.tasks.append(self.task_queue.pop())

            with self.lock:
                try:
                    #Sort our list of tasks which should be mostly already sorted except the new stuff.
                    #If no new tasks have been inserted there;s no need to do a sort.
                    if need_sort:
                        self.tasks = sorted(self.tasks, key=lambda x: x.time or -1)
                        need_sort=False
                    if self.tasks:
                        x = lmax(lmin((self.tasks[0].time-time.time()),time_till_next),0)
                    else:
                        x=time_till_next
                except:
                    x = 0.01

            time.sleep(x)
            with self.lock:
                #Run tasks until all remaining ones are in the future
                while self.tasks and (self.tasks[0].time <time.time()):
                    i = self.tasks.pop(False)
                    #Set this flag immediatly, otherwise an error somewhere could
                    #Cause lost repeating events
                    i.scheduled = False
                    overdueby = time.time()-i.time
                    if i.exact and overdueby > i.exact:
                        continue
                    try:
                        i.run()

                    except:
                        try:
                            logging.exception("error in scheduler\n"+traceback.format_exc(6))
                            if isinstance(i.f, weakref.ref):
                                f = i.f()
                            else:
                                f = i.f
                            try:
                                if lhasattr(f,"__name__") and lhasattr(f,"__module__"):
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
                            finally:
                                del f
                        except:
                            print(traceback.format_exc(6))

                #Take all the repeating tasks that aren't already scheduled to happen and schedule them.
                #Normally tasks  just reschedule themselves, but this check prevents any errors in
                #the chain of run>reschedule>run>etc

                #We have to run in a try block because we don't want a bad schedule function to take out the whole thread.

                #We only need to do this every 5 seconds or so, because it's only an error recovery thing.
                if time.time()-self.lastrecheckedschedules>5:
                    for i in self.repeatingtasks:
                        try:
                            if not i.scheduled:
                                xyz = time.time()
                                #Let's maybe not block the entire scheduling thread
                                #If one event takes a long time to schedule or if it
                                #Is already running and can't schedule yet.
                                workers.do(i.schedule)
                                messagebus.postMessage('system/errors/scheduler/warning',"rescheduled "+str(i)+"using error recovery")
                        except:
                                logging.exception("Exception while scheduling event")
                    self.lastrecheckedschedules = time.time()




#Newscheduler is a total rewrite and allows intervals less than 1s, probably has less bugs, etc.
#The only problem is that it is totally untested.
scheduler = NewScheduler()
#scheduler = Scheduler()
scheduler.start()
