#Copyright Daniel Dunn 2013,2017
#This file is part of Kaithem Automation.

#Kaithem Automation is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#Kaithem Automation is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

import re, jack,time,json,logging,copy, subprocess

from . import widgets, messagebus,util,registry
from . import jackmanager, gstwrapper

import threading

global_api =widgets.APIWidget()
global_api.require("/users/mixer.edit")

#Configured list of mixer channel strips
channels = {}

log =logging.getLogger("system.mixer")


def replaceClientNameForDisplay(i):
    x = i.split(':')[0]
    if x in jackmanager.portJackNames:
        return i.replace(x,jackmanager.portJackNames[x])
    
    return i

def onPortAdd(t,m):
    #m[1] is true of input
    global_api.send(['newport', m[0],{},m[1]])  

def onPortRemove(t,m):
    #m[1] is true of input
    global_api.send(['rmport', m[0]])

messagebus.subscribe("/system/jack/newport/", onPortAdd)
messagebus.subscribe("/system/jack/rmport/", onPortRemove)



def logReport():
    if not util.which("jackd"):
        log.error("Jackd not found. Mixing will not work")
    if not util.which("a2jmidid"):
        log.error("A2jmidid not found, MIDI may not work")
    if not util.which("fluidsynth"):
        log.error("Fluidsynth not found. MIDI playing will not work,")
    try:
        if not gstwrapper.doesElementExist("tee"):
            log.error("Gstreamer or python bindings not installed properly. Mixing will not work")
    except:
        log.exception("Gstreamer or python bindings not installed properly. Mixing will not work")
    if not gstwrapper.doesElementExist("jackaudiosrc"):
         log.error("Gstreamer JACK plugin not found. Mixing will not work")

    for i in effectTemplates:
        e = effectTemplates[i]
        if 'gstElement' in e:
            if not gstwrapper.doesElementExist(e['gstElement']):
                log.warning("GST element "+e['gstElement']+" not found. Some effects in the mixer will not work.")
        if 'gstMonoElement' in e:
            if not gstwrapper.doesElementExist(e['gstMonoElement']):
                log.warning("GST element "+e['gstMonoElement']+" not found. Some effects in the mixer will not work.")  
        if 'gstStereoElement' in e:
            if not gstwrapper.doesElementExist(e['gstStereoElement']):
                log.warning("GST element "+e['gstStereoElement']+" not found. Some effects in the mixer will not work.")

