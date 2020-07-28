
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

import threading,time,logging,uuid,weakref,gc,uuid,traceback,os

from . import workers,messagebus

initialized = False
initlock = threading.Lock()
Gst = None
lock = threading.RLock()
jackChannels = {}

def tryToAvoidSegfaults(t,v):
    if v.clientName=="system":
        stopAllJackUsers()
messagebus.subscribe("/system/jack/delport",tryToAvoidSegfaults)

pipes = weakref.WeakValueDictionary()

log = logging.getLogger("IceFlow_gst")

class PILCapture():
    def __init__(self,appsink):
        from PIL import Image

        self.img = Image
        self.appsink=appsink

    def pull(self):
        sample = self.appsink.emit('try-pull-sample', 0.1*10**9)
        if not sample:
            return None

        buf = sample.get_buffer()
        caps = sample.get_caps()
        h=caps.get_structure(0).get_value('height')
        w=caps.get_structure(0).get_value('width')

        return self.img.frombytes("RGB", (w, h), buf.extract_dup(0, buf.get_size()))



class PILSource():
    def __init__(self,appsrc,greyscale=False):
        self.appsrc=appsrc
        self.greyscale = greyscale


    def push(self,img):
        img = img.tobytes("raw","L" if self.greyscale else "rgb")
        img = Gst.Buffer.new_wrapped(img)
        self.appsrc.emit("push-buffer", img)

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
                raise RuntimeError("Could not link: "+str(a)+str(b))

        elif not a.link(b):
            raise RuntimeError("Could not link"+str(a)+str(b))
    finally:
        if unref:
            pass#b.unref()

def stopAllJackUsers():
    #It seems best to stop everything using jack before stopping and starting the daemon.
    with lock:
        c = list(jackChannels.items())
        for i in c:
            #Sync stop, we gotta wait
            try:
                i[1]().syncStop=True
                i[1]().stop()
            except:
                log.exception("Err stopping JACK user")
        del c
        #Defensive programming against a double stop, which might be something that
        #No longer is in a state that can be touched without a segfault
        try:
            if i[0] in jackChannels:
                del jackChannels[i[1]]
        except:
            pass

def elementInfo(e):
    r=Gst.Registry.get()

def Element(n,name=None):
    e = Gst.ElementFactory.make(n,None)
    if e:
        return e
    else:
        raise ValueError("No such element exists: "+n)
loop = None

autorunMainloop = True

mainContext = None

def init():
    "On demand loading, for startup speed but also for compatibility if Gstreamer isn't there"
    global initialized, Gst,loop,mainContext
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

            #mainContext = GLib.MainContext()

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

def makeWeakrefPoller(selfref,exitSignal):

    def pollerf():
        alreadyStarted = False
        lastAdjustment=0
        #Last time we adjusted, how much error was left?
        lastRemnantError=0
        computeRemnant=False

        avgDiff = 0
        while selfref():
            self=selfref()
            
            self.threadStarted = True
            if not self.running:
                exitSignal.append(True)
                return
            
            if self.running:
                t=time.monotonic()
                try:
                    with self.lock:
                        self.loopCallback()
                    
                        state = self.pipeline.get_state(1000000000)[1]
                    if not state==Gst.State.NULL:
                        self.wasEverRunning=True

                    #Set the flag if anything ever drives us into the null state
                    if self.wasEverRunning and state==Gst.State.NULL:
                        self.running=False
                        exitSignal.append(True)
                        return

                except:
                    #Todo actually handle some errors?
                    exitSignal.append(True)
                    #After pipeline deleted, we clean up
                    if hasattr(self,'pipeline') and  hasattr(self,'bus'):
                        raise
                    else:
                        return
            
            del self
            time.sleep(1)
    return pollerf




def getCaps(e):
    try:
        return e.caps
    except:
        return "UNKNOWN"
    e.getSinks()[0].getNegotiatedCaps()


def linkClosureMaker(self, src, dest,connectWhenAvailable,eid):
    "This has t be outside, it can't leak a ref to self's strong reference into the closure or it may leak memory"
    def linkFunction(element, pad,dummy):
        s = pad.query_caps(None).to_string()
        if isinstance(connectWhenAvailable,str):
            if not connectWhenAvailable in s:
                return

        if eid in self().waitingCallbacks:
            link(element,dest)
        del self().waitingCallbacks[eid]
    return linkFunction

