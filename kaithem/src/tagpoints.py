
from . import scheduling,workers, virtualresource,newevt,widgets
import time, threading,weakref,logging

logger = logging.getLogger("system.tagpoints")

t = time.monotonic

#This is used for messing with the set of tags.
#We just accept that creating and deleting tags and claims is slow.
lock = threading.RLock()

allTags = {}

allTagsAtomic = {}

providers = {}


class TagProvider():
    def mount(self, path):
        if not self.path.endswith("/"):
            self.path.append("/")
        self.path = path
        with lock:
            providers[path]= weakref.ref(self)
    
    def unmount(self):
        del providers[self.path]
    
    def __del__(self):
        with lock:
            del providers[self.path]

    def getTag(self, tagName):
        return _TagPoint(tagName)


def Tag(name):
    with lock:
        if name in allTags:
            return allTags[name]
        
        for i in providers:
            if name.startswith(i):
                return providers[i].getTag(i)

        return _TagPoint(name)

class Claim():
    "Represents a claim on a tag point's value"
    def __init__(self,tag, value, name='default',priority=50):
        self.name=name
        self.tag=tag
        
    def __del__(self):
        self.tag.release(self.name)
    
    def set(self,value):
       self.tag.setClaimVal(self.name, value)

    def release(self):
        self.tag.release(self.name)