#These are templates for effect data. Note that they contain everything needed to generate and interface for
#And use a gstreamer element. Except fader, which is special cased.
effectTemplates_data={
    "fader":{"type":"fader", "displayType": "Fader", "help": "The main fader for the channel",
    "params": {}
    },

    "voicedsp":{
        "type":"voicedsp", 
        "displayType":"Voice DSP",
        "help": "Noise Removal, AGC, and AEC", 
        "gstElement": "webrtcdsp",
        
        "params": {
          "gain-control": {
                "type":"bool",
                "displayName": "AGC",
                "value": False,
                "sort":0
            },
          "echo-cancel": {
                "type":"bool",
                "displayName": "Feedback Cancel",
                "value": True,
                "sort":1
            },
           "noise-suppression":
           {
                "type":"bool",
                "displayName": "Noise Suppression",
                "value": True,
                "sort":1          
            }

        },
        "gstSetup":{
            "high-pass-filter": False,
            "delay-agnostic": True,
            'noise-suppression-level': 0
        },
        "preSupportElements":[
            {"gstElement": "queue", "gstSetup":{"min-threshold-time": 25*1000*000}},
            {"gstElement": "audioconvert", "gstSetup":{}},
            {"gstElement": "interleave", "gstSetup":{}}

        ],
        "postSupportElements":[
            {"gstElement": "audioconvert", "gstSetup":{}}
        ]
    },

    "voicedsprobe":{"type":"voicedsprobe", "displayType":"Voice DSP Probe","help": "When using voice DSP, you must have one of these right before the main output.", "gstElement": "webrtcechoprobe",
    "params":{}, "gstSetup":{},
     "preSupportElements":[
        {"gstElement": "audioconvert", "gstSetup":{}},
        {"gstElement": "interleave", "gstSetup":{}}

        ],
    "postSupportElements":[
        {"gstElement": "audioconvert", "gstSetup":{}}
    ]
    },

    "3beq":{"type":"3beq", "displayType":"3 Band EQ","help": "Basic builtin EQ", "gstElement": "equalizer-nbands",
        "params": {
          "0:gain": {
                "type":"float",
                "displayName": "Low",
                "value": 0,
                "min": -12,
                "max": 12,
                "sort":3
            },
            "1:gain": {
                "type":"float",
                "displayName": "Mid",
                "value": 0,
                "min": -12,
                "max": 12,
                "sort":2
            },

            "1:freq": {
                "type":"float",
                "displayName": "MidFreq",
                "value": 0,
                "min": 200,
                "max": 8000,
                "sort":1
            },
          
            "2:gain": {
                "type":"float",
                "displayName": "High",
                "value": 0,
                "min": -12,
                "max": 12,
                "sort":0
            }
        },
        "gstSetup":
        {
            "num-bands":3,
            "band1::freq": 180,
            "band2::freq": 2000,
            "band3::freq": 12000,
            "band1::bandwidth": 360,
            "band2::bandwidth": 3600,
            "band3::bandwidth": 19000,
        }
    },
    "plateReverb":
    {
        "displayType":"Plate Reverb",
        "type": "plateReverb",
        "monoGstElement": "ladspa-caps-so-plate",
        "stereoGstElement": "ladspa-caps-so-plate",
        'help': "Basic plate reverb. From the CAPS plugins.",
        "params": {
          "blend": {
                "type":"float",
                "displayName": "Mix",
                "value": 0.25,
                "min": 0,
                "max": 1,
                "step":0.01,
                "sort":0
            },

            "bandwidth": {
                "type":"float",
                "displayName": "Bandwidth",
                "value": 0.5,
                "min": 0,
                "max": 1,
                "step":0.01,
                "sort":1
            },

            "tail": {
                "type":"float",
                "displayName": "Tail",
                "value": 0.75,
                "min": 0,
                "max": 1,
                "step":0.01,
                "sort":2
            },
            "damping": {
                "type":"float",
                "displayName": "Damping",
                "value": 0.5,
                "min": 0,
                "max": 1,
                "step":0.01,
                "sort":3
            }

            },
    "gstSetup":
            {},
        #It's stereo out, we may need to mono-ify it.
        "postSupportElements":[
            {"gstElement": "audioconvert", "gstSetup":{}}
        ]
    },

    "sc1Compressor":
    {
        "type": "sc1Compressor",
        "displayType":"SC1 Compressor",
        "help": "Steve Harris SC1 compressor",
        "monoGstElement": "ladspa-sc1-1425-so-sc1",
        "params": {

            "threshold-level": {
                "type":"float",
                "displayName": "Threshold",
                "value": -12,
                "min": -30,
                "max": 0,
                "step":0.01,
                "sort":0
            },
          "attack-time": {
                "type":"float",
                "displayName": "Attack",
                "value": 100,
                "min": 1,
                "max": 400,
                "step":0.01,
                "sort":1
            },

            "release-time": {
                "type":"float",
                "displayName": "Release",
                "value":200,
                "min": 0,
                "max": 800,
                "step":0.01,
                "sort":2
            },

            
            "ratio": {
                "type":"float",
                "displayName": "Ratio",
                "value": 2.5,
                "min": 0,
                "max": 10,
                "step":0.1,
                "sort":3
            },
            "knee-radius": {
                "type":"float",
                "displayName": "Knee",
                "value": 8,
                "min": 0,
                "max": 10,
                "step":0.1,
                "sort":4
            },
            "makeup-gain": {
                "type":"float",
                "displayName": "Gain",
                "value": 8,
                "min": 0,
                "max": 24,
                "step":0.1,
                "sort":5
            }

            },
      "gstSetup":
            {},
    },
    "echo":
    {
        "type": "echo",
        "gstElement":"audioecho",
        "help":"Simple echo",
        "displayType":"echo",
        "params": {

            "delay": {
                "type":"float",
                "displayName": "Delay",
                "value": 250,
                "min": 10,
                "max": 2500,
                "step":10,
                "sort":0
            },
          "intensity": {
                "type":"float",
                "displayName": "Mix",
                "value": 0.5,
                "min": 0,
                "max": 1,
                "step":0.01,
                "sort":1
            },
         "feedback": {
                "type":"float",
                "displayName": "feedback",
                "value": 0,
                "min": 0,
                "max": 1,
                "step":0.01,
                "sort":2
            },
        },
        'gstSetup':{
            "max-delay":3000*1000*1000
        }
    },

    "pitchshift":
    {
        "type": "pitchshift",
        "monoGstElement":"ladspa-tap-pitch-so-tap-pitch",
        "help":"Pitch shift(TAP LADSPA)",
        "displayType":"TAP Pitch Shifter",
        "params": {
            "semitone-shift": {
                "type":"float",
                "displayName": "Shift",
                "value": 0,
                "min": -12,
                "max": 12,
                "step":1,
                "sort":0
            },
          "dry-level": {
                "type":"float",
                "displayName": "Dry",
                "value": -90,
                "min": -90,
                "max": 20,
                "step":1,
                "sort":1
            },
         "wet-level": {
                "type":"float",
                "displayName": "Wet",
                "value": 0,
                "min": -90,
                "max": 20,
                "step":1,
                "sort":2
            },
        },
        'gstSetup':{
        }
    },

    "hqpitchshift":
    {
        "type": "hqpitchshift",
        "monoGstElement":"ladspa-pitch-scale-1194-so-pitchscalehq",
        "help":"Pitch shift(Steve Harris/swh-plugins)",
        "displayType":"FFT Pitch Shifter",
        "params": {
            "pitch-co-efficient": {
                "type":"float",
                "displayName": "Scale",
                "value": 0,
                "min": -2,
                "max": 2,
                "step":0.01,
                "sort":0
            },
        },
        'gstSetup':{
        }
    },

    "multichorus":
    {
        "type": "multichorus",
        "monoGstElement":"ladspa-multivoice-chorus-1201-so-multivoicechorus",
        "help":"Multivoice Chorus 1201 (Steve Harris/swh-plugins)",
        "displayType":"Multivoice Chorus",
        "params": {
            "number-of-voices": {
                "type":"float",
                "displayName": "Voices",
                "value": 1,
                "min": 1,
                "max": 8,
                "step":1,
                "sort":0
            },
 
            "delay-base": {
                "type":"float",
                "displayName": "Delay",
                "value": 10,
                "min": 10,
                "max": 40,
                "step":1,
                "sort":2
            },
            "voice-separation": {
                "type":"float",
                "displayName": "Separation",
                "value": 0.5,
                "min": 0,
                "max": 2,
                "step":0.1,
                "sort":3
            },

            "detune": {
                "type":"float",
                "displayName": "Detune",
                "value": 1,
                "min": 0,
                "max": 5,
                "step":1,
                "sort":4
            },
            "output-attenuation": {
                "type":"float",
                "displayName": "Level",
                "value": 1,
                "min": -20,
                "max": 0,
                "step":1,
                "sort":5
            },
        },
        'gstSetup':{
        }
    },

   "queue":
    {
        "type": "queue",
        "gstElement":"queue",
        "help":"Queue that enables multicore if placed before heavy effects.",
        "displayType":"queue",
        "params": {

            "min-threshold-time": {
                "type":"float",
                "displayName": "Delay",
                "value": 250,
                "min": 10,
                "max": 2500,
                "step":10,
                "sort":0
            },

        },
        'gstSetup':{
            "max-size-time": 5*1000*1000*1000,
            "leaky":2
        }
    }

}

