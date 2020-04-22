from . import scheduling,workers, virtualresource,widgets,messagebus,directories,persist,alerts
import time, threading,weakref,logging,types,traceback,math,os,gc

from typing import Callable,Optional,Union
from threading import setprofile
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

subscriberErrorHandlers=[]

hasUnsavedData = [0]

#Allows use to recalc entire lists of tags on the creation of another tag,
#For dependancy resolution
recalcOnCreate = weakref.WeakValueDictionary()


from .unitsofmeasure import convert, unitTypes
from . import widgets

tagsAPI = widgets.APIWidget()

def normalizeTagName(n):
    if n.endswith("/"):
        n=n[:-1]
    if n.startswith("/"):
        n=n[1:]
    return n


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

configTags ={}
configTagData = {}

def configTagFromData(name,data):
    existingData = configTagData.get(name, {})

    t = data.get("type","number")

    #Get rid of any unused existing tag
    try:
        if name in configTags:
            del configTags[name]
            gc.collect()
            time.sleep(0.01)
            gc.collect()
            time.sleep(0.01)
            gc.collect()
    except:
        pass
   

    #Create or get the tag
    if t=="number":
        configTags[name]= Tag(name)
    elif t=="string":
        configTags[name]= StringTag(name)
    elif name in allTags:
        configTags[name]= allTags[name]()
    else:
        #Config later when the tag is actually created
        configTagData[name]=data
        return
    
    #Now set it's config.
    configTags[name].setConfigData(data)




def getFilenameForTagConfig(i):
    if i.startswith("/"):
        n = i[1:]
    else:
        n=i
    return os.path.join(directories.vardir,"tags",n+".yaml")


def gcEmptyConfigTags():
    torm= []                
    #Empty dicts can be deleted from disk, letting us just revert to defaultsP
    for i in configTagData:
        if not configTagData[i].getAllData():
            #Can't delete the actual data till the file on disk is gone,
            #Which is handled by the persist libs
            if not os.path.exists(configTagData[i].filename):
                torm.append(i)

    #Note that this is pretty much the only way something can ever be deleted,
    #When it is empty we garbarge collect it.
    #This means we never need to worry about what to keep config data for.
    for i in torm:
       configTagData.pop(i,0)


