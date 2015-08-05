import threading,sys,re,time,datetime,weakref,re,recurrent,dateutil,os,traceback, collections
from . import messagebus,workers

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
        self.sec2.append(f)
        return f

    def everyMinute(self,f):
        self.min2.append(f)
        return f

    def schedule(self,f,at,exact = 60*3):
        class ScheduledEvent():
            def __init__(self,id,parent):
                self.id = id
                self.parent = parent
            def unregister(self):
                self.parent._unschedule(id)

        id = str(time.time())+f.__module__+repr(os.urandom(3))
        self.events2.append((weakref.ref(f),at,exact,id))
        return ScheduledEvent(id,self)

    def _unschedule(self,id):
        with self.lock:
            for index,i in enumerate(self.events):
                if i[4] == id:
                    self.pop(index)


    def at(self,t,exact=60*5, async = True):
        def decorator(f):
            self.schedule(workers.async(f) if async else f, time, exact)
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
        while self.running:
            messagebus.postMessage("/system/scheduler/tick", time.time())
            with self.lock:
                for i in self.second:
                    try:
                        f= i()
                        if f:
                            f()
                    except:
                        try:
                            messagebus.postMessage('system/errors/scheduler/second/',
                                                    {"function":f.__name__,
                                                    "module":f.__module__,
                                                    "traceback":traceback.format_exc(6)})
                            self.handle_error_notification(f)
                        except Exception as e:
                            pass

                if time.localtime().tm_sec == 0:
                    for i in self.minute:
                        try:
                           f= i()
                           if f:
                               f()
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
                           f =f[0]()
                           if f:
                               f()
                        except:
                            try:
                                messagebus.postMessage('system/errors/scheduler/time',
                                                   {"function":f.__name__,
                                                    "module":f.__module__,
                                                    "traceback":traceback.format_exc(6)})
                                self.handle_error_notification(f)
                            except:
                                pass
                #Don't make there be a reference hanging around to screw up the weakref garbage collection
                try:
                    del f
                except:
                    pass

            #We can't let users directly add to the lists, so the users put stuff in staging
            #Areas until we finish iterating. Then we copy all the items to the lists.
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
            #Sleep until beginning of the next second
            time.sleep(1-(time.time()%1))



def get_next_run(s,start = None):
    s = s.replace("every second",'every 1 seconds')
    if start==None:
        start = datetime.datetime.now().replace(minute=0,second=0,microsecond=0)
    r = recurrent.RecurringEvent()
    dt = r.parse(s)

    if isinstance(dt,str):
        rr = dateutil.rrule.rrulestr(r.get_RFC_rrule(),dtstart=start)
        dt=rr.after(datetime.datetime.now())
    tz = re.search(r"(\w\w+/\w+)",s)
    if tz:
        tz = dateutil.tz.gettz(tz.groups()[0])
        if not tz:
            raise ValueError("Invalid Time Zone")
        EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
        dt= dt.replace(tzinfo = tz)
        offset = 0

    else:
        EPOCH = datetime.datetime(1970, 1, 1)
        offset = dateutil.tz.tzlocal().utcoffset(dt)


    if sys.version_info < (3,0):
        return ((dt-EPOCH)-offset).total_seconds()
    else:
        return ((dt-EPOCH)-offset)/datetime.timedelta(seconds=1)


scheduler = Scheduler()
scheduler.start()