effectTemplates = effectTemplates_data
def cleanupEffectData(fx):
    x= effectTemplates.get(fx['type'],{})
    for i in x:
        if not i in fx:
            fx[i]==x[i]

    if not 'help' in fx:
        fx['help'] = ''
    if not 'displayName' in fx:
        fx['displayName'] = fx['type']
    if not 'gstSetup' in fx:
        fx['gstSetup'] = {}

channelTemplate = {"type":"audio","effects":[effectTemplates['fader']], "input": '', 'output': '', "fader":-60}

specialCaseParamCallbacks={}




#Returning true enables the default param setting action
def beq3(e, p, v):
    if p =="band2::freq":
        e.set_property("band2::bandwidth", v*0.3)
    return True

def echo(e, p, v):
    if p =="delay":
        e.set_property("delay", v*1000000)
        return False
    return True

def queue(e, p, v):
    if p =="min-threshold-time":
        e.set_property("min-threshold-time", v*1000000)
        #Set to something short to clear the already buffered crap through leakage
        e.set_property("max-size-time", v*1000000 )
        #We should be able to depend on JACK not to let us get horribly out of sync,
        #The read rate should be exactly the write rate, so we give
        #As much buffer as you can before delay sounds worse than dropouts.
        e.set_property("max-size-time", v*1000000 + 50*1000*1000)

        return False
    return True

