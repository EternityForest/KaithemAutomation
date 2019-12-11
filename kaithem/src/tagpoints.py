
from . import scheduling,workers, virtualresource,widgets,util
import time, threading,weakref,logging

from typing import Callable,Optional,Union
from typeguard import typechecked


logger = logging.getLogger("tagpoints")
syslogger = logging.getLogger("system")

t = time.monotonic

#This is used for messing with the set of tags.
#We just accept that creating and deleting tags and claims is slow.
lock = threading.RLock()

allTags = {}

allTagsAtomic = {}

providers = {}




from .unitsofmeasure import convert, unitTypes

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



#_ and . allowed
illegalCharsInName = "[]{}|\\<>,?-=+)(*&^%$#@!~`\n\r\t\0"
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
    defaultData=None
   
    @typechecked
    def __init__(self,name:str):
        global allTagsAtomic

        if name =="":
            raise ValueError("Tag with empty name")

        for i in illegalCharsInName:
            if i in name:
                raise ValueError("Illegal char in tag point name: "+i)
        virtualresource.VirtualResource.__init__(self)
        
        #Might be the number, or might be the getter function.
        #it's the current value of the active claim
        self._value = self.defaultData
        self.name = name
        #The cached actual value from the claims
        self.cvalue = self.defaultData
        #The cached output of processValue
        self.lastValue = self.defaultData
        self.lastGotValue = 0
        self.interval =0
        self.activeClaim =None
        self.claims = {}
        self.lock = threading.RLock()
        self.subscribers = []
        self.poller = None
       
        self.lastError = 0
        


      

        #String describing the "owner" of the tag point
        #This is not a precisely defined concept
        self.owner = ""

        #Stamp of when the tag's value was set
        self.timestamp = time.monotonic()
        self.annotation=None

        self.handler=None

  

       
        #If we should push the same value twice in a row when it comes in.
        #If false, only push changed data to subscribers.
        self.pushOnRepeats = False
        self.lastPushedValue=None
        self.onSourceChanged = None

        with lock:
            allTags[name]=weakref.ref(self)
            allTagsAtomic= allTags.copy()


        self.defaultClaim = self.claim(self.defaultData)
        
        #What permissions are needed to 
        #manually override this tag 
        self.permissions = []

        #This is where we can put a manual override
        #claim from the web UI.
        self.manualOverrideClaim = None

        self._alarms = {}


    @classmethod
    def Tag(cls,name:str):
        if not isinstance(name,str):
            raise TypeError("Name must be string")
        with lock:
            if name in allTags:
                x=allTags[name]()
                if x:
                    if not x.__class__ is cls:
                        raise TypeError("A tag of that name exists, but it is the wrong type.")
                    return x
            
            for i in sorted(providers.keys(),key =lambda p: len(p.path), reverse=True):
                if name.startswith(i):
                    return providers[i].getTag(i)

            return cls(name)


    @property
    def currentSource(self):
        return self.activeClaim[2]
  
    def filterValue(self,v):
        "Pure function that returns a cleaned up or normalized version of the value"
        return v

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


    def _managePolling(self):        
        if self.subscribers:
            if not self.poller or not (self.interval == self.poller.interval):
                self.poller = scheduling.scheduler.scheduleRepeating(self.p, self.interval)
        else:
            self.poller.unregister()
            self.poller = None


    @typechecked
    def subscribe(self,f:Callable):
        with self.lock:
            self.subscribers.append(util.universal_weakref(f))
            torm = []
            for i in self.subscribers:
                if not i():
                    torm.append(i)
            for i in torm:
                self.subscribers.remove(i)
    
    def unsubscribe(self,f):
        with self.lock:
            x = None
            for i in self.subscribers:
                if i()==f:
                    x = i
            if x:
                self.subscribers.remove(x)

    @typechecked
    def setHandler(self, f:Callable):
        self.handler=weakref.ref(f)

    def _guiPush(self, value):
        pass

    def _push(self,val,timestamp,annotation):
        """Push to subscribers. Only call under the same lock you changed value
            under. Otherwise the push might happen in the opposite order as the set, and
            subscribers would see the old data as most recent.
        """
       
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
                f(val, timestamp, annotation)
            else:
                self.handler=None
        self._guiPush(val)

        self.lastPushedValue = val

        for i in self.subscribers:
            f=i()
            if f:
                try:
                    f(val,timestamp,annotation)
                except:
                    logger.exception("Tag subscriber error")
                    #Return the error from whence it came to display in the proper place
                    try:
                        from . import newevt
                        newevt.eventByModuleName(f.__module__)._handle_exception()
                    except:
                        pass
            del f

    def processValue(self,value):

        """Represents the transform from the claim input to the output.
            Can be stateful, for things like digital filters.
        """
        #Functions are special valid types of value.
        #They are automatically resolved.
        if callable(value):
            value = value()

        return value
   
    @property
    def age(self):
        return time.time()-self.lastGotValue

    @property
    def value(self):
        return self._getValue()

    def _getValue(self):
        #Get the numeric value of the tag. It is meant to be called under lock.
        if not callable(self._value):
            self.lastValue= self.processValue(self._value)
        else:
            #Rate limited tag getter logic
            if time.time()-self.lastGotValue> self.interval:
                try:
                    #None means no new data
                    x = self._value()
                  
                    self.cvalue=  x or  self.cvalue
                    if not x is None:
                        self.lastGotValue = time.time()
                        self.timestamp = time.monotonic()
                        self.annotation=None
                except:
                    #We treat errors as no new data.
                    logger.exception("Error getting tag value")

                    #The system logger is the one kaithem actually logs to file.
                    if self.lastError<(time.time()-(60*10)):
                        syslogger.exception("Error getting tag value. This message will only be logged every ten minutes.")
                    #If we can, try to send the exception back whence it came
                    try:
                        import newevt
                        newevt.eventByModuleName(self._value.__module__)._handle_exception()
                    except:
                        pass

            self.lastValue = self.processValue(self.cvalue)
        return self.lastValue
    
    @value.setter
    def value(self, v):
        self.setClaimVal("default",v,time.monotonic(),"Set via value property")

    
    def handleSourceChanged(self,name):
        if self.onSourceChanged:
            try:
                self.onSourceChanged(name)
            except:
                logging.exception("Error handling changed source")

    def claim(self, value, name="default", priority=None,timestamp=None, annotation=None):
        """Adds a 'claim', a request to set the tag's value either to a literal 
            number or to a getter function.

            A tag's value is the highest priority claim that is currently
            active, or the value returned from the getter if the active claim is
            a function.
        """
        timestamp = timestamp or time.monotonic()

        if priority and priority>100:
            raise ValueError("Maximum priority is 100")

        if not callable(value):
            value=self.filterValue(value)
            
        with self.lock:
            #we're changing the value of an existing claim,
            #We need to get the claim object, which we stored by weakref
            claim=None
            try:
                ##If there's an existing claim by that name we're just going to modify it
                if name in self.claims:
                    claim= self.claims[name][3]()
                    priority= priority or claim.priority
            except:
                logger.exception("Probably a race condition and safe to ignore this")

            #If the weakref obj disappeared it will be None
            if claim ==None:
                priority = priority or 50
                claim = self.claimFactory(value,name,priority,annotation)
        
            claim.value=value
            claim.timestamp = timestamp
            claim.annotation = annotation
            claim.priority = priority


            #Note  that we use the time, so that the most recent claim is
            #Always the winner in case of conflicts
            self.claims[name] = (priority, t(),name,weakref.ref(claim))

            if self.activeClaim==None or priority >= self.activeClaim[0]:
                self.activeClaim = self.claims[name]
                self.handleSourceChanged(name)

                self._value = value
                self.timestamp = timestamp
                self.annotation = annotation

            #If priority has been changed on the existing active claim
            #We need to handle it
            elif name==self.activeClaim[2]:
                #Defensive programming against weakrefs dissapearing
                #in some kind of race condition that leaves them in the list.
                #Basically we find the highest priority valid claim
                for i in reversed(sorted(self.claims.values())):
                    x= i[3]()
                    if x:
                        self._value=x.value
                        self.timestamp = x.timestamp
                        self.annotation = x.annotation
                        self.activeClaim=i
                        self.handleSourceChanged(i[2])
                        break
            self._push(self._getValue(),self.timestamp, self.annotation)           
            return claim

    def setClaimVal(self,claim,val,timestamp,annotation):
        "Set the value of an existing claim"
        timestamp = timestamp or time.monotonic()
        
        if not callable(val):
            val=self.filterValue(val)
        
        with self.lock:
            c=self.claims[claim]
            #If we're setting the active claim
            if c==self.activeClaim:
                upd=True
            else:
                upd=False
            #Grab the claim obj and set it's val
            x= c[3]()
            x.value = val
            x.annotation=annotation
            if upd:
                self.timestamp = timestamp
                self._value=val
                self.annotation=annotation
                self._push(self._getValue(),timestamp,annotation)           


    #Get the specific claim object for this class
    def claimFactory(self, value,name,priority,annotation):
        return Claim(self, value,name,priority,annotation)

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
            while self.claims:
                self.activeClaim = sorted(list(self.claims.values()),reverse=True)[0]
                o = self.activeClaim[3]()

                #Perhaps in a race condition that has dissapeared.
                #We must remove it and retry.
                if o==None:
                    del self.claims[self.activeClaim[2]]
                else:
                    self._value = o.value
                    self.timestamp = o.timestamp
                    self.annotation =o.annotation
                    break
            self._push(self.value, self.timestamp, self.annotation)


