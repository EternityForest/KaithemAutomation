
#Copyright Daniel Dunn 2019
#This file is part of Kaithem Automation.

#Kaithem Automation is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#Kaithem Automation is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License


#This file really shouldn't have too many non-essential dependancies onthe rest of kaithem,
#Aside from the threadpool and the message bus.

import threading,time,logging,uuid,weakref,gc,uuid,traceback

from . import jackmanager,workers

initialized = False
initlock = threading.Lock()
Gst = None
lock = threading.RLock()
jackChannels = {}

pipes = weakref.WeakValueDictionary()

log = logging.getLogger("gstwrapper")
#Try to import a cython extension that only works on Linux
try:
    from . import threadpriority
    setPririority = threadpriority.setThreadPriority
except:
    log.exception("Cython import failed, gstreamer realtime priority is disabled")
    setPririority = lambda p,po:None



def link(a,b):
    unref = False
    try:
        if not a or not b:
            raise ValueError("Cannot link None")
        if isinstance(a, Gst.Pad):
            if not isinstance(b,Gst.Pad):
                b = b.get_static_pad("sink")
                unref=True
                if not b:
                    raise RuntimeError("B has no pad named sink and A is a pad") 
            if not a.link(b)==Gst.PadLinkReturn.OK:
                raise RuntimeError("Could not link")

        elif not a.link(b):
            raise RuntimeError("Could not link")
    finally:
        if unref:
            pass#b.unref()

def stopAllJackUsers():
    #It seems best to stop everything using jack before stopping and starting the daemon.
    with lock:
        for i in jackChannels:
            x=jackChannels[i]()
            if x:
                x.stop()
            del x

def elementInfo(e):
    r=Gst.Registry.get()

def Element(n,name=None):
    e = Gst.ElementFactory.make(n,None)
    if e:
        return e
    else:
        raise ValueError("No such element exists: "+n)
loop = None
def init():
    "On demand loading, for startup speed but also for compatibility if Gstreamer isn't there"
    global initialized, Gst,loop
    #Quick check outside the lock
    if initialized:
        return
    with initlock:
        if not initialized:
            import gi
            gi.require_version('Gst', '1.0')
            gi.require_version('GstBase', '1.0')
            gi.require_version('Gtk', '3.0')
            from gi.repository import Gst as gst
            from gi.repository import GObject, GstBase, Gtk, GObject,GLib
            Gst = gst
            Gst.init(None)
            glibloop = GLib.MainLoop()

            loop=threading.Thread(target=glibloop.run,daemon=True)
            loop.start()
            initialized = True



def doesElementExist(n):
    n =Gst.ElementFactory.make(n)
    if n:
        pass#n.unref()
    return True


def wrfunc(f,fail_return=None):
    def f2(*a,**k):
        try:
            return f()(*a,**k)
        except:
            print(traceback.format_exc())
            return fail_return
    return f2

def makeWeakrefPoller(selfref):

    def pollerf():
        alreadyStarted = False
        while selfref():
            self=selfref()
            
            if not self.running:
                self.exited=True
                return
            if self.running:
                t=time.monotonic()
               
                try:
                    with self.lock:
                        state = self.pipeline.get_state(1000000000)[1]
                    

                    if not state==Gst.State.NULL:
                        self.wasEverRunning=True

                    #Set the flag if anything ever drives us into the null state
                    if self.wasEverRunning and state==Gst.State.NULL:
                        self.running=False
                        self.exited=True
                        return
                        
                    #Some of this other stuff should be threadsafe but isn't
                    with self.lock:
                        if self.systemTime:
                            #Closed loop adjust the pipeline time.
                            t = self.pipeline.query_position(Gst.Format.TIME)/10**9
                            m = time.monotonic()

                            sysElapsed = (m-self.startTime)/self.targetRate
                            diff = t-sysElapsed
                            needAdjust = False
                            if diff>0.005:
                                self.pipelineRate = self.targetRate - 0.0003
                                needAdjust=True
                            elif diff<-0.005:
                                self.pipelineRate = self.targetRate + 0.0003
                                needAdjust=True

                            if needAdjust:
                                self.pipeline.seek (self.pipelineRate, Gst.Format.TIME,
                            Gst.SeekFlags.SKIP, Gst.SeekType.NONE,0,
                            Gst.SeekType.NONE, -1)
                except:
                    #After pipeline deleted, we clean up
                    if hasattr(self,'pipeline') and  hasattr(self,'bus'):
                        raise
                    else:
                        self.exited=True
                        return
            self.exited=True
            del self
            time.sleep(5)
    return pollerf




def getCaps(e):
    try:
        return e.caps
    except:
        return "UNKNOWN"
    e.getSinks()[0].getNegotiatedCaps()

