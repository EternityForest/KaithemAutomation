
from . import scheduling,workers, virtualresource
import time, threading,weakref
t = time.time()

lock = threading.Lock()

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
        virtualresource.VirtualResource.__init__(self)
        self._value = 0
        self.cvalue = 0
        self.lastGotValue = 0
        self.interval =1
        self.activeClaim = (50, t(),"default",50)
        self.claims = {}
        self.lock = threading.Lock()
        self.subscribers = []
        self.poller = None

        self.min = min
        self.max = max
        with lock:
            allTags[name]=self
            allTagsAtomic= allTags.copy()


        def poll():
            self._push(self.value)

        self.p = poll

    def __del__(self):
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

    def _push(self,val):
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

        if self.min !=None:
            value= max(self.min,value)

        if self.max !=None:
            value= min(self.max,value)        
        
        return float(value)
       

    @property
    def value(self):
        if isinstance(self._value, (float,int)):
            return self.processValue(self._value)
        else:
            #Call the function if that's what it is
            if time.time()-self.lastGotValue> self.interval:
                self.cvalue= self._value()
                self.lastGotValue = time.time()
            return self.processValue(self.cvalue)

    def claim(self, value, name="default", priority=50):
        """Adds a 'claim', a request to set the tag's value either to a literal 
            number or to a getter function.

            A tag's value is the highest priority claim that is currently
            active, or the value returned from the getter if the active claim is
            a function.
        """
        with self.lock:
            #Note  that we use the time, so that the most recent claim is
            #Always the winner in case of conflicts
            self.claims[name] = (priority, t(),name, value)
            
            if priority >= self.activeClaim.priority:
                self.activeClaim = (priority, t(), name, value)
                self._value = value
                return
            
            oldp = self.activeClaim[0]
            if oldp>priority:
                self.activeClaim = sorted(list(self.claims.values()))[-1]
                self._value = self.activeClaim[3]

    
    def release(self, name):
        with self.lock:
            del self.claims[name]
            self.activeClaim = sorted(list(self.claims.values()))[-1]
            self._value = self.activeClaim[3]


t=Tag("Blah")
t.claim(8889,"TestClaim",51)