def loadAllConfiguredTags(f=os.path.join(directories.vardir,"tags")):
    with lock:
        global configTagData
        
        configTagData= persist.loadAllStateFiles(f)

        gcEmptyConfigTags()

        for i in configTagData:
            try:
                configTagFromData(i, configTagData[i].getAllData())
            except:
                logging.exception("Failure with configured tag")
                messagebus.postMessage("/system/notifications/errors","Failed to preconfigure tag "+i)
        
       



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
        if not name.strip().startswith("="):
            for i in illegalCharsInName:
                if i in name:
                    raise ValueError("Illegal char in tag point name: "+i)
        virtualresource.VirtualResource.__init__(self)
        
        #Might be the number, or might be the getter function.
        #it's the current value of the active claim
        self._value = self.defaultData

        #Used to track things like min and max, what has been changed by manual setting.
        #And should not be overridden by code.
        self.configOverrides = {}

        self.dynamicAlarmData={}
        self.configuredAlarmData = {}

        self.alarms = {}

        self.name = name
        #The cached actual value from the claims
        self.cachedRawClaimVal = self.defaultData
        #The cached output of processValue
        self.lastValue = self.defaultData
        self.lastGotValue = 0
        self._interval =0
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
        #start at zero because the time has never been set
        self.timestamp = 0
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

        with lock:
            messagebus.postMessage("/system/tags/created",self.name, synchronous=True)
            if self.name in recalcOnCreate:
                for i in recalcOnCreate[self.name]:
                    try:
                        i()
                    except:
                        pass
                
        if self.name.startswith("="):
            createGetterFromExpression(self.name, self)
        with lock:
            self.setConfigData(configTagData.get(self.name,{}))

    def setConfigAttr(self,k,v):
        "Currently converts everything to float or None if blank"
        with lock:
            if not v in (None,''):
                self.configOverrides[v]=v
                if not self.name in configTagData:
                    configTagData[self.name]= persist.getStateFile(getFilenameForTagConfig(self.name))
                    configTagData[self.name].noFileForEmpty = True
                configTagData[self.name][k]=v
            else:
                #Setting at attr to none or an empty string
                #Deletes it.
                self.configOverrides.pop(k,0)
                if self.name in configTagData:
                    configTagData[self.name].pop(k,0)
            if isinstance(v,str):
                if v.strip()=='':
                    v=None
                else:
                    v=float(v)
            setattr(self,k,v)

            hasUnsavedData[0]=True

    def setAlarm(self,name, condition, priority="warning", releaseCondition='',autoAck='no', tripDelay='0',isConfigured=True,_refresh=True):
        with lock:
            if not name:
                raise RuntimeError("Empty string name")
            d={
                'condition':condition,
                'priority':priority,
                'autoAck':autoAck,
                'tripDelay':tripDelay,
                'releaseCondition': releaseCondition
            }
            
            if isConfigured:
                if not isinstance(condition,str) and not condition==None:
                    raise ValueError("Configurable alarms only str or none condition")
                hasUnsavedData[0]=True

                storage = self.configuredAlarmData
            else:
                storage= self.dynamicAlarmData

            if condition:
                storage[name]=d
            else:
                storage.pop(name,0)

            #If we have configured alarms, there should be a configTagData entry.
            #If not, delete, because when that is empty it's how we know
            #to delete the actual file
            if isConfigured:
                if self.configuredAlarmData:
                    if not self.name in configTagData:
                        configTagData[self.name]=persist.getStateFile(getFilenameForTagConfig(self.name))    
                        configTagData[self.name].noFileForEmpty = True

                    configTagData[self.name]['alarms']= self.configuredAlarmData
                else:
                    if self.name in configTagData:
                        configTagData[self.name].pop("alarms",0)
            if _refresh:
                self.createAlarms()


    def createAlarms(self):
        merged = {}
        with lock:
            for i in self.dynamicAlarmData:
                merged[i] = merged.get(i,{})
                for j in self.dynamicAlarmData[i]:
                    merged[i][j]=self.dynamicAlarmData[i][j]

            for i in self.configuredAlarmData:
                merged[i] = merged.get(i,{})
                for j in self.configuredAlarmData[i]:
                    merged[i][j]=self.configuredAlarmData[i][j]

            
        for i in self.alarms:
            try:
                self.unsubscribe(self.alarms[i].tagSubscriber)
            except:
                pass

            self.alarms[i].release()
        
        self.alarms ={}

        for i in merged:
            d =merged[i]
            self._alarmFromData(i,d)

    
    def _alarmFromData(self,name,d):
        if not d.get("condition",''):
            return
        tripCondition=d['condition']

        releaseCondition = d.get('releaseCondition',None)
    
        priority=d.get("priority","warning") or 'warning'
        autoAck= d.get("autoAck",'').lower() in ('yes', 'true','y','auto')
        tripDelay = float(d.get("tripDelay",0) or 0) 

        from . import kaithemobj

        context = {
                "math": math,
                "time": time,
                'tag': self,
                'kaithem': kaithemobj.kaithem,
        }
        
        tripCondition = compile(tripCondition, self.name+".alarms."+name+"_trip","eval")
        if releaseCondition:
            releaseCondition = compile(tripCondition, self.name+".alarms."+name+"_trip","eval")

        obj = alerts.Alert(self.name+".alarms."+name, 
            priority=priority,
            autoAck=autoAck,
            tripDelay=tripDelay,
            )

        #Give access to the alert obj itself
        context['alert']=obj
    
        def pollf(value, annotation, timestamp):
            context['value']= value
            if eval(tripCondition,context, context):
                obj.trip()
            elif releaseCondition:
                if eval(releaseCondition,context, context):
                    obj.release()
            else:
                obj.release()

        obj.tagSubscriber = pollf
        self.subscribe(pollf)
        self.alarms[name]= obj

        try:
            with self.lock:
                pollf(self.value,self.timestamp,self.annotation)
        except:
            logging.exception("Problem with alarm?")

    def setConfigData(self,data):
        with lock:
            hasUnsavedData[0]=True
            #Only modify tags if the current data matches the existing
            #Configured value and has not beed overwritten by code
            if 'hi' in data:
                self.setConfigAttr('hi',data['hi'])
            else:
                self.setConfigAttr('hi',None)
            
            if 'lo' in data:
                self.setConfigAttr('lo',data['lo'])
            else:
                self.setConfigAttr('lo',None)

            if 'interval' in data:
                self.setConfigAttr('interval',data['interval'])
            else:
                self.setConfigAttr('interval',None)

            if 'min' in data:
                self.setConfigAttr('min',data['min'])
            else:
                self.setConfigAttr('min',None)

            if 'max' in data:
                self.setConfigAttr('max',data['max'])
            else:
                self.setConfigAttr('max',None)


            alarms = data.get('alarms',{})
            for i in alarms:
                if not alarms[i]==None:
                    #Avoid duplicate param
                    alarms[i].pop('name','')
                    self.setAlarm(i, **alarms[i],isConfigured=True,_refresh=False)
                else:
                    self.setAlarm(i,None,isConfigured=True,_refresh=False)

            #This one is a little different. If the timestamp is 0,
            #We know it has never been set.
            if 'value' in data and not 'value'=='':
                if not self.name in configTagData:
                    configTagData[self.name]= persist.getStateFile(getFilenameForTagConfig(self.name))
                    configTagData[self.name].noFileForEmpty = True
                configTagData[self.name]['value']=data['value']

                if self.timestamp == 0:
                    #Set timestamp to 0, this marks the tag as still using a default
                    #Which can be further changed
                    self.setClaimVal("default", float(data['value']),0,"Configured default")
            else:
                if self.name in configTagData:
                    configTagData[self.name].pop("value",0)
            self.createAlarms()

    @property
    def interval(self):
        return self._interval

    @interval.setter
    def interval(self,val):
        if not val==self.configOverrides.get('interval',val):
            return
        if not val==None:
            self._interval=val
        else:
            self._interval=0
        with self.lock:
            self._managePolling() 


  

    @classmethod
    def Tag(cls,name:str, defaults={}):
        if not isinstance(name,str):
            raise TypeError("Name must be string")
        #Normalize
        if not name.startswith("/"):
            name="/"+name
        rval = None
        with lock:
            if name in allTags:
                x=allTags[name]()
                if x:
                    if not x.__class__ is cls:
                        raise TypeError("A tag of that name exists, but it is the wrong type.")
                    rval=x
            
           
            for i in sorted(providers.keys(),key =lambda p: len(p.path), reverse=True):
                if name.startswith(i):
                    rval= providers[i].getTag(i)

            rval= cls(name)

            return rval

    @property
    def currentSource(self):
        return self.activeClaim[2]
  
    def filterValue(self,v):
        "Pure function that returns a cleaned up or normalized version of the value"
        return v

    def addAlarm(self,name, alarm):
        with lock:
            self._alarms[name]=weakref.ref(alarm)

            #Do some cleanup here
            torm = []
            for i in self._alarms:
                if self._alarms[i]()==None:
                    torm.append(i)
            for i in torm:
                del self._alarms[i]

    def removeAlarm(self,name):
        with lock:
            del self._alarms[name]

    def __del__(self):
        global allTagsAtomic
        with lock:
            try:
                del allTags[self.name]
                allTagsAtomic= allTags.copy()
            except:
                pass
            messagebus.postMessage("/system/tags/deleted",self.name, synchronous=True)


    def __call__(self,*args,**kwargs):
        if not args:
            return self.value
        else:
            return self.setClaimVal(*args,**kwargs)


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
        interval = self._interval or 0
        if (self.subscribers or self.handler) and interval>0:
            if not self.poller or not (interval == self.poller.interval):
                self.poller = scheduling.scheduler.scheduleRepeating(self.poll, interval)
        else:
            if self.poller:
                self.poller.unregister()
                self.poller = None


    @typechecked
    def subscribe(self,f:Callable):
        with self.lock:
            
            if isinstance(f,types.MethodType):
                ref=weakref.WeakMethod(f)
            else:
                ref = weakref.ref(f)

            self.subscribers.append(ref)


            torm = []
            for i in self.subscribers:
                if not i():
                    torm.append(i)
            for i in torm:
                self.subscribers.remove(i)
            
            self._managePolling()
    
    def unsubscribe(self,f):
        with self.lock:
            x = None
            for i in self.subscribers:
                if i()==f:
                    x = i
            if x:
                self.subscribers.remove(x)
            
            self._managePolling()

    @typechecked
    def setHandler(self, f:Callable):
        self.handler=weakref.ref(f)

    def _guiPush(self, value):
        pass

    def poll(self):
        with self.lock:
            self._getValue()
            self._push()

    def _push(self):
        """Push to subscribers. Only call under the same lock you changed value
            under. Otherwise the push might happen in the opposite order as the set, and
            subscribers would see the old data as most recent.

            Also, keep setting the timestamp and annotation under that lock, to stay atomic
        """
       
        #This is not threadsafe, but I don't think it matters.
        #A few unnecessary updates shouldn't affect anything.
        if self.lastValue==self.lastPushedValue:
            if not self.pushOnRepeats:
                return
        
        #Note the difference with the handler.
        #It is called synchronously, right then and there
        if self.handler:
            f=self.handler()
            if f:
                f(self.lastValue, self.timestamp, self.annotation)
            else:
                self.handler=None
        self._guiPush(self.lastValue)

        self.lastPushedValue = self.lastValue

        for i in self.subscribers:
            f=i()
            if f:
                try:
                    f(self.lastValue,self.timestamp,self.annotation)
                except:
                    logger.exception("Tag subscriber error")
                    #Return the error from whence it came to display in the proper place

                    for i in subscriberErrorHandlers:
                        try:
                            i(self, f,self.lastValue)
                        except:
                            print("Failed to handle error: "+traceback.format_exc(6))
            del f

    def processValue(self,value):

        """Represents the transform from the claim input to the output.
            Must be a pure-ish function
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
        "Get the processed value of the tag, and update lastValue, It is meant to be called under lock."

        activeClaimValue = self._value
        if not callable(activeClaimValue):
            #We no longer are aiming to support using the processor for impure functions
            pass
            self.lastValue= self.processValue(activeClaimValue)
        else:
            #Rate limited tag getter logic. We ignore the possibility for
            #Race conditions and assume that calling a little too often is fine, since
            #It shouldn't affect correctness
            if time.time()-self.lastGotValue> self._interval:
                #Set this flag immediately, or else a function with an error could defeat the cacheing
                #And just flood everything with errors
                self.lastGotValue = time.time()

                try:
                    #However, the actual logic IS ratelimited
                    #Note the lock is IN the try block so we don' handle errors under it and
                    #Cause bugs that way
                    with self.lock:
                        #None means no new data
                        x = activeClaimValue()
                        t = time.monotonic()
                        
                        if not x is None:
                            #Race here. Data might not always match timestamp an annotation, if we weren't under lock
                            self.timestamp = t 
                            self.annotation=None

                        self.cachedRawClaimVal= x or self.cachedRawClaimVal
                        self.lastValue = self.processValue(self.cachedRawClaimVal)
                except:
                    #We treat errors as no new data.
                    logger.exception("Error getting tag value")

                    #The system logger is the one kaithem actually logs to file.
                    if self.lastError<(time.time()-(60*10)):
                        syslogger.exception("Error getting tag value. This message will only be logged every ten minutes.")
                    #If we can, try to send the exception back whence it came
                    try:
                        import newevt
                        newevt.eventByModuleName(activeClaimValue.__module__)._handle_exception()
                    except:
                        pass
            
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
        if timestamp is None:
            timestamp = time.monotonic()

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
                    #No priority change, set and return
                    if priority == claim.priority:
                        claim.set(value,timestamp, annotation)
                        return claim
                    priority= priority or claim.priority
            except:
                logger.exception("Probably a race condition and safe to ignore this")

            #If the weakref obj disappeared it will be None
            if claim ==None:
                priority = priority or 50
                claim = self.claimFactory(value,name,priority,timestamp,annotation)
        
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

                if callable(self._value) or callable(value):
                    self._managePolling()

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
            
            self._getValue()
            self._push()           
            return claim

    def setClaimVal(self,claim,val,timestamp,annotation):
        "Set the value of an existing claim"
        if timestamp == None:
            timestamp = time.monotonic()
        
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
            if callable(x.value) or callable(val):
                self._managePolling()
            x.value = val
         
            x.annotation=annotation
            if upd:
                self.timestamp = timestamp
                self._value=val
                self.annotation=annotation
                self._getValue()
                self._push()

              


    #Get the specific claim object for this class
    def claimFactory(self, value,name,priority,timestamp,annotation):
        return Claim(self, value,name,priority,timestamp,annotation)

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

            self._getValue()
            self._push()
            self._managePolling()


class _NumericTagPoint(_TagPoint):
    defaultData=0
    @typechecked
    def __init__(self,name:str, 
        min:Union[float,int,None]=None, 
        max:Union[float,int,None]=None):
        self.meterWidget= widgets.Meter()
        self.meterWidget.setPermissions(['/users/tagpoints.view'],['/users/tagpoints.edit'])
        
        self._hi = None
        self._lo = None
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

    def claimFactory(self, value,name,priority,timestamp,annotation):
        return NumericClaim(self,value,name,priority,timestamp,annotation)
    
    @property
    def min(self):
        return self._min
    
    @min.setter
    def min(self,v):
        if not v==self.configOverrides.get('min',v):
            return
        self._min = v
        self._setupMeter()

    @property
    def max(self):
        return self._max
    
    @max.setter
    def max(self,v):
        if not v==self.configOverrides.get('max',v):
            return        
        self._max = v
        self._setupMeter()

    @property
    def hi(self):
        return self._hi
    
    @hi.setter
    def hi(self,v):
        if not v==self.configOverrides.get('hi',v):
            return
        if v==None:
            v=10**16
        self._hi = v
        self._setupMeter()

    @property
    def lo(self):
        return self._lo
    
    @lo.setter
    def lo(self,v):
        if not v==self.configOverrides.get('lo',v):
            return
        if v==None:
            v=-(10**16)
        self._lo = v
        self._setupMeter()

    def _setupMeter(self):
        self.meterWidget.setup(self._min if (not (self._min is None)) else -100,
        self._max if (not (self._max is None)) else 100,
        self._hi if not (self._hi is None) else 10**16,
        self._lo if not (self._lo is None) else -(10**16),
        unit = self.unit,
        displayUnits= self.displayUnits

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
        self.spanWidget = widgets.DynamicSpan()
        self.spanWidget.setPermissions(['/users/tagpoints.view'],['/users/tagpoints.edit'])
        self.guiLock=threading.Lock()

        _TagPoint.__init__(self,name)
    
    def processValue(self,value):
        #Functions are special valid types of value.
        #They are automatically resolved.
        if callable(value):
            value = value()
        
        return str(value)
   

    def filterValue(self,v):
        return str(v)

    def _guiPush(self, value):
        #Immediate write, don't push yet, do that in a thread because TCP can block
        self.spanWidget.write(value,push=False)
        def pushFunction():
            self.spanWidget.value=value
            if self.guiLock.acquire(timeout=1):
                try:
                    #Use the cached literal computed value, not what we were passed,
                    #Because it could have changed by the time we actually get to push
                    self.spanWidget.write(self.lastValue)
                finally:
                    self.guiLock.release()
        #Should there already be a function queued for this exact reason, we just let
        #That one do it's job
        if self.guiLock.acquire(timeout=0.001):
            try:
                workers.do(pushFunction)
            finally:
                self.guiLock.release()    
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
        self.priority=priority
        
    def __del__(self):
        if self.name != 'default':
            self.tag.release(self.name)
    
    def set(self,value,timestamp=None, annotation=None):
        self.tag.setClaimVal(self.name, value,timestamp,annotation)


    def release(self):
        self.tag.release(self.name)

    def __call__(self,*args,**kwargs):
        if not args:
            raise ValueError("No arguments")
        else:
            return self.set(*args,**kwargs)
class NumericClaim(Claim):
    "Represents a claim on a tag point's value"
    @typechecked
    def __init__(self,tag:_TagPoint, value, 
        name:str='default',priority:Union[int,float]=50,
        timestamp:Union[int,float,None]=None, annotation=None):

        Claim.__init__(self,tag,value,name,priority,timestamp,annotation)


    def setAs(self, value, unit, timestamp=None,annotation=None):
        "Convert a value in the given unit to the tag's native unit"
        self.set(convert(value,unit,self.tag.unit), timestamp, annotation)

# Math for the first order filter
# v is our state, k is a constant, and i is input.

# At each timestep of one, we do:
# v = v*(1-k) + i*k

# moving towards the input with sped determined by k.
# We can reformulate that as explicitly taking the difference, and moving along portion of it
# v = (v+((i-v)*k))

# We can show this reformulation is correct with XCas:
# solve((v*(1-k) + i*k) - (v+((i-v)*k)) =x,x)

# x is 0, because the two equations are always the same.


# Now we use 1-k instead, such that k now represents the amount of difference allowed to remain.
# Higher k is slower.
# (v+((i-v)*(1-k)))


# Twice the time means half the remaining difference, so we are going to raise k to the power of the number of timesteps
# at each round to account for the uneven timesteps we are using:
# v = (v+((i-v)*(1-(k**t))))

# Now we need k such that v= 1/e when starting at 1 going to 0, with whatever our value of t is.
# So we substitute 1 for v and 0 for i, and solve for k:
# solve(1/e = (1+((0-1)*(1-(k**t)))),k)

# Which gives us k=exp(-(1/t))


class Filter():
    def subscribe(f):
        self.tag.subscribe
    
class LowpassFilter(Filter):
    def __init__(self, name, inputTag, timeConstant, priority=60,interval=-1):
        self.state = inputTag.value
        self.filtered = self.state
        self.lastRanFilter = time.monotonic()
        self.lastState = self.state

        #All math derived with XCas
        self.k = math.exp(-(1/timeConstant))
        self.lock = threading.Lock()

        self.inputTag =inputTag
        inputTag.subscribe(self.doInput)

        self.tag= _NumericTagPoint(name)
        self.claim = self.tag.claim(self.getter, name=inputTag.name+".lowpass",priority=priority)
        
        if interval==None:
            self.tag.interval = timeConstant/2
        else:
            self.tag.interval=interval

    
    def doInput(self,val, ts,annotation):
        "On new data, we poll the output tag which also loads the input tag data."
        self.tag.poll()
    
    def getter(self):
        self.state=self.inputTag.value

        #Get the average state over the last period
        state = (self.state+self.lastState)/2
        t=time.monotonic()-self.lastRanFilter
        self.filtered= (self.filtered+((state-self.filtered)*(1-(self.k**t))))
        self.lastRanFilter+=t

        self.lastState = self.state

        #Suppress extremely small changes that lead to ugly decimals and network traffic
        if abs(self.filtered-self.state)<(self.filtered/1000000.0):
            return self.state
        else:
            return self.filtered


class HysteresisFilter(Filter):
    def __init__(self, name, inputTag,  hysteresis=0, priority=60):
        self.state = inputTag.value

        #Start at midpoint with the window centered
        self.hysteresisUpper = self.state+hysteresis/2
        self.hysteresisLower = self.state+hysteresis/2
        self.lock = threading.Lock()

        self.inputTag =inputTag
        inputTag.subscribe(self.doInput)
    
        self.tag= _NumericTagPoint(name)
        self.claim = self.tag.claim(self.getter, name=inputTag.name+".hysteresis",priority=priority)
    
    def doInput(self,val, ts,annotation):
        "On new data, we poll the output tag which also loads the input tag data."
        self.tag.poll()
    
    def getter(self):
        with self.lock:
            self.lastState = self.state
            
            if val>=self.hysteresisUpper:
                self.state=val
                self.hysteresisUpper = val
                self.hysteresisLower = val-self.hysteresis
            elif val<=self.hysteresisLower:
                self.state=val
                self.hysteresisUpper = val+self.hysteresis
                self.hysteresisLower = val
            return self.state

def createGetterFromExpression(e, t):
    t.sourceTags = {}
    def recalc(*a):
        t()
    t.recalcHelper = recalc
    def t(n,t):
        try:
            return t.sourceTags[n].value
        except KeyError:
            if n in allTags:
                try:
                    #We aren't just going to create the tag, we don't know the type.
                    t.sourceTags[n] = allTags[n]
                    #When any source tag updates, we want to recalculate.
                    t.sourceTags[n].subscribe(recalc)
                    return t.sourceTags[n].value
                except KeyError:
                    #NOt in any way neccesary, but this lets us resolve dependancy in
                    #A hurry
                    if lock.accquire(timeout=1):
                        try:
                            if n in recalcOnCreate:
                                t.recalcOnCreateList = recalcOnCreate[n]
                            else:
                                t.recalcOnCreateList=recalcOnCreate[n]=[]
                            
                            t.recalcOnCreateList.append(t)
                        finally:
                            lock.release()
        return 0

    evalContext ={
        "time": time,
        "math": math,
        "t": t,
    }

    c = compile(e,t.name+"_expr","eval")
    def f():
        return(eval(c,evalContext, evalContext))
    t.value=f
    
Tag = _NumericTagPoint.Tag
ObjectTag = _TagPoint.Tag
StringTag = _StringTagPoint.Tag