class _NumericTagPoint(_TagPoint):
    defaultData=0
    @typechecked
    def __init__(self,name:str, 
        min:Union[float,int,None]=None, 
        max:Union[float,int,None]=None):
        self.meterWidget= widgets.Meter()
        self.meterWidget.setPermissions(['/users/tagpoints.view'],['/users/tagpoints.edit'])
        
        self._hi = 10**16
        self._lo = -10**16
        self._min=min
        self._max =max
        #Pipe separated list of how to display value
        self._displayUnits=None
        self._unit = None
        self.guiLock = threading.Lock()
        
        self._setupMeter()
        _TagPoint.__init__(self,name)

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
   
    def _guiPush(self, value):
        #Immediate write, don't push yet, do that in a thread because TCP can block
        self.meterWidget.write(value,push=False)
        def pushFunction():
            self.meterWidget.value=value
            if self.guiLock.acquire(timeout=1):
                try:
                    #Use the cached literal computed value, not what we were passed,
                    #Because it could have changed by the time we actually get to push
                    self.meterWidget.write(self.lastValue)
                finally:
                    self.guiLock.release()
            

        #Should there already be a function queued for this exact reason, we just let
        #That one do it's job
        if self.guiLock.acquire(timeout=0.001):
            try:
                workers.do(pushFunction)
            finally:
                self.guiLock.release()    

    def filterValue(self,v):
        return float(v)

    def claimFactory(self, value,name,priority,annotation):
        return NumericClaim(self,value,name,priority,annotation)
    
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
        self.meterWidget.setup(self._min if (not (self._min is None)) else -100,
        self._max if (not (self._max is None)) else 100,
        self._hi, self._lo, unit = self.unit, displayUnits= self.displayUnits
         )
    def convertTo(self, unit):
        "Return the tag's current vakue converted to the given unit"
        return convert(self.value,self.unit,unit)
    
    def convertValue(self, value, unit):
        "Convert a value in the tag's native unit to the given unit"
        return convert(value,self.unit,unit)


    @property
    def unit(self):
        return self._unit

    @unit.setter
    @typechecked
    def unit(self,value:str):
        if self._unit:
            if not self._unit==value:
                if value:
                    raise ValueError("Cannot change unit of tagpoint. To override this, set to None first")
        self._unit = value
        self._setupMeter()
        self.meterWidget.write(self.value)


    @property
    def displayUnits(self):
        return self._displayUnits

    @displayUnits.setter
    def displayUnits(self,value):
        self._displayUnits = value
        self._setupMeter()
        self.meterWidget.write(self.value)


