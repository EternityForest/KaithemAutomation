from mako.lookup import TemplateLookup
from src import devices, alerts, scheduling, messagebus, workers
from scullery import workers
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

logger = logging.Logger("plugins.jackmidi")

templateGetter = TemplateLookup(os.path.dirname(__file__))


defaultSubclassCode = """
class CustomDeviceType(DeviceType):

    #These functions are called for the corresponding MIDI events

    def noteOn(self,channel, pitch, vel):
        print("Note On: CH# "+str(channel)+ " Pitch: "+ str(pitch)+" Vel: "+str(vel))

    def noteOff(self,channel, pitch ):
        print("Note On: CH# "+str(channel)+ " Pitch: "+ str(pitch))

    def cc(self,channel, cc,val ):
        print("Note On: CH# "+str(channel)+ " CC#: "+ str(cc)+" Val: "+str(val))

    def programChange(self,channel,prg):
        print("Note On: CH# "+str(channel)+ " Program: "+ str(prg))

    def pitchBend(self,channel,bend):
        print("Pitch Bend: CH# "+str(channel)+ " Bend: "+ str(bend))
"""


class JackMIDIListener(devices.Device):
    deviceTypeName = 'JackMIDIListener'
    readme = os.path.join(os.path.dirname(__file__), "README.md")
    defaultSubclassCode = defaultSubclassCode

    def close(self):
        devices.Device.close(self)

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
                        self.noteOn(c,60,64)
                else:
                    with self.synthLock:
                        self.noteOff(c,60)
        return f

    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)
        try:
            if len(name)==1:
                self.handleError('Single letter names may not work correctly')
            self.synthLock=threading.Lock()

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
            
 
            @self.client.set_process_callback
            def process(frames):
                try:
                    for offset, indata in inport.incoming_midi_events():
                        # Note: This may raise an exception:
                        if len(indata) == 3:
                            status, pitch, vel = struct.unpack('3B', indata)

                            channel = status & 0b1111
                            if status >> 4 ==NOTEON:
                                self.noteOn(channel,pitch,vel)
                            elif status >> 4 ==NOTEOFF:
                                self.noteOff(channel,pitch)
                            elif status >> 4 ==0b1011:
                                self.cc(channel,pitch,vel)

                            elif status >> 4 ==0b1110:
                                self.pitchBend(channel,struct.unpack("<h",indata[1:])[0] )

                        if len(indata) == 2:
                            status, rg = struct.unpack('2B', indata)
                            if status >> 4 == 0b1100:
                                self.programChange(channel,prg)
                       
                except:
                    self.handleException()

                            
            self.client.activate()
        except:
            self.handleException()

    def noteOn(self,channel, pitch, vel):
        pass

    def noteOff(self,channel, pitch ):
        pass

    def cc(self,channel, cc,val ):
        pass

    def programChange(self,channel,prg):
        pass

    def pitchBend(self,channel,bend):
        pass

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["JackMIDIListener"] = JackMIDIListener