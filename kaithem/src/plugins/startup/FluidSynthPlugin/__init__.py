from mako.lookup import TemplateLookup
from kaithem.src import devices, alerts, scheduling, messagebus, workers
from .scullery import iceflow, workers
import scullery
import os
import mako
import time
import threading
import logging
import weakref
import base64
import traceback
import shutil

from kaithem.src import widgets,jackmanager

logger = logging.Logger("plugins.fluidsynth")

templateGetter = TemplateLookup(os.path.dirname(__file__))


defaultSubclassCode = """
class CustomDeviceType(DeviceType):
    pass
"""


class JackFluidSynth(devices.Device):
    deviceTypeName = 'JackFluidSynth'
    readme = os.path.join(os.path.dirname(__file__), "README.md")
    defaultSubclassCode = defaultSubclassCode

    def close(self):
        devices.Device.close(self)
        try:
            self.synth.close()
        except:
            print(traceback.format_exc())


    def __del__(self):
        self.close()

    def makeWidgetHandler(self, c):
        def f(u,v):
            for i in v:
                if v=='pushed':
                    with self.synthLock:
                        self.synth.noteOn(c,60,64)
                else:
                    with self.synthLock:
                        self.synth.noteOff(c,60)
        return f

    def onMidiMsg(self, t,v):
        if v[0]=='noteon':
            self.noteOn(v[1],v[2],v[3])
        elif v[0]=='noteoff':
            self.noteOff(v[1],v[2])
        elif v[0]=='cc':
            self.cc(v[1],v[2],v[3])
        elif v[0]=='pitch':
            self.bend(v[1],v[2])

    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)
        self.widgets=[] 
        self.synth=None
        def f():
            try:
                if len(name)==1:
                    self.handleError('Single letter names may not work correctly.  JACK in general may have subpar performace with this plugin badly configured.')
                self.synthLock=threading.Lock()

                self.synth = scullery.fluidsynth.FluidSynth(
                                            soundfont=data.get("device.soundfont", "").strip(),
                                            jackClientName= name,
                                            connectOutput=data.get("device.connectOutput", "").strip()
                                            )


                for i in range(0,16):
                    try:
                        inst = ""
                        inst = data.get("device.ch"+str(i)+"instrument", "")
                        bank=None

                        if ':' in inst:
                            bank, inst= inst.split(":")
                            bank=int(bank.strip())
                        inst = inst.strip()

                        try:
                            inst= int(inst)
                        except:
                            pass

                    
                        if inst:
                            self.synth.setInstrument(i,inst,bank=bank)
                    except:
                        self.handleError("Error setting instrument:" +inst+" for channel "+str(i)+"\n"+traceback.format_exc())



                connectMidi=data.get("device.connectMidi", "").strip().replace(":",'_').replace("[",'').replace("]",'').replace(" ",'')

                messagebus.subscribe("/midi/"+connectMidi,self.onMidiMsg)
                
            

                
                for i in range(16):
                    x=widgets.Button()
                    x.attach(self.makeWidgetHandler(i))
                    self.widgets.append(x)
                    


            except:
                self.handleException()
        workers.do(f)


    def noteOn(self,c,p,v):
        def f():
            if not self.synth:
                return
            with self.synthLock:
                self.synth.noteOn(c,p,v)
        workers.do(f)

    def noteOff(self,c,p):
        def f():
            if not self.synth:
                return
            with self.synthLock:
                self.synth.noteOff(c,p)
        workers.do(f)

    def cc(self,c,p,v):
        def f():
            if not self.synth:
                return
            with self.synthLock:
                self.synth.cc(c,p,v)
        workers.do(f)

    def bend(self,c,v):
        def f():
            if not self.synth:
                return
            with self.synthLock:
                self.synth.pitchBend(c,v)
        workers.do(f)

    def pgc(self,c,v):
        def f():
            if not self.synth:
                return
            with self.synthLock:
                self.synth.programChange(c,v)
        workers.do(f)
    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["JackFluidSynth"] = JackFluidSynth