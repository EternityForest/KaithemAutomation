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

import re, jack,time,json,logging

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

#These are templates for effect data. Note that they contain everything needed to generate and interface for
#And use a gstreamer element. Except fader, which is special cased.
effectTemplates={
    "fader":{"type":"fader", "displayType": "Fader", "help": "The main fader for the channel",
    "params": {}
    },

    "voicedsp":{
        "type":"voicedsp", 
        "displayType":"Voice DSP",
        "help": "Noise Removal, AGC, and AEC", 
        "gstelement": "webrtcdsp",
        
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
            {"gstelement": "queue", "gstSetup":{"min-threshold-time": 25*1000*000}},
            {"gstelement": "audioconvert", "gstSetup":{}},
            {"gstelement": "interleave", "gstSetup":{}}

        ],
        "postSupportElements":[
            {"gstelement": "audioconvert", "gstSetup":{}}
        ]
    },

    "voicedsprobe":{"type":"voicedsprobe", "displayType":"Voice DSP Probe","help": "When using voice DSP, you must have one of these right before the main output.", "gstelement": "webrtcechoprobe",
    "params":{}, "gstSetup":{},
     "preSupportElements":[
        {"gstelement": "audioconvert", "gstSetup":{}},
        {"gstelement": "interleave", "gstSetup":{}}

        ],
    "postSupportElements":[
        {"gstelement": "audioconvert", "gstSetup":{}}
    ]
    },

    "3beq":{"type":"3beq", "displayType":"3 Band EQ","help": "Basic builtin EQ", "gstelement": "equalizer-nbands",
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
    }
}


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

channelTemplate = {"effects":[effectTemplates['fader']], "input": '', 'output': '', "fader":-60}

specialCaseParamCallbacks={}

def beq3(e, p, v):
    if p =="band2::freq":
        e.set_property("band2::bandwidth", v*0.3)

specialCaseParamCallbacks['3beq']= beq3




import uuid
class ChannelStrip(gstwrapper.Pipeline):

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
                        self.addElement(j['gstelement'],**j['gstSetup'])

                self.effectsById[i['id']] = self.addElement(i['gstelement'],**i['gstSetup'])
                self.effectDataById[i['id']]= i
                
                if "postSupportElements" in i:
                    for j in i['postSupportElements']:
                        self.addElement(j['gstelement'],**j['gstSetup'])
               
                for j in i['params']:
                    self.setProperty(self.effectsById[i['id']],j, i['params'][j]['value'])

        self.setFader(d["fader"])
        self.setInput(d['input'])
        self.setOutputs(d['output'].split(","))

    def setEffectParam(self,effectId,param,value):
        with self.lock:
            paramData = self.effectDataById[effectId]['params'][param]
            paramData['value']=value
            self.setProperty(self.effectsById[effectId], param, value)
            t = self.effectDataById[effectId]['type']
            if t in specialCaseParamCallbacks:
                specialCaseParamCallbacks[t](self.effectsById[effectId], param, value)
    
    def addLevelDetector(self):
        self.addElement("level", message=True, peak_ttl=3*1000*1000*1000)

    def on_message(self, bus, message):
        if  message.structure.get_name() == 'level':
            s = message.structure
            if self.board:
                l = [i for i in s['decay']]
                if l==self.lastLevel:
                    if time.monotonic()-self.lastPushedLevel< 1:
                        return
                self.lastPushedLevel = time.monotonic()
                self.lastLevel = l
                self.board.pushLevel(self.name, l)

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
        def f(t,v):
            self.reload()
        messagebus.subscribe("/system/jack/started", f)
        self.reloader = f
    def loadData(self,d):
        with self.lock:
            self._loadData(d)
    
    def reload(self):
        print("999999999999999999999999999999999999999999999999")
        self.loadData(self.channels)

    def _loadData(self,x):
        #Raise an error if it can't be serialized
        json.dumps(x)
        if not isinstance(x,dict):
            raise TypeError("Data must be a dict")

        self.channels=x
        for i in self.channels:
            log.info("Creating mixer channel "+i)
            try:
                self._createChannel(i,self.channels[i])
            except:
                log.exception("Could not create channel "+i)
    def sendState(self):
        with self.lock:
            inPorts = jackmanager.getPorts(is_audio=True, is_input=True)
            outPorts = jackmanager.getPorts(is_audio=True, is_output=True)

            self.api.send(['inports',{i.name:{} for i in  inPorts}])
            self.api.send(['outports',{i.name:{} for i in  outPorts}])
            self.api.send(['channels', self.channels])
            self.api.send(['effectTypes', effectTemplates])
            self.api.send(['presets',registry.ls("/system.mixer/presets/")])

    def createChannel(self, name, data={}):
        with self.lock:
            self._createChannel(name,data)

    def _createChannel(self, name,data=channelTemplate):
        backup = []
        if name in self.channelObjects:
            backup =self.channelObjects[name].backup()
            self.channelObjects[name].stop()

        self.channels[name]=data
        time.sleep(0.01)
        time.sleep(0.01)
        time.sleep(0.01)
        time.sleep(0.01)
        time.sleep(0.01)

        p = ChannelStrip(name,board=self)
        p.fader=None
        p.loadData(data)
        p.addLevelDetector()
        p.finalize()
        p.connect(restore=backup)
        self.channelObjects[name]=p
        self.api.send(['channels', self.channels])


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
        with self.lock:
            self.channels[channel]['fader']= float(level)
            self.api.send(['fader', channel, level])
            c = self.channelObjects[channel]
            c.setFader(level)
            

    def savePreset(self, presetName):
        with self.lock:
            util.disallowSpecialChars(presetName)
            registry.set("/system.mixer/presets/"+presetName, self.channels)

    def deletePreset(self,presetName):
        registry.delete("/system.mixer/presets/"+presetName)

    def loadPreset(self, presetName):
        with self.lock:
            x = list(self.channels)
            for i in x:
                self._deleteChannel(i)
            self._loadData(registry.get("/system.mixer/presets/"+presetName))

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
            self.createChannel(data[1], channelTemplate)

        if data[0]=='setEffects':
            "Directly set the effects data of a channel"
            with self.lock:
                self.channels[data[1]]['effects']= data[2]
                self.api.send(['channels', self.channels])
                self._createChannel(data[1], self.channels[data[1]])


        if data[0]== 'setInput':
            self.channels[data[1]]['input']= data[2]
            self.channelObjects[data[1]].setInput(data[2])

        if data[0]== 'setOutput':
            self.channels[data[1]]['output']= data[2]
            self.channelObjects[data[1]].setOutputs(data[2].split(","))


        if data[0]=='setFader':
            "Directly set the effects data of a channel"
            self.setFader(data[1], data[2])

        if data[0]=='setParam':
            "Directly set the effects data of a channel. Packet is channel, effectID, paramname, val"
            self.channelObjects[data[1]].setEffectParam(data[2],data[3],data[4])
            self.api.send(['param', data[1],data[2], data[3], data[4]])


        if data[0]=='addEffect':
            with self.lock:
                self.channels[data[1]]['effects'].append(effectTemplates[data[2]])
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