
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

import threading,time,logging,uuid

from . import jackmanager,workers

initialized = False
initlock = threading.Lock()
Gst = None
lock = threading.RLock()
jackChannels = {}

log = logging.getLogger("gstwrapper")
#Try to import a cython extension that only works on Linux
try:
    from . import threadpriority
    setPririority = threadpriority.setThreadPriority
except:
    log.exception("Cython import failed, gstreamer realtime priority is disabled")
    setPririority = lambda p,po:None



def link(a,b):

    if not a or not b:
        raise ValueError("Cannot link None")
    if isinstance(a, Gst.Pad):
        if not isinstance(b,Gst.Pad):
            b = b.get_static_pad("sink")
            if not b:
                raise RuntimeError("B has no pad named sink and A is a pad") 
        if not a.link(b)==Gst.PadLinkReturn.OK:
            raise RuntimeError("Could not link")

    elif not a.link(b):
        raise RuntimeError("Could not link")

def stopAllJackUsers():
    #It seems best to stop everything using jack before stopping and starting the daemon.
    with lock:
        for i in jackChannels:
            jackChannels[i].stop()

def elementInfo(e):
    r=Gst.Registry.get()

def Element(n,name=None):
    e = Gst.ElementFactory.make(n,None)
    if e:
        return e
    else:
        raise ValueError("No such element exists: "+n)
def init():
    "On demand loading, for startup speed but also for compatibility if Gstreamer isn't there"
    global initialized, Gst
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
            from gi.repository import GObject, GstBase, Gtk, GObject
            Gst = gst
            Gst.init(None)
            initialized = True



def doesElementExist(n):
    n =Gst.ElementFactory.make(n)
    if n:
        n.unref()
    return True







def getCaps(e):
    try:
        return e.caps
    except:
        return "UNKNOWN"
    e.getSinks()[0].getNegotiatedCaps()

class Pipeline():
    "Semi-immutable pipeline. You can only add stuff to it"
    def __init__(self, name, realtime=70, systemTime =False):
        init()
        self.realtime = 70
        self.lock = threading.RLock()
        self.pipeline = Gst.Pipeline()
        if not self.pipeline:
            raise RuntimeError("Could not create pipeline")
        if not initialized:
            raise RuntimeError("Gstreamer not set up")
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.pgbcobj = self.bus.connect('message',self.on_message)
        self.pgbcobj2 = self.bus.connect("message::eos", self.on_eos)
        self.bus.connect("message::error", self.on_error)
        self.name = name

        self.elements = []
        self.namedElements = {}

        #Just a place to store refs
        self.waitingCallbacks= []

        self.running = False
        
        self.knownThreads= {}
        self.startTime = 0
        def dummy(*a,**k):
            pass
        self.bus.set_sync_handler(self.syncMessage,0,dummy)
        self.pollthread=None

        self.lastElementType = None
        
        #If true, keep the pipeline running at the same rate as system time
        self.systemTime = systemTime
        self.targetRate = 1.0
        self.pipelineRate = 1.0
        
    
    def seek(self, time=None,rate=1.0):
        "Seek the pipeline to a position in seconds, set the playback rate, or both"
        with self.lock:
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
        if self.knownThreads and time.monotonic()-self.startTime>3:
            def f():
                with self.lock:
                    self.bus.set_sync_handler(None,0,None)
            workers.do(f)
        if not threading.currentThread().ident in self.knownThreads:
            self.knownThreads[threading.currentThread().ident] = True
            if self.realtime:
                try:
                    setPririority(1,self.realtime)
                except:
                    log.exception("Error setting realtime priority")
        return Gst.BusSyncReply.PASS
    
    def makeElement(self,n,name=None):
        with self.lock:
            e = Element(n,name)
            self.pipeline.add(e)
            return e

    def pollerf(self):
        alreadyStarted = False
        while self.running:
            with self.lock:
                if self.running:
                    self.bus.poll(Gst.MessageType.ANY,0.1)

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
    
    def on_eos(self,*a,**k):
        #Some kinda deadlock happened here between this and the delete function.
        #So we just try our best to stop and excpect the del function to catch it in cases of deadlock.
        #Our backup plan is to try doing it from another thread
        
        def f():
            if self.lock.acquire(timeout=0.1):
                try:
                    if self.running:
                        self.running=False
                        self.stop()
                        return True
                finally:
                    self.lock.release()
        
        def f2():
            try:
                f()
            except:
                pass
        if not f():
            workers.do(f2)

        self.onStreamFinished()
    def onStreamFinished(self):
        pass

    def __del__(self):
        with self.lock:
            try:
                if self.running:
                    self.running=False
                    self.pipeline.set_state(Gst.State.NULL)
            except:
                pass
        with lock:
            try:
                del jackChannels[self]
            except:
                pass
        self.pipeline.unref()

    def on_message(self, bus, message):
        return True

    def on_error(self,bus,message):
        logging.debug(str(message))



   

    def start(self, effectiveStartTime=None):
        "effectiveStartTime is used to keep multiple players synced when used with systemTime"
        with self.lock:
            x = effectiveStartTime or time.time()
            timeAgo = time.time()-x
            #Convert to monotonic time that the nternal APIs use
            self.startTime= time.monotonic()-timeAgo
            self.pipeline.set_state(Gst.State.PAUSED)

            #Seek to where we should be, if we had actually
            #Started when we should have.
            if self.systemTime:
                self.seek(time.monotonic()-self.startTime)

            self.pipeline.set_state(Gst.State.PLAYING)
            self.running=True
            if not self.pollthread:
                self.pollthread = threading.Thread(target=self.pollerf,daemon=True,name="GSTPoller")
                self.pollthread.daemon=True
                self.pollthread.start()

    def play(self):
        with self.lock:
            if not self.running:
                raise RuntimeError("Pipeline is not paused, or running, call start()")
            self.pipeline.set_state(Gst.State.PLAYING)
            
    def pause(self):
        "Not that we can start directly into paused without playing first, to preload stuff"
        with self.lock:
            self.pipeline.set_state(Gst.State.PAUSED)
            self.running=True
            if not self.pollthread:
                self.pollthread = threading.Thread(target=self.pollerf,daemon=True,name="GSTPoller")
                self.pollthread.daemon=True
                self.pollthread.start()

    def stop(self):
        self.running=False
        with self.lock:
            self.pipeline.set_state(Gst.State.NULL)

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

                    def closureMaker(src, dest):
                        def f(element, pad):
                            link(element,dest)
                        return f
                    f = closureMaker(self.elements[-1],e)

                    self.waitingCallbacks.append(f)
                    self.elements[-1].connect("pad-added",f)
                else:
                    link(self.elements[-1],e)
            self.elements.append(e)
            self.namedElements[name]=e

            #Mark as a JACK user so we can stop if needed for JACK
            #Stuff
            if t.startswith("jackaudio"):
                with lock:
                    jackChannels[self.name] = self

            self.lastElementType = t
            return e

    def setProperty(self, element, prop,value):
        with self.lock:

            if prop=='caps':
                value=Gst.caps(value)
            prop=prop.replace("_","-")

            prop=prop.split(":")
            if len(prop)>1:
                childIndex=int(prop[0])
                target= element.get_child_by_index(childIndex)
                target.set_property(prop[1], value)
            else:
                element.set_property(prop[0], value)




# import time
# p = Pipeline("test", outputs=["system"])
# p.finalize()
# time.sleep(2)
# p.connect()

# while(1):
#     pass