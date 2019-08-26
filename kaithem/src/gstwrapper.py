
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


def elementInfo(e):
    r=Gst.Registry.get()
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





       

class Pipeline():
    def __init__(self, name, channels= 2, input=None, outputs=[]):
        init()
        self.lock = threading.RLock()
        if not jackmanager.getPorts():
            raise RuntimeError("JACK not running")
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

        self.src = Gst.ElementFactory.make('jackaudiosrc')
        if not self.src:
            raise RuntimeError("Could not create jack source")
        self.src.set_property("buffer-time",10)
        self.src.set_property("latency-time",10)

        self.capsfilter = Gst.ElementFactory.make('capsfilter')
        self.capsfilter.caps = Gst.Caps("audio/x-raw,channels="+str(channels))


        self.capsfilter2 = Gst.ElementFactory.make('capsfilter')
        self.capsfilter2.caps = Gst.Caps("audio/x-raw,channels="+str(channels))
        
        self.sink = Gst.ElementFactory.make('jackaudiosink')
        self.sink.set_property("buffer-time",8000)
        self.sink.set_property("latency-time",4000)
        self.sink.set_property("sync",False)
        self.sink.set_property("slave-method",2)


        self.src.connect = 0
        self.sink.connect=0

        #Random nonsense so they don't auto connect
        self.src.set_property("port-pattern","fdgjkndgmkndfmfgkjkf")
        self.sink.set_property("port-pattern","fdgjkndgmkndfmfgkjkf")

        self.src.set_property("client-name",name+"_in")
        self.sink.set_property("client-name",name+"_out")


        self.pipeline.add(self.src)
        self.pipeline.add(self.capsfilter)
        self.pipeline.add(self.capsfilter2)

        self.pipeline.add(self.sink)
        self.channels = channels

        if not self.src.link(self.capsfilter):
            raise RuntimeError

        self.elements = [self.capsfilter]
        self.input=input
        self._input= None
        self.outputs=outputs
        self._outputs = []
        self.sends = []
        self.sendAirwires =[]
        self.namedElements = {}

        self.usingJack=True
        self.running = False 
    def pollerf(self):
        while self.running:
            self.bus.poll(Gst.MessageType.ANY,1)
        
        
    def __del__(self):
        self.pipeline.unref()

    def on_message(self, bus, message):
        print("*******************************************************************",message)  
        return True

    def on_error(self,bus,message):
        logging.debug(str(message))


    def connect(self, restore=[]):
        self._outputs = []
        for i in self.outputs:
            x = jackmanager.Airwire(self.name+"_out", i)
            x.connect()
            self._outputs.append(x)

        self._input = jackmanager.Airwire(self.input, self.name+"_in") 
        self._input.connect()
        for i in restore:
            for j in i[1]:
                jackmanager.connect(i[0],j)

    def backup(self):
        c = []
        
        for i in jackmanager.getPorts(self.name+"_in:"):
            c.append((i, jackmanager.getConnections(i)))
        for i in jackmanager.getPorts(self.name+"_out:"):
            c.append((i, jackmanager.getConnections(i)))
        return c

    def setInput(self, input):
        with self.lock:
            self.input=input
            if self._input:
                self._input.disconnect()
            self._input = jackmanager.Airwire(self.input, self.name+"_in") 
            self._input.connect()

    def setOutputs(self, outputs):
        with self.lock:
            self.outputs = outputs
            for i in self._outputs:
                i.disconnect()
            
            self._outputs = []
            for i in self.outputs:
                x = jackmanager.Airwire(self.name+"_out", i)
                x.connect()
                self._outputs.append(x)

    def finalize(self):
        with self.lock:
            if not self.elements[-1].link(self.capsfilter2):
                raise RuntimeError("Could not link "+str(self.elements[-1])+" to "+str(self.sink))
            if not self.capsfilter2.link(self.sink):
                raise RuntimeError("Could not link "+str(self.capsfilter2)+" to "+str(self.sink))

            #I think It doesn't like it if you start without jack
            if self.usingJack:
                t=time.time()
                while(time.time()-t)<3:
                    if jackmanager.getPorts():
                        break
                if not jackmanager.getPorts():
                    return
            self.pipeline.set_state(Gst.State.PLAYING)
            self.running=True
            self.pollthread = threading.Thread(target=self.pollerf,daemon=True,name="GSTPoller")
            self.pollthread.start()

    def stop(self):
        self.running=False
        with self.lock:
            for i in self.sendAirwires:
                i.disconnect()
            if self._input:
                self._input.disconnect()
            for i in self._outputs:
                i.disconnect()
        
            self.pipeline.set_state(Gst.State.NULL)

    def addElement(self,t,name=None,**kwargs):
        with self.lock:
            if not isinstance(t, str):
                raise ValueError("Element type must be string")

            e = Gst.ElementFactory.make(t,name)

            if e==None:
                raise ValueError("Nonexistant element type")


            for i in kwargs:
                if not ":" in i:
                    if name=="capsfilter" and i=="caps" and isinstance(i,str):
                        e.set_property(i,Gst.Caps(kwargs[i]))
                    else:
                        v = kwargs[i]
                        i=i
                        e.set_property(i,v)
                
            self.pipeline.add(e)
            if not self.elements[-1].link(e):
                raise RuntimeError("Could not link "+str(self.elements[-1])+" to "+str(e))
            self.elements.append(e)
            self.namedElements[name]=e
            return e

    def setProperty(self, element, prop,value):
        with self.lock:
            prop=prop.replace("_","-")

            prop=prop.split(":")
            if len(prop)>1:
                childIndex=int(prop[0])
                target= element.get_child_by_index(childIndex)
                target.set_property(prop[1], value)
            else:
                element.set_property(prop[0], value)



    def addSend(self,target):
        with self.lock:
            if not isinstance(target, str):
                raise ValueError("Targt must be string")

            e = Gst.ElementFactory.make("tee")

            if e==None:
                raise ValueError("Nonexistant element type")

            e2 = Gst.ElementFactory.make("jacksink")
            e2.sink.set_property("buffer-time",8000)
            if e2==None:
                raise ValueError("Nonexistant element type jacksink")

            self.pipeline.add(e)
            self.pipeline.add(e2)
            e2.set_property("port-pattern","fdgjkndgmkndfmfgkjkf")
            #Sequentially number the sends
            cname = self.name+"_send"+str(len(self.sends))
            e2.set_property("client-name",cname)
            self.sendAirwires.append(jackmanager.Airwire(cname, target))
            self.sends.append(e2)


            self.elements[-1].link(e)
            self.elements.append(e)
            return e

# import time
# p = Pipeline("test", outputs=["system"])
# p.finalize()
# time.sleep(2)
# p.connect()

# while(1):
#     pass