class _TagPoint(virtualresource.VirtualResource):
    """
        A Tag Point is a named object that can be chooses from a set of data sources based on priority,
        filters that data, and returns it on a push or a pull basis.

        A data source here is called a "Claim", and can either be a number or a function. The highest
        priority claim is called the active claim.

        If the claim is a function, it will be called at most once per interval, which is set by tag.interval=N
        in seconds. However the filter function is called every time the data is requested.

        If there are any subscribed functions to the tag, they will automatically be called at the tag's interval,
        with the one parameter being the tag's value. Any getter functions will be called to get the value.


        It is also a VirtualResource, and as such if you enter it into a module, then replace it,
        all claims and subscriptions carry over.

        One generally does not instantiate a tag this way, instead they use the Tag function
        which can get existing tags. This allows use of tags for cross=
    
    """
    def __init__(self,name, min=None, max=None):
        global allTagsAtomic
        virtualresource.VirtualResource.__init__(self)
        self._value = 0
        self.cvalue = 0
        self.lastGotValue = 0
        self.interval =1
        self.activeClaim =None
        self.claims = {}
        self.lock = threading.Lock()
        self.subscribers = []
        self.poller = None
        self._hi = 10**10
        self._lo = -10**10

        self.handler=None

        self._min = min
        self._max = max

        self.meterWidget= widgets.Meter()
        self.meterWidget.setPermissions(['/users/tagpoints.view'],['/users/tagpoints.edit'])
        #If we should push the same value twice in a row when it comes in.
        #If false, only push changed data to subscribers.
        self.pushOnRepeats = False
        self.lastPushedValue=None

        with lock:
            allTags[name]=self
            allTagsAtomic= allTags.copy()


        def poll():
            self._push(self.value)

        self.p = poll
        self.defaultClaim = self.claim(0)
        
        #What permissions are needed to 
        #manually override this tag 
        self.permissions = []

        #This is where we can put a manual override
        #claim from the web UI.
        self.manualOverrideClaim = None

        self._alarms = {}

    def addAlarm(self,name, alarm):
        with self.lock:
            self._alarms[name]=weakref.ref(alarm)

            #Do some cleanup here
            torm = []
            for i in self._alarms:
                if self._alarms[i]()==None:
                    torm.append(i)
            for i in torm:
                del self._alarms[i]

    def removeAlarm(self,name):
        with self.lock:
            del self._alarms[name]

    def __del__(self):
        global allTagsAtomic
        with lock:
            try:
                del allTags[self.name]
                allTagsAtomic= allTags.copy()
            except:
                pass


    def interface(self):
        "Override the VResource thing"
        #With no replacement or master objs, we just return self
        return self

    def handoff(self, other):
        #Tag points have no concept of a master object.
        #They have no parameters that can' be set from any ref to it
        if not other ==self:
            raise RuntimeError("Tag points can't be replaced except by the same obj")
        return


        with self.lock:
            with other.lock:
                for i in self.subscribers:
                    if not i() in [j() for j in other.subscribers]:
                       other.subscribers.append()
        
        for i in self.claims:
            if not i in other.claims:
                other.claims[i] = self.claims[i]
        virtualresource.VirtualResource.handoff(self,other)


    def _managePolling(self):        
        if self.subscribers:
            if not self.poller or not (self.interval == self.poller.interval):
                self.poller = scheduling.scheduler.scheduleRepeating(self.p, self.interval)
        else:
            self.poller.unregister()
            self.poller = None



    def subscribe(self,f):
        with self.lock:
            self.subscribers.append(weakref.ref(f))
            torm = []
            for i in self.subscribers:
                if not i():
                    torm.append(i)
            for i in torm:
                self.subscribers.remove(x)
    
    def unsubscribe(self,f):
        with self.lock:
            x = None
            for i in self.subscribers:
                if i()==f:
                    x = i
            if x:
                self.subscribers.remove(x)

    def setHandler(self, f):
        self.handler=weakref.ref(f)

    def _push(self,val):
        self.meterWidget.write(val)
        #This is not threadsafe, but I don't think it matters.
        #A few unnecessary updates shouldn't affect anything.
        if val==self.lastPushedValue:
            if not self.pushOnRepeats:
                return

        #Note the difference with the handler.
        #It is called synchronously, right then and there
        if self.handler:
            f=self.handler()
            if f:
                f(val)
            else:
                self.handler=None
        self.lastPushedValue = val

        for i in self.subscribers:
            def f():
                x=i()
                if x:
                    x(val)
                del x
                workers.do(f)

    def processValue(self,value):
        #Functions are special valid types of value.
        #They are automatically resolved.
        if callable(value):
            value = value()

        if self._min !=None:
            value= max(self._min,value)

        if self._max !=None:
            value= min(self._max,value)        
        
        return float(value)
       
    @property
    def min(self):
        return self._min
    
    @min.setter
    def min(self,v):
        self._min = v
        self._setupMeter()

    @property
    def max(self):
        return self._max
    
    @max.setter
    def max(self,v):
        self._max = v
        self._setupMeter()

    @property
    def hi(self):
        return self._hi
    
    @hi.setter
    def hi(self,v):
        self._hi = v
        self._setupMeter()

    @property
    def lo(self):
        return self._lo
    
    @lo.setter
    def lo(self,v):
        self._lo = v
        self._setupMeter()

    def _setupMeter(self):
        self.meterWidget.setup(self._min if not self._min is None else -100,
        self._max if not self._max is None else 100,
        self._hi, self._lo
         )

    @property
    def value(self):
        if isinstance(self._value, (float,int)):
            return self.processValue(self._value)
        else:
            #Call the function if that's what it is
            if time.time()-self.lastGotValue> self.interval:
                try:
                    self.cvalue= self._value()
                    self.lastGotValue = time.time()
                except:
                    logger.exception("Error getting tag value")
                    #If we can, try to send the exception back whence it came
                    try:
                        newevt.eventByModuleName(self._value.__module__)._handle_exception()
                    except:
                        pass
                    raise

            return self.processValue(self.cvalue)
    
    @value.setter
    def value(self, v):
        self.setClaimVal("default",v)

    def claim(self, value, name="default", priority=50):
        """Adds a 'claim', a request to set the tag's value either to a literal 
            number or to a getter function.

            A tag's value is the highest priority claim that is currently
            active, or the value returned from the getter if the active claim is
            a function.
        """

        with self.lock:
            #ClaimObj means we're changing the value of an existing claim
            if name in self.claims:
                raise ValueError("Cannot have two claims with the same name")
            
            #Note  that we use the time, so that the most recent claim is
            #Always the winner in case of conflicts
            self.claims[name] = (priority, t(),name, value)

            if self.activeClaim==None or priority >= self.activeClaim[0]:
                self.activeClaim = self.claims[name]
                self._value = value

            self._push(self.value)           
            return Claim(self, value,name,priority)

    def setClaimVal(self,claim,val):
        "Set the value of an existing claim"
        with self.lock:
            c=self.claims[claim]
            if c==self.activeClaim:
                upd=True
            else:
                upd=False
            x= (c[0],t(),c[2], val)
            self.claims[claim]=x
            if upd:
                self.activeClaim=x
                self._value=val
                self._push(self.value)

    def release(self, name):
        with self.lock:
            #Ifid lets us filter by ID, so that a claim object that has
            #Long since been overriden can't delete one with the same name
            #When it gets GCed
            if not name in self.claims:
                return
            
            if name=="default":
                raise ValueError("Cannot delete the default claim")

            if len(self.claims)==1:
                raise RuntimeError("Tags must maintain at least one claim")
            del self.claims[name]
            self.activeClaim = sorted(list(self.claims.values()))[-1]
            self._value = self.activeClaim[3]
            self._push(self.value)