class Pipeline():
    """Semi-immutable pipeline. You can only add stuff to it.
    """
    def __init__(self, name, realtime=70, systemTime =False):
        init()
        self.exiting = False

        self.uuid = uuid.uuid4()
        gc.collect()
        self.realtime = 70
        self.lock = threading.RLock()
        self._stopped=True
        self.pipeline = Gst.Pipeline()
        
        self.weakrefs = weakref.WeakValueDictionary()

        self.exited=False

        self.weakrefs[str(self.pipeline)]=self.pipeline
        if not self.pipeline:
            raise RuntimeError("Could not create pipeline")
        if not initialized:
            raise RuntimeError("Gstreamer not set up")
        self.bus = self.pipeline.get_bus()
        self._stopped=False

        self.weakrefs[str(self.bus)]=self.bus

        self.hasSignalWatch=0
        self.bus.add_signal_watch()
        self.hasSignalWatch = 1
        #1 is dummy user data, because some have reported segfaults if it is missing
        self.pgbcobj = self.bus.connect('message',wrfunc(weakref.WeakMethod(self.on_message)),1)
        self.pgbcobj2 = self.bus.connect("message::eos", wrfunc(weakref.WeakMethod(self.on_eos)),1)
        self.pgbcobj3 = self.bus.connect("message::error", wrfunc(weakref.WeakMethod(self.on_error)),1)
        self.name = name

        self.elements = []
        self.namedElements = {}

        #Just a place to store refs
        self.waitingCallbacks= {}

        self.running = False
        self.wasEverRunning = True
        
        self.knownThreads= {}
        self.startTime = 0
        def dummy(*a,**k):
            pass
        self.bus.set_sync_handler(wrfunc(weakref.WeakMethod(self.syncMessage), fail_return=Gst.BusSyncReply.PASS ),0,dummy)
        self.pollthread=None

        self.lastElementType = None
        
        #If true, keep the pipeline running at the same rate as system time
        self.systemTime = systemTime
        self.targetRate = 1.0
        self.pipelineRate = 1.0


        
    
    def seek(self, time=None,rate=1.0):
        "Seek the pipeline to a position in seconds, set the playback rate, or both"
        with self.lock:
            if self.exiting:
                return
            if not self.running:
                return

            #Set effective start time so that the system clock sync keeps working.
            if not time is None:
                self.startTime = time.monotonic()-time

            self.targetRate = rate
            self.pipelineRate = rate
            self.pipeline.seek (rate, Gst.Format.TIME,
            Gst.SeekFlags.SKIP, Gst.SeekType.NONE if time is None else Gst.SeekType.SET, time*10**9,
            Gst.SeekType.NONE, -1)
    
    def getPosition(self):
        "Returns stream position in seconds"
        with self.lock:
            return self.pipeline.query_position(Gst.Format.TIME)/10**9

    def syncMessage(self,*arguments):
        "Synchronous message, so we can enable realtime priority on individual threads."
        #Stop the poorly performing sync messages after a while.
        #Wait till we have at least one thread though.
        try:
            if self.knownThreads and time.monotonic()-self.startTime>3:
                #This can't use the lock, we don't know what thread it might be called in.
                def noSyncHandler():
                    with self.lock:
                        self.bus.set_sync_handler(None,0,None)
                workers.do(noSyncHandler)
            if not threading.currentThread().ident in self.knownThreads:
                self.knownThreads[threading.currentThread().ident] = True
                if self.realtime:
                    try:
                        setPririority(1,self.realtime)
                    except:
                        log.exception("Error setting realtime priority")
            return Gst.BusSyncReply.PASS
        except:
            return Gst.BusSyncReply.PASS
            print(traceback.format_exc())
    
    def makeElement(self,n,name=None):
        with self.lock:
            e = Element(n,name)
            self.pipeline.add(e)
            return e

    
    
    def on_eos(self,*a,**k):
        def f2():
            try:
                self.stop()
            except:
                pass
        workers.do(f2)

        self.onStreamFinished()

    def onStreamFinished(self):
        pass

    def __del__(self):
        self.running=False
        t=time.monotonic()
        while not self.exited:
            time.sleep(0.1)
            if time.monotonic()-t> 10:
                raise RuntimeError("Timeout")
        with self.lock:
            if not self._stopped:
                self.stop()

       
        

    def on_message(self, bus, message,userdata):
        return True

    def on_error(self,bus,msg,userdata):
        logging.debug('Error {}: {}, {}'.format(msg.src.name, *msg.parse_error()))



    def _waitForState(self,s,timeout=10):
        t=time.monotonic()
        while not self.pipeline.get_state(1000_000_000)[1]==s:
            if time.monotonic()-t> timeout:
                raise RuntimeError("Timeout")
            time.sleep(0.1)

    def start(self, effectiveStartTime=None):
        "effectiveStartTime is used to keep multiple players synced when used with systemTime"
        with self.lock:
            if self.exiting:
                return
            x = effectiveStartTime or time.time()
            timeAgo = time.time()-x
            #Convert to monotonic time that the nternal APIs use
            self.startTime= time.monotonic()-timeAgo
            self.pipeline.set_state(Gst.State.PAUSED)
            self._waitForState(Gst.State.PAUSED)
            
            #Seek to where we should be, if we had actually
            #Started when we should have.
            if self.systemTime:
                self.seek(time.monotonic()-self.startTime)

            self.pipeline.set_state(Gst.State.PLAYING)
            self._waitForState(Gst.State.PLAYING)
            self.running=True
            self.maybeStartPoller()

    def play(self):
        with self.lock:
            if self.exiting:
                return
            if not self.running:
                raise RuntimeError("Pipeline is not paused, or running, call start()")
            self.pipeline.set_state(Gst.State.PLAYING)
            self._waitForState(Gst.State.PAUSED)

    def pause(self):
        "Not that we can start directly into paused without playing first, to preload stuff"
        with self.lock:
            if self.exiting:
                return
            self.pipeline.set_state(Gst.State.PAUSED)
            self._waitForState(Gst.State.PAUSED)

            self.running=True
            self.maybeStartPoller()
    
    def maybeStartPoller(self):
        if not self.pollthread:
            self.pollthread = threading.Thread(target=makeWeakrefPoller(weakref.ref(self)),daemon=True,name="nostartstoplog.GSTPoller")
            self.pollthread.daemon=True
            self.pollthread.start()

    def stop(self):

        #Actually stop as soon as we can
        with self.lock:
            self.pipeline.set_state(Gst.State.NULL)
            self._waitForState(Gst.State.NULL)
            self.exiting = True

        #Now we're going to do the cleanup stuff
        #In the background, because it involves a lot of waiting
        def gstStopCleanupTask():
            self.running=False
            t = time.monotonic()
            time.sleep(0.01)
            while not self.exited:
                time.sleep(0.1)
                if time.monotonic()-t> 10:
                    raise RuntimeError("Timeout")
            with self.lock:
                if self._stopped:
                    return
                try:
                    self.bus.disconnect(self.pgbcobj)
                    self.bus.disconnect(self.pgbcobj2)
                    self.bus.disconnect(self.pgbcobj3)
                    self.bus.set_sync_handler(None,0,None)
                except:
                    print(traceback.format_exc())

                if self.hasSignalWatch:
                    self.bus.remove_signal_watch()
                while not self.pipeline.get_state(1000_000_000)[1]==Gst.State.NULL:
                    if time.monotonic()-t> 10:
                        raise RuntimeError("Timeout")
                    time.sleep(0.1)

                del self.elements
                del self.namedElements
                del self.pipeline
                del self.bus

                try:
                    del jackChannels[self.uuid]
                except:
                    pass
                self._stopped=True

        workers.do(gstStopCleanupTask)
        
       


    def addElement(self,t,name=None,**kwargs):

        #Don't let the user use JACK if it's not running,
        #For fear of gstreamer undefined behavior
        if t.startswith("jackaudio"):
            if not jackmanager.getPorts():
                raise RuntimeError("JACK not running")
        
        with self.lock:
            if not isinstance(t, str):
                raise ValueError("Element type must be string")

            e = Gst.ElementFactory.make(t,name)
            self.weakrefs[str(e)]=e
            if e==None:
                raise ValueError("Nonexistant element type")


            for i in kwargs:
                if not ":" in i:
                    if t=="capsfilter" and i=="caps" and isinstance(i,str):
                        e.set_property(i,Gst.Caps(kwargs[i]))
                    else:
                        v = kwargs[i]
                        i=i
                        e.set_property(i,v)
                
            self.pipeline.add(e)

            #This could be the first element
            if self.elements:
                #Decodeboin doesn't have a pad yet for some awful reason
                if self.lastElementType=='decodebin':
                    xx = uuid.uuid4()
                    def closureMaker(src, dest):
                        def linkFunction(element, pad,dummy):
                            link(element,dest)
                            del self.waitingCallbacks[xx]
                        return linkFunction
                    f = closureMaker(self.elements[-1],e)

                    self.waitingCallbacks[xx]=f
                    #Dummy 1 param because some have claimed to get segfaults without
                    self.elements[-1].connect("pad-added",f,1)
                else:
                    link(self.elements[-1],e)
            self.elements.append(e)
            self.namedElements[name]=e

            #Mark as a JACK user so we can stop if needed for JACK
            #Stuff
            if t.startswith("jackaudio"):
                with lock:
                    jackChannels[self.uuid] = weakref.ref(self)

            self.lastElementType = t
            return weakref.proxy(e)

    def setProperty(self, element, prop,value):
        with self.lock:

            if prop=='caps':
                value=Gst.caps(value)
                self.weakrefs[str(value)]=value

            prop=prop.replace("_","-")

            prop=prop.split(":")
            if len(prop)>1:
                childIndex=int(prop[0])
                target= element.get_child_by_index(childIndex)
                target.set_property(prop[1], value)
                self.weakrefs[str(target)+"fromgetter"]=target
            else:
                element.set_property(prop[0], value)