class GStreamerPipeline():
    """Semi-immutable pipeline that presents a nice subclassable GST pipeline You can only add stuff to it.
    """
    def __init__(self, name=None, realtime=None, systemTime =False):
        init()
        self.exiting = False

        self.uuid = uuid.uuid4()
        name=name or "Pipeline"+str(time.monotonic())
        gc.collect()
        self.realtime = realtime
        self.lock = threading.RLock()
        self._stopped=True
        self.syncStop=False
        self.pipeline = Gst.Pipeline()
        self.threadStarted=False
        self.weakrefs = weakref.WeakValueDictionary()



        #This WeakValueDictionary is mostly for testing purposes
        pipes[id(self)]=self
        
        #Thread puts something in this so we know we exited
        self.exitSignal  =[]

        self.weakrefs[str(self.pipeline)]=self.pipeline
        if not self.pipeline:
            raise RuntimeError("Could not create pipeline")
        if not initialized:
            raise RuntimeError("Gstreamer not set up")
        self.bus = self.pipeline.get_bus()
        self._stopped=False

        self.weakrefs[str(self.bus)]=self.bus

        self.hasSignalWatch=0

        #Run in our own mainContext
        #mainContext.push_thread_default()
        try:
            self.bus.add_signal_watch()
        finally:
            pass#mainContext.pop_thread_default()


        self.hasSignalWatch = 1
        #1 is dummy user data, because some have reported segfaults if it is missing
        #Note that we keep strong refs to the functions, so they don't go away when we unregister,
        #Leading to a segfault in libffi because of a race condition
        self._onmessage = wrfunc(weakref.WeakMethod(self.on_message))
        self.pgbcobj = self.bus.connect('message',self._onmessage,1)
        
        self._oneos = wrfunc(weakref.WeakMethod(self.on_eos))
        self.pgbcobj2 = self.bus.connect("message::eos", self._oneos,1)

        self._onerror = wrfunc(weakref.WeakMethod(self.on_error))
        self.pgbcobj3 = self.bus.connect("message::error", self._onerror,1)
        self.name = name

        self.elements = []
        self.sidechainElements = []
        self.namedElements = {}

        self.elementTypesById= {}


        #Just a place to store refs
        self.waitingCallbacks= {}

        self.running = False
        self.wasEverRunning = True
        
        self.knownThreads= {}
        self.startTime = 0
        def dummy(*a,**k):
            pass
        self._syncmessage = wrfunc(weakref.WeakMethod(self.syncMessage),fail_return=Gst.BusSyncReply.PASS)
        self.bus.set_sync_handler(self._syncmessage,0,dummy)
        self.pollthread=None

        self.lastElementType = None
        
        #If true, keep the pipeline running at the same rate as system time
        self.systemTime = systemTime
        self.targetRate = 1.0
        self.pipelineRate = 1.0



    def sendEOS(self):
        self.pipeline.send_event(Gst.Event.new_eos())    

    def loopCallback(self):
        #Meant to subclass. Gets called under the lock
        pass
    def seek(self, t=None,rate=None, _raw=False,_offset=0.008):
        "Seek the pipeline to a position in seconds, set the playback rate, or both"
        with self.lock:
            if self.exiting:
                return
            if not self.running:
                return
            
            if rate is None:
                rate=self.targetRate

           
            if not _raw:
                #Set "effective start time" so that the system clock sync keeps working.
                if not t is None:
                    t= max(t,0)
                    self.startTime = time.monotonic()-t
                self.targetRate = rate
                self.pipelineRate = rate
            self.pipeline.seek (rate, Gst.Format.TIME,
            Gst.SeekFlags.SKIP|Gst.SeekFlags.FLUSH, Gst.SeekType.NONE if t is None else Gst.SeekType.SET, max((t+_offset or 0)*10**9,0),
            Gst.SeekType.NONE, -1)
    
    def getPosition(self):
        "Returns stream position in seconds"
        with self.lock:
            ret,current = self.pipeline.query_position(Gst.Format.TIME)
            if not ret:
               raise RuntimeError(ret)
            if current <0:
                raise RuntimeError("Nonsense position: "+str(current))
            if current==Gst.CLOCK_TIME_NONE:
                raise RuntimeError("gst.CLOCK_TIME_NONE")
            return current/10**9

    @staticmethod
    def setCurrentThreadPriority(x,y):
        raise RuntimeError("Must override this to use realtime priority")

    def syncMessage(self,*arguments):
        "Synchronous message, so we can enable realtime priority on individual threads."
        #Stop the poorly performing sync messages after a while.
        #Wait till we have at least one thread though.
        try:
            if self.knownThreads and time.monotonic()-self.startTime>3:
                #This can't use the lock, we don't know what thread it might be called in.
                def noSyncHandler():
                    with self.lock:
                        if hasattr(self,'bus'):
                            self.bus.set_sync_handler(None,0,None)
                workers.do(noSyncHandler)
            if not threading.currentThread().ident in self.knownThreads:
                self.knownThreads[threading.currentThread().ident] = True
                if self.realtime:
                    try:
                        self.setCurrentThreadPriority(1,self.realtime)
                    except:
                        log.exception("Error setting realtime priority")
            return Gst.BusSyncReply.PASS
        except:
            return Gst.BusSyncReply.PASS
            print(traceback.format_exc())
    
    def makeElement(self,n,name=None):
        with self.lock:
            e = Element(n,name)
            self.elementTypesById[id(e)] = n
            self.pipeline.add(e)
            return e

    
    #Low level wrapper just for filtering out args we don't care about
    def on_eos(self,*a,**k):
        self.onEOS()

    def onEOS(self):
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
        
        #Give it some time, in case it really was started
        if not self.threadStarted:
            time.sleep(0.01)
            time.sleep(0.01)
            time.sleep(0.01)
            time.sleep(0.01)
            
        if self.threadStarted:
            while not self.exitSignal:
                time.sleep(0.1)
                if time.monotonic()-t> 10:
                    raise RuntimeError("Timeout")
                
        with self.lock:
            if not self._stopped:
                self.stop()


       
        

    def on_message(self, bus, message,userdata):
        s = message.get_structure()
        if s:
            self.onMessage(message.src,s.get_name(), s)
        return True

    def onMessage(self,src,name, structure):
        pass

    def on_error(self,bus,msg,userdata):
        logging.debug('Error {}: {}, {}'.format(msg.src.name, *msg.parse_error()))



    def _waitForState(self,s,timeout=10):
        t=time.monotonic()
        while not self.pipeline.get_state(1000_000_000)[1]==s:
            if time.monotonic()-t> timeout:
                raise RuntimeError("Timeout, pipeline still in: ", self.pipeline.get_state(1000_000_000)[1])
            time.sleep(0.1)

    def start(self, effectiveStartTime=None,timeout=10):
        "effectiveStartTime is used to keep multiple players synced when used with systemTime"
        with self.lock:
            if self.exiting:
                return

                        
            x = effectiveStartTime or time.time()
            timeAgo = time.time()-x
            #Convert to monotonic time that the nternal APIs use
            self.startTime= time.monotonic()-timeAgo
            
            
            if not self.pipeline.get_state(1000_000_000)[1] ==Gst.State.PAUSED:
                self.pipeline.set_state(Gst.State.PAUSED)
                self._waitForState(Gst.State.PAUSED)
            
            #Seek to where we should be, if we had actually
            #Started when we should have. We want to get everything set up in the pause state
            #First so we have the right "effective" start time.

            #We accept cutting off a few 100 milliseconds if it means
            #staying synced.
            if self.systemTime:
                self.seek(time.monotonic()-self.startTime)

            self.pipeline.set_state(Gst.State.PLAYING)
            self._waitForState(Gst.State.PLAYING,timeout)
            self.running=True

            for i in range(0,500):
                try:
                    #Test that we can actually read the clock
                    self.getPosition()
                    break
                except:
                    if i>150:
                        raise RuntimeError("Clock still not valid")
                    time.sleep(0.1)

            #Don't start the thread until we have a valid clock
            self.maybeStartPoller()

    def play(self):
        with self.lock:
            if self.exiting:
                return
            if not self.running:
                raise RuntimeError("Pipeline is not paused, or running, call start()")
            if not self.pipeline.get_state(1000_000_000)[1] in (Gst.State.PLAYING,Gst.State.PAUSED,Gst.State.READY):
                raise RuntimeError("Pipeline is not paused, or running, call start()")
            
            #Hopefully this willl raise an error if the clock is invalid for some reason,
            #Instead of potentially causing a segfault, if that was the problem
            self.getPosition()
            
            self.pipeline.set_state(Gst.State.PLAYING)
            self._waitForState(Gst.State.PLAYING)

    def pause(self):
        "Not that we can start directly into paused without playing first, to preload stuff"
        with self.lock:
            if self.exiting:
                return
            self.pipeline.set_state(Gst.State.PAUSED)
            self._waitForState(Gst.State.PAUSED)
            self.getPosition()
            self.running=True
            self.maybeStartPoller()
    
    def maybeStartPoller(self):
        if not self.pollthread:
            self.pollthread = threading.Thread(target=makeWeakrefPoller(weakref.ref(self),self.exitSignal),daemon=True,name="nostartstoplog.GSTPoller")
            self.pollthread.daemon=True
            self.pollthread.start()

    def stop(self):
        #Actually stop as soon as we can
        with self.lock:
            if hasattr(self,'pipeline'):
                #This was causing segfaults for some reasons
                if not (self.pipeline.get_state(1000_000_000)[1]==Gst.State.NULL):
                    self.pipeline.set_state(Gst.State.NULL)
            self.exiting = True
            if hasattr(self,'bus'):
                self.bus.set_sync_handler(None,0,None)
                if self.hasSignalWatch:
                    self.bus.remove_signal_watch()
                    self.hasSignalWatch = False
        
        #Now we're going to do the cleanup stuff
        #In the background, because it involves a lot of waiting.
        #This might fail, if it never even started, but we just kinda ignore that.
        def gstStopCleanupTask():
            self.running=False
            t = time.monotonic()
            time.sleep(0.01)
            
            
            if not self.threadStarted:
                time.sleep(0.01)
                time.sleep(0.01)
                time.sleep(0.01)
                time.sleep(0.01)
            
            #On account of the race condition, it is possible that the thread actually never did start yet
            #So we have to ignore the exit flag stuff.
            
            #It shouldn't really be critical, most likely the thread can stop on it's own time anyway, because it doesn't do anything without getting the lock.
            if self.threadStarted:
                while not self.exitSignal:
                    time.sleep(0.1)
                    if time.monotonic()-t> 10:
                        break
                
            with self.lock:
                if self._stopped:
                    return

                self.pipeline.set_state(Gst.State.NULL)
                self._waitForState(Gst.State.NULL,10000)

                #This stuff happens in the NULL state, because we prefer not to mess with stuff while it's
                #Running
                try:
                    self.bus.disconnect(self.pgbcobj)
                    del self.pgbcobj
                    self.bus.disconnect(self.pgbcobj2)
                    del self.pgbcobj2
                    self.bus.disconnect(self.pgbcobj3)
                    del self.pgbcobj3
                except:
                    print(traceback.format_exc())
    

                del self.elements
                del self.namedElements
                del self.pipeline
                del self.bus

                try:
                    del jackChannels[self.uuid]
                except:
                    pass
                self._stopped=True

        #Allow waiting so we can be real sure it's stopped
        if not self.syncStop:
            workers.do(gstStopCleanupTask)
        else:
            gstStopCleanupTask()
        
       

    @staticmethod
    def shouldAllowGstJack():
        raise RuntimeError("You must override this method to return True if jackd is running and can be used")

    def addPILCapture(self,resolution,connectToOutput=None, buffer=1):
        "Return a video capture object"
        conv = self.addElement("videoconvert",connectToOutput=connectToOutput)
        scale=self.addElement("videoscale")
        caps = self.addElement("capsfilter",caps="video/x-raw,width="+str(resolution[0])+",height="+str(resolution[0])+", format=RGB")
        appsink = self.addElement("appsink",drop=True,sync=False,max_buffers=buffer)

        return PILCapture(appsink)

    def addPILSource(self,resolution, buffer=1,greyscale=False):
        "Return a video source object that we can use to put PIL buffers into the stream"

        appsrc = self.addElement("appsrc",caps="video/x-raw,width="+str(resolution[0])+",height="+str(resolution[0])+", format="+"GREy8" if greyscale else "RGB",connectToOutput=False)
        conv = self.addElement("videoconvert")
        scale=self.addElement("videoscale")

        #Start with a blck image to make things prerooll
        if(greyscale):
            appsrc.emit("push-buffer", Gst.Buffer.new_wrapped(bytes(resolution[0]*resolution[1])))
        else:
            appsrc.emit("push-buffer",Gst.Buffer.new_wrapped( bytes(resolution[0]*resolution[1]*3)))

      

        return PILSource(appsrc,greyscale)
    
    def addElement(self,t,name=None,connectWhenAvailable=False, connectToOutput=None, sidechain=False, **kwargs):

        #Don't let the user use JACK if it's not running,
        #For fear of gstreamer undefined behavior
        if t.startswith("jackaudio"):
            if not self.shouldAllowGstJack():
                raise RuntimeError("JACK not running")
        
        with self.lock:
            if not isinstance(t, str):
                raise ValueError("Element type must be string")

            e = Gst.ElementFactory.make(t,name)
            
            if e==None:
                raise ValueError("Nonexistant element type: "+t)
            self.weakrefs[str(e)]=e
            self.elementTypesById[id(e)] = t


            for i in kwargs:
                v = kwargs[i]
                self.setProperty(e,i,v)
                
            self.pipeline.add(e)

        
            if connectToOutput:
                if not id(connectToOutput) in self.elementTypesById:
                    raise ValueError("Cannot connect to the output of: "+str(connectToOutput)+", no such element in pipeline.")
            
            #Element doesn't have an input pad, we want this to be usable as a fake source to go after a real source if someone
            #wants to use it as a effect
            if t=="audiotestsrc":
                connectToOutput=False
                


            #This could be the first element
            if self.elements and (not (connectToOutput is False)):
                connectToOutput=connectToOutput or self.elements[-1]

                #Fakesinks have no output, we automatically don't connect those
                if self.elementTypesById[id(connectToOutput)]=='fakesink':
                    connectToOutput=False

                #Decodebin doesn't have a pad yet for some awful reason
                elif (self.elementTypesById[id(connectToOutput)]=='decodebin') or connectWhenAvailable:
                    eid = uuid.uuid4()
                    f = linkClosureMaker(weakref.ref(self),connectToOutput,e,connectWhenAvailable, eid)

                    self.waitingCallbacks[eid]=f
                    #Dummy 1 param because some have claimed to get segfaults without
                    connectToOutput.connect("pad-added",f,1)
                else:
                    link(connectToOutput,e)
            
            #Sidechain means don't set this element as the
            #automatic thing that the next entry links to
            if not sidechain:
                self.elements.append(e)
            else:
                self.sidechainElements.append(e)

            self.namedElements[name]=e

            #Mark as a JACK user so we can stop if needed for JACK
            #Stuff
            if t.startswith("jackaudio"):
                with lock:
                    jackChannels[self.uuid] = weakref.ref(self)

            self.lastElementType = t
            p= weakref.proxy(e)
            #List it under the proxy as well
            self.elementTypesById[id(p)] = t
            return p


    def setProperty(self, element, prop,value):
        with self.lock:

            if prop=="location" and self.elementTypesById[id(element)]=='filesrc':
                if not os.path.isfile(value):
                    raise ValueError("No such file: "+value)
                
            if prop=='caps':
                value=Gst.Caps(value)
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
    def isActive(self):
        with self.lock:
            if self.pipeline.get_state(1000_000_000)[1] ==Gst.State.PAUSED:
                return True
            if self.pipeline.get_state(1000_000_000)[1] ==Gst.State.PLAYING:
                return True
#Legacy misspelling
GstreamerPipeline= GStreamerPipeline