class _StringTagPoint(_TagPoint):
    defaultData=''
    @typechecked
    def __init__(self,name:str):
        _TagPoint.__init__(self)
    
    def processValue(self,value):
        #Functions are special valid types of value.
        #They are automatically resolved.
        if callable(value):
            value = value()
        
        return str(value)
   

    def filterValue(self,v):
        return str(v)

    

class Claim():
    "Represents a claim on a tag point's value"
    @typechecked
    def __init__(self,tag:_TagPoint, value, 
        name:str='default',priority:Union[int,float]=50,
        timestamp:Union[int,float,None]=None, annotation=None):

        self.name=name
        self.tag=tag
        self.value = value
        self.annotation=annotation
        self.timestamp = timestamp
        
    def __del__(self):
        if self.name != 'default':
            self.tag.release(self.name)
    
    def set(self,value,timestamp=None, annotation=None):
        self.value = value
        self.tag.setClaimVal(self.name, value,timestamp,annotation)


    def release(self):
        self.tag.release(self.name)


class NumericClaim(Claim):
    "Represents a claim on a tag point's value"
    @typechecked
    def __init__(self,tag:_TagPoint, value:Union[int,float], 
        name:str='default',priority:Union[int,float]=50,
        timestamp:Union[int,float,None]=None, annotation=None):

        Claim.__init__(self,tag,value,name,priority,timestamp,annotation)


    def setAs(self, value, unit, timestamp=None,annotation=None):
        "Convert a value in the given unit to the tag's native unit"
        self.set(convert(value,unit,self.tag.unit), timestamp, annotation)


Tag = _NumericTagPoint.Tag
ObjectTag = _TagPoint.Tag