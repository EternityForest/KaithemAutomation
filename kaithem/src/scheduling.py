import threading,sys,re,time,datetime,weakref,re,recurrent,dateutil
from . import messagebus
       
class Scheduler(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.second = set()
        self.minute = set()
        self.hour = set()
        self.sec2 = []
        self.min2=[]
        self.events = []
        self.events2 = []
        self.daemon = True
        self.running = True
        self.name = 'SchedulerThread'
        
    def everySecond(self,f):
        self.sec2.append(f)
        return f
        
    def everyMinute(self,f):
        self.min2.append(f)
        return f
    
    def schedule(self,f,at,exact = 60*5):
        self.events2.append((weakref.ref(f),at,exact))

    def at(self,t,exact=60*5):
        def decorator(f):
            self.schedule(f, time, exact)
        return f
    
    def run(self):
        while self.running:
            messagebus.postMessage("/system/scheduler/tick", time.time())

            for i in self.second:
                try:
                    f= i()
                    if f:
                        f()
                except:
                    try:
                        messagebus.postMessage('system/errors/scheduler/second/'+
                                                {"function":f.__name__,
                                                "module":f.__module__,
                                                "traceback":traceback.format_exc()})
                    except:
                        pass
            if time.localtime().tm_sec == 0:
                for i in self.minute:
                    try:
                       f= i()
                       if f:
                           f()
                    except:
                        try:
                            messagebus.postMessage('system/errors/scheduler/minute'+
                                               {"function":f.__name__,
                                                "module":f.__module__,
                                                "traceback":traceback.format_exc()})
                        except:
                            pass
            
            #Iterate over all the events until we get to one that is in the future
            while self.events and (self.events[0][1]<time.time()):
                #Get the event tuple
                f = self.events.pop(0)
                messagebus.postMessage("got",str(f)+str(time.time()))

                #If the exact parameter is false, or it is less than exact in the past
                if f[2]==False or f[1]< time.time() + f[2] :
                    messagebus.postMessage("nortooold","")

                    #Then we dereference the weak reference and call the function
                    try:
                       f =f[0]()
                       messagebus.postMessage("dereferenced",str(f))

                       if f:
                           messagebus.postMessage("calling","")

                           f()
                           messagebus.postMessage("called","")

                    except:
                        try:
                            messagebus.postMessage('system/errors/scheduler/minute'+
                                               {"function":f.__name__,
                                                "module":f.__module__,
                                                "traceback":traceback.format_exc()})
                        except:
                            pass
            #Don't make there be a reference hanging around
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
    messagebus.postMessage('ass',s)
    if start==None:
        start = datetime.datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)
    r = recurrent.RecurringEvent()
    dt = r.parse(s)
    if isinstance(dt,str):
        rr = dateutil.rrule.rrulestr(r.get_RFC_rrule(),dtstart=start)
        dt=rr.after(datetime.datetime.now())
    tz = re.search(r"(\w\w+/\w+)",s)
    if tz:
        tz = dateutil.tz.gettz(tz.groups()[0])
        EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
        dt= dt.replace(tzinfo = tz)
        offset = 0

    else:
        EPOCH = datetime.datetime(1970, 1, 1)
        offset = time.timezone

        
    if sys.version_info < (3,0):
        return (dt-EPOCH).total_seconds()+offset
    else:
        return (dt-EPOCH)/datetime.timedelta(seconds=1)+offset


scheduler = Scheduler()
scheduler.start()