specialCaseParamCallbacks['3beq']= beq3
specialCaseParamCallbacks['echo']= echo
specialCaseParamCallbacks['queue']= queue



class BaseChannel():
    pass
class MidiConnection(BaseChannel):
    "Represents one MIDI connection with a single plugin that remaps all channels to one"
    def __init__(self, board, input, output,mapToChannel=0):
        self.map = mapToChannel

        if not mapToChannel:
            self.airwire = jackmanager.MonoAirwire(input, output)


    def start(self):
        if self.map:
            self.process = subprocess.Popen(["jalv"], stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL)
            self.input.connect()
            self.output.connect()
        else:
            self.aiirwire.connect()


    def close(self):
        try:
            self.process.kill()
        except:
            pass

    def __del__(self):
        self.close()
    



class FluidSynthChannel(BaseChannel):
    "Represents one MIDI connection with a single plugin that remaps all channels to one"
    def __init__(self, board,name, input, output,mapToChannel=0):
        self.name=name

        self.input = jackmanager.MonoAirwire(input,self.name+"-midi:*")
        self.output = jackmanager.airwire(self.name, output)


    def start(self):
        if self.map:
            self.process = subprocess.Popen(["fluidsynth", 
            '-a','jack','-m','jack', "-c","0","-r","0",
            "-o","audio.jack.id",self.name,
            "-o","audio.jack.multi","True",
            "-o","midi.jack.id",self.name+"-midi",
            ],
            
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL)
            self.input.connect()
            self.output.connect()
        else:
            self.aiirwire.connect()



import uuid
class ChannelStrip(gstwrapper.Pipeline,BaseChannel):

    def __init__(self, *a,board=None, **k):
        gstwrapper.Pipeline.__init__(self,*a,**k)
        self.board =board
        self.lastLevel = None
        self.lastPushedLevel = time.monotonic()
        self.effectsById = {}
        self.effectDataById = {}
        self.faderLevel = -60

    def loadData(self,d):
        for i in d['effects']:
            if not "id" in i or not i['id']:
                i['id']=str(uuid.uuid4())
            if i['type']=="fader":
                self.fader= self.addElement("volume")
                self.fader.set_property('volume', 0)
            else:
                if "preSupportElements" in i:
                    for j in i['preSupportElements']:
                        self.addElement(j['gstElement'],**j['gstSetup'])

                #Prioritize specific mono or stereo version of elements
                if self.channels == 1 and 'monoGstElement' in i:
                    self.effectsById[i['id']] = self.addElement(i['monoGstElement'],**i['gstSetup'])
                elif self.channels == 2 and 'stereoGstElement' in i:
                    self.effectsById[i['id']] = self.addElement(i['stereoGstElement'],**i['gstSetup'])
                else:
                    self.effectsById[i['id']] = self.addElement(i['gstElement'],**i['gstSetup'])


                self.effectDataById[i['id']]= i
                
                if "postSupportElements" in i:
                    for j in i['postSupportElements']:
                        self.addElement(j['gstElement'],**j['gstSetup'])
               
                for j in i['params']:
                    if i['type'] in specialCaseParamCallbacks:
                        x=specialCaseParamCallbacks[i['type']]
                        if x(self.effectsById[i['id']], j, i['params'][j]['value'] ):
                            self.setProperty(self.effectsById[i['id']],j, i['params'][j]['value'])
                    else:
                        self.setProperty(self.effectsById[i['id']],j, i['params'][j]['value'])


        self.setFader(d["fader"])
        self.setInput(d['input'])
        self.setOutputs(d['output'].split(","))

    def setEffectParam(self,effectId,param,value):
        with self.lock:
            paramData = self.effectDataById[effectId]['params'][param]
            paramData['value']=value
            t = self.effectDataById[effectId]['type']
            if t in specialCaseParamCallbacks:
                if specialCaseParamCallbacks[t](self.effectsById[effectId], param, value):
                    self.setProperty(self.effectsById[effectId], param, value)
            else:
                self.setProperty(self.effectsById[effectId], param, value)

    
    def addLevelDetector(self):
        self.addElement("level", post_messages=True, peak_ttl=300*1000*1000,peak_falloff=60)

    def on_message(self, bus, message):
        s = message.get_structure()
        if not s:
            return
        if  s.get_name() == 'level':
            if self.board:
                l = sum([i for i in s['decay']])/len(s['decay'])
                if l>-45:
                    if time.monotonic()-self.lastPushedLevel< 3:
                        return True
                else:
                    if time.monotonic()-self.lastPushedLevel< 0.2:
                        return True
                self.board.channels[self.name]['level']=l
                self.lastPushedLevel = time.monotonic()
                self.board.pushLevel(self.name, l)
        return True

    def setFader(self,level):
        if self.fader:
            if level>-60:
                self.fader.set_property('volume', 10**(float(level)/20))
            else:
                self.fader.set_property('volume', 0)
