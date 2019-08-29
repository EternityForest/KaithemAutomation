
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

import threading,time,logging

from . import jackmanager

initialized = False
initlock = threading.Lock()
Gst = None
lock = threading.RLock()
jackChannels = {}


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

class AudioFilePlayer():
    def __init__(self, file, output=None):
        init()
        self.lock = threading.Lock()
        self.pipeline = Gst.Pipeline()
        self.name = name

        self.src = Gst.ElementFactory.make('filesrc')
        self.src.set_property("file", file)

        self.decoder = Gst.ElementFactory.make('decodebin')
        self.converter = Gst.ElementFactory.make('audioconvert')
        self.converter2 = Gst.ElementFactory.make('audioresample')

        self.pipeline.add(self.decoder)
        self.pipeline.add(self.converter)
        self.pipeline.add(self.converter2)

        self.src.link(self.decoder)
        self.decoder.link(self.converter)
        self.converter.link(self.converter2)

        if output=="__auto__":
            self.sink = Gst.ElementFactory.make('autoaudiosink')
        if ":" in output:
            self.sink = Gst.ElementFactory.make('jackaudiosink')
            self.sink.set_property("buffer-time",8000)
            self.sink.set_property("latency-time",4000)
            self.sink.set_property("sync",False)
            self.sink.set_property("slave-method",2)
            self.sink.set_property("port-pattern","fdgjkndgmkndfmfgkjkf")
            self.sink.connect=0
            self.aw = jackmanager.Airwire(self.name+"_out", i)



        self.pipeline.add(self.sink)
        self.converter2.link(self.sink)

    def pause(self):
        self.pipeline.set_state(Gst.State.PAUSED)

    def play(self):
        self.pipeline.set_state(Gst.State.PLAYING)





def getCaps(e):
    try:
        return e.caps
    except:
        return "UNKNOWN"
    e.getSinks()[0].getNegotiatedCaps()

class Pipeline():
    "Semi-immutable pipeline. You can only add stuff to it"
    def __init__(self, name):
        init()
        self.lock = threading.RLock()
        self.pipeline = Gst.Pipeline()
        if not self.pipeline:
            raise RuntimeError("Could not create pipeline")
        if not initialized:
            raise RuntimeError("Gstreamer not set up")
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.pgbcobj = self.bus.connect('message',self.on_message)
        self.bus.connect("message::error", self.on_error)
        self.name = name

        self.elements = []
        self.namedElements = {}

        self.running = False

    
    def makeElement(self,n,name=None):
        with self.lock:
            e = Element(n,name)
            self.pipeline.add(e)
            return e

    def pollerf(self):
        while self.running:
            with self.lock:
                if self.running:
                    self.bus.poll(Gst.MessageType.ANY,0.1)
        
        
    def __del__(self):
        self.running=False
        with self.lock:
            try:
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
        print("*******************************************************************",message)  
        return True

    def on_error(self,bus,message):
        logging.debug(str(message))



   

    def start(self):
        with self.lock:
            self.pipeline.set_state(Gst.State.PLAYING)
            self.running=True
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
                link(self.elements[-1],e)
            self.elements.append(e)
            self.namedElements[name]=e

            #Mark as a JACK user so we can stop if needed for JACK
            #Stuff
            if t.startswith("jackaudio"):
                with lock:
                    jackChannels[self.name] = self
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