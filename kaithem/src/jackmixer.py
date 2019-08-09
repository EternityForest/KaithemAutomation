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

import re, jack,time

from . import widgets, messagebus
from . import jackmanager, gstwrapper

global_api =widgets.APIWidget()
global_api.require("/users/mixer.edit")

#Configured list of mixer channel strips
channels = {}

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


effectTemplates={
    "fader":{"type":"fader", "displayType": "Fader", "help": "The main fader for the channel",
    "params": []
    },
    "3beq":{"type":"fader", "displayType":"3 Band EQ","help": "Basic builtin EQ",
        "params": {
            "high": {
                "type":"float",
                "displayName": "High",
                "value": 0,
                "min": -12,
                "max": 12,
                "sort":0
            }
        }
    }
}

class MixingBoard():
    def __init__(self, *args, **kwargs):
        self.api =widgets.APIWidget()
        self.api.require("/users/mixer.edit")
        self.api.attach(self.f)
        self.channels = {}
        self.channelObjects ={}


    def sendPorts(self):
        inPorts = jackmanager.getPorts(is_audio=True, is_input=True)
        outPorts = jackmanager.getPorts(is_audio=True, is_output=True)

        self.api.send(['inports',{i.name:{} for i in  inPorts}])
        self.api.send(['outports',{i.name:{} for i in  outPorts}])
        self.api.send(['channels', self.channels])

    def createChannel(self, name,data):
        # import time
        op = data['output'].split(",")


        if name in self.channelObjects:
            self.channelObjects[name].stop()
        time.sleep(0.01)
        time.sleep(0.01)
        time.sleep(0.01)
        time.sleep(0.01)
        time.sleep(0.01)

        p = gstwrapper.Pipeline(name, outputs=op, input=data['input'])
        p.effectsList = []
        p.fader=None

        for i in data['effects']:
            if i['type']=="fader":
                p.fader= p.addElement("volume")
        p.finalize()
        p.connect()
        self.channelObjects[name]=p

    def deleteChannel(self,name):
        if name in self.channels:
            del self.channels[name]
        if name in self.channelObjects:
            self.channelObjects[name].stop()
            del self.channelObjects[name]



    def f(self,user, data):
        if data[0]== 'refresh':
            self.sendPorts()
        if data[0]=='addChannel':
            #No overwrite
            if data[1] in self.channels:
                return
            #No empty names
            if not data[1]:
                return
            self.channels[data[1]] = {"effects":[effectTemplates['fader']], "input": '', 'output': '', "fader":-60}
            self.api.send(['channels', self.channels])
            self.createChannel(data[1], self.channels[data[1]])

        if data[0]=='setEffects':
            "Directly set the effects data of a channel"
            self.channels[data[1]]['effects']= data[2]
            self.api.send(['channels', self.channels])
            self.createChannel(data[1], self.channels[data[1]])


        if data[0]== 'setInput':
            self.channels[data[1]]['input']= data[2]
            self.channelObjects[data[1]].setInput(data[2])
        if data[0]== 'setOutput':
            self.channels[data[1]]['output']= data[2]
            self.channelObjects[data[1]].setOutputs(data[2].split(","))


        if data[0]=='setFader':
            "Directly set the effects data of a channel"
            self.channels[data[1]]['fader']= float(data[2])
            self.api.send(['fader', data[1], data[2]])
            if data[2]>-80:
                self.channelObjects[data[1]].fader.set_property('volume', 10**(float(data[2])/20))
            else:
                self.channelObjects[data[1]].fader.set_property('volume', 0)

        if data[0]=='setParam':
            "Directly set the effects data of a channel. Params and effects don't have names"
            self.channels[data[1]]['effects'][data[2]]['params'][data[3]]['value'] = data[4]
            self.api.send(['param', data[1],data[2], data[3], data[4]])


        if data[0]=='addEffect':
            self.channels[data[1]]['effects'].append(effectTemplates[data[2]])
            self.api.send(['channels', self.channels])
            self.createChannel(data[1], self.channels[data[1]])

        if data[0]=='rmChannel':
            del self.channels[data[1]]
            self.api.send(['channels', self.channels])
            self.deleteChannel(data[1])

board = MixingBoard()