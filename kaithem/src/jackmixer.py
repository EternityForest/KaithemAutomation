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
from . import jackmanager, gstwrapper,mixerfx

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

effectTemplates_data= mixerfx.effectTemplates_data
 
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

    def __init__(self, name,board=None,channels= 2, input=None, outputs=[]):
        gstwrapper.Pipeline.__init__(self,name)
        self.board =board
        self.lastLevel = 0
        self.lastPushedLevel = time.monotonic()
        self.effectsById = {}
        self.effectDataById = {}
        self.faderLevel = -60

        self.src=self.addElement("jackaudiosrc", buffer_time=10, latency_time=10, port_pattern="fgfcghfhftyrtw5ew453xvrt", client_name=name+"_in",connect=0) 
        self.capsfilter = self.addElement("capsfilter", caps="audio/x-raw,channels="+str(channels))
        self.channels = channels

        self.input=input
        self._input= None
        self.outputs=outputs
        self._outputs = []
        self.sends = []
        self.sendAirwires =[]
  

        self.usingJack=True





    def finalize(self):
        with self.lock:
            #self.addElement("audioconvert")
            #self.capsfilter2= self.addElement("capsfilter", caps="audio/x-raw,channels="+str(channels))

            self.sink=self.addElement("jackaudiosink", buffer_time=8000, latency_time=4000,sync=False,
                slave_method=2, port_pattern="fgfcghfhftyrtw5ew453xvrt", client_name=self.name+"_out",connect=0) 

            #I think It doesn't like it if you start without jack
            if self.usingJack:
                t=time.time()
                while(time.time()-t)<3:
                    if jackmanager.getPorts():
                        break
                if not jackmanager.getPorts():
                    return
        self.start()


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

    def stop(self):
        with self.lock:
            for i in self.sendAirwires:
                i.disconnect()
            if self._input:
                self._input.disconnect()
            for i in self._outputs:
                i.disconnect()
        gstwrapper.Pipeline.stop(self)


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

    def loadData(self,d):
        for i in d['effects']:
            if not "id" in i or not i['id']:
                i['id']=str(uuid.uuid4())
            if i['type']=="fader":
                self.fader= self.addElement("volume")
                self.fader.set_property('volume', 0)
            #Special case this, it's made of multiple gstreamer blocks and also airwires
            elif i['type']=="send":
                self.addSend(i['params']['target']['value'], i['id'], i['params']['level']['value'])

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

            #One type of special case
            if t[0]=='*':
                if t=="*destination":
                    #Keep the old origin, just swap the destination
                    if effectId in self.sendAirwires:
                        self.sendAirwires[effectId].disconnect()
                        self.sendAirwires[effectId] = jackmanager.Airwire(self.sendAirwires[effectId].orig, value)

            elif t in specialCaseParamCallbacks:
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
                if l<-45 or abs(l-self.lastLevel)<6:
                    if time.monotonic()-self.lastPushedLevel< 1:
                        return True
                else:
                    if time.monotonic()-self.lastPushedLevel< 0.07:
                        return True
                self.board.channels[self.name]['level']=l
                self.lastPushedLevel = time.monotonic()
                self.lastLevel = l
                self.board.pushLevel(self.name, l)
        return True

    def setFader(self,level):
        if self.fader:
            if level>-60:
                self.fader.set_property('volume', 10**(float(level)/20))
            else:
                self.fader.set_property('volume', 0)

    def addSend(self,target, id,volume=-60):
            with self.lock:
                if not isinstance(target, str):
                    raise ValueError("Targt must be string")

                e = self.makeElement("tee")

                l = self.makeElement('volume')
                self.effectsById[id] = l

                e2 =self.makeElement("jacksink")
                e2.set_property("buffer-time",8000)
                e2.set_property("port-pattern","fdgjkndgmkndfmfgkjkf")


                #Sequentially number the sends
                cname = self.name+"_send"+str(len(self.sends))
                e2.set_property("client-name",cname)
                self.sendAirwires[id] = jackmanager.Airwire(cname, target)
                self.sends.append(e2)


                self.elements[-1].link(e)
                self.elements.append(e)
                return e



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