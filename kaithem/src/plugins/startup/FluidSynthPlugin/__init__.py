from mako.lookup import TemplateLookup
from src import devices, alerts, scheduling, messagebus, workers
from scullery import iceflow, workers
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

from src import widgets,jackmanager

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

        try:
            self.client.deactivate()
        except:
            print(traceback.format_exc())

        try:
            self.client.close()
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

    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)
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


            import jack
            import struct

            # First 4 bits of status byte:
            NOTEON = 0x9
            NOTEOFF = 0x8

            INTERVALS = 3, 7  # minor triad

            self.client = jack.Client(self.name+"_in")
            inport = self.client.midi_inports.register("input")

            connectMidi=data.get("device.connectMidi", "").strip()

            self.midiAirwire = jackmanager.MonoAirwire(connectMidi, self.name+"_in:input")
            self.midiAirwire.connect()

            self.widgets=[] 
            
            for i in range(16):
                x=widgets.Button()
                x.attach(self.makeWidgetHandler(i))
                self.widgets.append(x)
                
            
            def noteOn(c,p,v):
                def f():
                    with self.synthLock:
                        self.synth.noteOn(c,p,v)
                workers.do(f)

            def noteOff(c,p):
                def f():
                    with self.synthLock:
                        self.synth.noteOff(c,p)
                workers.do(f)

            def cc(c,p,v):
                def f():
                    with self.synthLock:
                        self.synth.cc(c,p,v)
                workers.do(f)

            def bend(c,v):
                def f():
                    with self.synthLock:
                        self.synth.pitchBend(c,v)
                workers.do(f)

            def pgc(c,v):
                def f():
                    with self.synthLock:
                        self.synth.programChange(c,v)
                workers.do(f)


            @self.client.set_process_callback
            def process(frames):
                try:
                    for offset, indata in inport.incoming_midi_events():
                        # Note: This may raise an exception:
                        if len(indata) == 3:
                            status, pitch, vel = struct.unpack('3B', indata)

                            channel = status & 0b1111
                            if status >> 4 ==NOTEON:
                                noteOn(channel,pitch,vel)
                            elif status >> 4 ==NOTEOFF:
                                noteOff(channel,pitch)
                            elif status >> 4 ==0b1011:
                                cc(channel,pitch,vel)

                            elif status >> 4 ==0b1110:
                                bend(channel,struct.unpack("<h",indata[1:])[0] )

                        if len(indata) == 2:
                            status, rg = struct.unpack('2B', indata)
                            if status >> 4 == 0b1100:
                                pgc(channel,prg)
                       
                except:
                    self.handleException()

                            
            self.client.activate()
        except:
            self.handleException()

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["JackFluidSynth"] = JackFluidSynth