class ChannelInterface():
    def __init__(self, name,effectData={},mixingboard=None):
        if not mixingboard:
            mixingboard = board
        self.channel=board.createChannel(name, effectData)

    def fader(self):
        return self.board.getFader()
    def __del__(self):
        board.deleteChannel(self.name)
        
class MixingBoard():
    def __init__(self, *args, **kwargs):
        self.api =widgets.APIWidget()
        self.api.require("/users/mixer.edit")
        self.api.attach(self.f)
        self.channels = {}
        self.channelObjects ={}
        self.lock = threading.Lock()
        self.running=False
        def f(t,v):
            self.running=True
            self.reload()
        messagebus.subscribe("/system/jack/started", f)
        self.reloader = f
        self.loadedPreset = "default"


    def loadData(self,d):
        with self.lock:
            self._loadData(d)
    
    def reload(self):
        self.loadData(self.channels)

    def _loadData(self,x):
        #Raise an error if it can't be serialized
        json.dumps(x)
        if not isinstance(x,dict):
            raise TypeError("Data must be a dict")

        self.channels=x
        if not self.running:
            return
        for i in self.channels:
            log.info("Creating mixer channel "+i)
            try:
                self._createChannel(i,self.channels[i])
            except:
                log.exception("Could not create channel "+i)

       
    def sendState(self):
        with self.lock:
            inPorts = jackmanager.getPortNamesWithAliases(is_audio=True, is_input=True)
            outPorts = jackmanager.getPortNamesWithAliases(is_audio=True, is_output=True)
            midiOutPorts = jackmanager.getPortNamesWithAliases(is_midi=True, is_output=True)
            midiInPorts = jackmanager.getPortNamesWithAliases(is_midi=True, is_input=True)

            self.api.send(['inports',{i:{} for i in  inPorts}])
            self.api.send(['outports',{i:{} for i in  outPorts}])
            self.api.send(['midiinports',{i:{} for i in  midiInPorts}])
            self.api.send(['midioutports',{i:{} for i in  midiOutPorts}])

            self.api.send(['channels', self.channels])
            self.api.send(['effectTypes', effectTemplates])
            self.api.send(['presets',registry.ls("/system.mixer/presets/")])
            self.api.send(['loadedPreset', self.loadedPreset])


    def createChannel(self, name, data={}):
        with self.lock:
            self._createChannel(name,data)

    def _createChannel(self, name,data=channelTemplate):
        self.channels[name]=data
        self.api.send(['channels', self.channels])
        if not self.running:
            return
        if not 'type' in data or data['type']=="audio":
            backup = []
            if name in self.channelObjects:
                backup =self.channelObjects[name].backup()
                self.channelObjects[name].stop()


            time.sleep(0.01)
            time.sleep(0.01)
            time.sleep(0.01)
            time.sleep(0.01)
            time.sleep(0.01)

            p = ChannelStrip(name,board=self, channels=data.get('channels',2))
            self.channelObjects[name]=p
            p.fader=None
            p.loadData(data)
            p.addLevelDetector()
            p.finalize()
            p.connect(restore=backup)

        elif data['type']=="midiConnection":
            self.channels[name]=data
            if name in self.channelObjects:
                self.channelObjects[name].stop()
            self.channelObjects[name]=MidiConnection(self, data['input'], data['output'])

    def deleteChannel(self,name):
        with self.lock:
            self._deleteChannel(name)

    def _deleteChannel(self,name):
        if name in self.channels:
            del self.channels[name]
        if name in self.channelObjects:
            self.channelObjects[name].stop()
            del self.channelObjects[name]
        self.api.send(['channels', self.channels])

    def pushLevel(self,cn,d):
        self.api.send(['lv',cn,d])

    def setFader(self, channel,level):
        "Set the fader of a given channel to the given level"
        if not self.running:
            return
        with self.lock:
            self.channels[channel]['fader']= float(level)
            self.api.send(['fader', channel, level])
            c = self.channelObjects[channel]
            c.setFader(level)
            

    def savePreset(self, presetName):
        if not presetName:
            raise ValueError("Empty preset name")
        with self.lock:
            util.disallowSpecialChars(presetName)
            registry.set("/system.mixer/presets/"+presetName, self.channels)
            self.loadedPreset=presetName
            self.api.send(['loadedPreset', self.loadedPreset])

    def deletePreset(self,presetName):
        registry.delete("/system.mixer/presets/"+presetName)

    def loadPreset(self, presetName):
        with self.lock:
            x = list(self.channels)
            for i in x:
                self._deleteChannel(i)
            self._loadData(registry.get("/system.mixer/presets/"+presetName))
            self.loadedPreset=presetName
            self.api.send(['loadedPreset', self.loadedPreset])

    def f(self,user, data):
        if data[0]== 'refresh':
            self.sendState()

        if data[0]=='addChannel':
            #No overwrite
            if data[1] in self.channels:
                return
            #No empty names
            if not data[1]:
                return
            util.disallowSpecialChars(data[1])
            c = copy.deepcopy(channelTemplate)
            c['channels']=data[2]
            self.createChannel(data[1], c)

        if data[0]=='setEffects':
            "Directly set the effects data of a channel"
            with self.lock:
                self.channels[data[1]]['effects']= data[2]
                self.api.send(['channels', self.channels])
                self._createChannel(data[1], self.channels[data[1]])


        if data[0]== 'setInput':
            self.channels[data[1]]['input']= data[2]
            if not self.running:
                return
            self.channelObjects[data[1]].setInput(data[2])

        if data[0]== 'setOutput':
            self.channels[data[1]]['output']= data[2]

            if not self.running:
                return
            self.channelObjects[data[1]].setOutputs(data[2].split(","))


        if data[0]=='setFader':
            "Directly set the effects data of a channel"
            self.setFader(data[1], data[2])

        if data[0]=='setParam':
            "Directly set the effects data of a channel. Packet is channel, effectID, paramname, val"

            for i in self.channels[data[1]]['effects']:
                if i['id']==data[2]:
                    i['params'][data[3]]['value']=data[4]
            if not self.running:
                return
            self.channelObjects[data[1]].setEffectParam(data[2],data[3],data[4])
            self.api.send(['param', data[1],data[2], data[3], data[4]])


        if data[0]=='addEffect':
            with self.lock:
                fx = copy.deepcopy(effectTemplates[data[2]])
                fx['id']=str(uuid.uuid4())
                self.channels[data[1]]['effects'].append(fx)
                self.api.send(['channels', self.channels])
                self._createChannel(data[1], self.channels[data[1]])

        if data[0]=='rmChannel':
            self.deleteChannel(data[1])

        if data[0]=='savePreset':
            self.savePreset(data[1])
            self.api.send(['presets',registry.ls("/system.mixer/presets/")])

        if data[0]=='loadPreset':
            self.loadPreset(data[1])

        if data[0]=='deletePreset':
            self.deletePreset(data[1])
            self.api.send(['presets',registry.ls("/system.mixer/presets/")])

board = MixingBoard()
board.loadData(registry.get("/system.mixer/presets/default",{}))