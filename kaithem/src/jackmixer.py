# Copyright Daniel Dunn 2013,2017
# This file is part of Kaithem Automation.

# Kaithem Automation is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.

# Kaithem Automation is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

import uuid
import time
import json
import logging
import copy
import subprocess
import os

from . import widgets, messagebus, util, registry, tagpoints, persist, directories, alerts, workers, directories
from . import jackmanager, gstwrapper, mixerfx

import threading

global_api = widgets.APIWidget()
global_api.require("/users/mixer.edit")

# Configured list of mixer channel strips
channels = {}

log = logging.getLogger("system.mixer")

presetsDir = os.path.join(directories.vardir, "system.mixer", "presets")

settingsFile = os.path.join(
    directories.vardir, "system.mixer", "jacksettings.yaml")


recorder = None
settings = persist.getStateFile(settingsFile)

# Try to import a cython extension that only works on Linux
try:
    from . import threadpriority
    setPriority = threadpriority.setThreadPriority
except:
    log.exception(
        "Cython import failed, gstreamer realtime priority is disabled")

    def setPriority(p, po): return None

gstwrapper.Pipeline.setCurrentThreadPriority = setPriority


def replaceClientNameForDisplay(i):
    x = i.split(':')[0]
    if x in jackmanager.portJackNames:
        return i.replace(x, jackmanager.portJackNames[x])

    return i


def onPortAdd(t, m):
    # m[1] is true of input
    global_api.send(['newport', m.name, {}, m.isInput])


def onPortRemove(t, m):
    # m[1] is true of input
    global_api.send(['rmport', m.name])


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
            log.error(
                "Gstreamer or python bindings not installed properly. Mixing will not work")
    except:
        log.exception(
            "Gstreamer or python bindings not installed properly. Mixing will not work")
    if not gstwrapper.doesElementExist("jackaudiosrc"):
        log.error("Gstreamer JACK plugin not found. Mixing will not work")

    for i in effectTemplates:
        e = effectTemplates[i]
        if 'gstElement' in e:
            if not gstwrapper.doesElementExist(e['gstElement']):
                log.warning(
                    "GST element " + e['gstElement'] + " not found. Some effects in the mixer will not work.")
        if 'gstMonoElement' in e:
            if not gstwrapper.doesElementExist(e['gstMonoElement']):
                log.warning("GST element " + e['gstMonoElement'] +
                            " not found. Some effects in the mixer will not work.")
        if 'gstStereoElement' in e:
            if not gstwrapper.doesElementExist(e['gstStereoElement']):
                log.warning("GST element " + e['gstStereoElement'] +
                            " not found. Some effects in the mixer will not work.")


effectTemplates_data = mixerfx.effectTemplates_data

effectTemplates = effectTemplates_data


def cleanupEffectData(fx):
    x = effectTemplates.get(fx['type'], {})
    for i in x:
        if not i in fx:
            fx[i] == x[i]

    if not 'help' in fx:
        fx['help'] = ''
    if not 'displayName' in fx:
        fx['displayName'] = fx['type']
    if not 'gstSetup' in fx:
        fx['gstSetup'] = {}


channelTemplate = {"type": "audio", "effects": [
    effectTemplates['fader']], "input": '', 'output': '', "fader": -60, "soundFuse": 3}


specialCaseParamCallbacks = {}


# Returning true enables the default param setting action
def beq3(e, p, v):
    if p == "2:freq":
        e.set_property("2:bandwidth", v * 0.3)
    return True


def echo(e, p, v):
    if p == "delay":
        e.set_property("delay", v * 1000000)
        return False
    return True


def queue(e, p, v):
    if p == "min-threshold-time":
        e.set_property("min-threshold-time", v * 1000000)
        # Set to something short to clear the already buffered crap through leakage
        e.set_property("max-size-time", v * 1000000)
        # We should be able to depend on JACK not to let us get horribly out of sync,
        # The read rate should be exactly the write rate, so we give
        # As much buffer as you can before delay sounds worse than dropouts.
        e.set_property("max-size-time", v * 1000000 + 50 * 1000 * 1000)

        return False
    return True

# with open("/dev/shm/kaithem_kw_file",'w') as f:
#     f.write('hello /1e-30/\n')

# with open("/dev/shm/kaithem_dummy_kw_file",'w') as f:
#     f.write('hello /1e-30/\n')

# def tmpKwFile(e,p,v,c):
#     if p=='kws':
#


specialCaseParamCallbacks['3beq'] = beq3
specialCaseParamCallbacks['echo'] = echo
specialCaseParamCallbacks['queue'] = queue

# Returning true enables the default param setting action


def send(e, p, v):
    if v > -60:
        e.set_property('volume', 10**(float(v) / 20))
    else:
        e.set_property('volume', 0)


specialCaseParamCallbacks['send'] = send


class BaseChannel():
    pass


class MidiConnection(BaseChannel):
    "Represents one MIDI connection with a single plugin that remaps all channels to one"

    def __init__(self, board, input, output, mapToChannel=0):
        self.map = mapToChannel

        if not mapToChannel:
            self.airwire = jackmanager.MonoAirwire(input, output)

    def start(self):
        if self.map:
            self.process = subprocess.Popen(
                ["jalv"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
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

    def __init__(self, board, name, input, output, mapToChannel=0):
        self.name = name

        self.input = jackmanager.MonoAirwire(input, self.name + "-midi:*")
        self.output = jackmanager.airwire(self.name, output)

    def start(self):
        if self.map:
            self.process = subprocess.Popen(["fluidsynth",
                                             '-a', 'jack', '-m', 'jack', "-c", "0", "-r", "0",
                                             "-o", "audio.jack.id", self.name,
                                             "-o", "audio.jack.multi", "True",
                                             "-o", "midi.jack.id", self.name + "-midi",
                                             ],

                                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            self.input.connect()
            self.output.connect()
        else:
            self.aiirwire.connect()


class Recorder(gstwrapper.Pipeline):
    def __init__(self, name="krecorder", channels=2, pattern="mixer_"):
        gstwrapper.Pipeline.__init__(self, name, realtime=70)

        self.src = self.addElement("jackaudiosrc", buffer_time=10, latency_time=10,
                                   port_pattern="fgfcghfhftyrtw5ew453xvrt", client_name="krecorder", connect=0, slave_method=0)
        self.capsfilter = self.addElement(
            "capsfilter", caps="audio/x-raw,channels=" + str(channels))

        filename = os.path.join(directories.vardir, "recordings", "mixer",
                                pattern + time.strftime("%Y%b%d%a%H%M%S", time.localtime()) + ".ogg")

        if not os.path.exists(os.path.join(directories.vardir, "recordings", "mixer")):
            os.makedirs(os.path.join(
                directories.vardir, "recordings", "mixer"))

        self.addElement("queue")
        self.addElement("audioconvert")
        self.addElement("opusenc", bitrate=96000)

        self.addElement("oggmux")
        self.addElement("filesink", location=filename)


class ChannelStrip(gstwrapper.Pipeline, BaseChannel):

    def __init__(self, name, board=None, channels=2, input=None, outputs=[], soundFuse=3):
        gstwrapper.Pipeline.__init__(self, name, realtime=70)
        self.board = board
        self.levelTag = tagpoints.Tag("/jackmixer/channels/" + name + "/level")
        self.levelTag.min = -90
        self.levelTag.max = 3
        self.levelTag.hi = -3
        self.levelTag.unit = 'dB'

        # Set default
        self.levelTag.value = -90
        self.lastLevel = 0
        self.lastRMS = 0
        self.lastNormalVolumeLevel = time.monotonic()
        # Limit how often we can clear the alert
        self.alertRatelimitTime = time.monotonic() + 10
        self.soundFuseSetting = soundFuse
        self.lastPushedLevel = time.monotonic()
        self.effectsById = {}
        self.effectDataById = {}
        self.faderLevel = -60
        self.channels = channels

        # Are we already doing a loudness cutoff?
        self.doingFeedbackCutoff = False

        self.src = self.addElement("jackaudiosrc", buffer_time=10, latency_time=10,
                                   port_pattern="fgfcghfhftyrtw5ew453xvrt", client_name=name + "_in", connect=0, slave_method=0)
        self.capsfilter = self.addElement(
            "capsfilter", caps="audio/x-raw,channels=" + str(channels))

        self.input = input
        self._input = None
        self.outputs = outputs
        self._outputs = []
        self.sends = []
        self.sendAirwires = {}

        self.faderTag = tagpoints.Tag("/jackmixer/channels/" + name + "/fader")
        self.faderTag.subscribe(self._faderTagHandler)
        self.faderTag.max = 20
        self.faderTag.min = -60
        self.faderTag.lo = -59
        self.faderTag.hi = 3
        self.faderTag.unit = 'dB'

        self.effectParamTags = {}

        self.usingJack = True

        # General good practice to use this when creating a tag,
        # If we don't know who else may have assigned alerts.
        self.levelTag.clearDynamicAlarms()
        self.levelTag.setAlarm(
            "volume", "value>soundFuseSetting", tripDelay=0.3)

        #self.loudnessAlert = alerts.Alert(self.name+".abnormalvolume", priority='info')

    @property
    def soundFuseSetting(self):
        return self._soundFuseSetting

    @soundFuseSetting.setter
    def soundFuseSetting(self, v):
        self._soundFuseSetting = v
        self.levelTag.evalContext['soundFuseSetting'] = v

    def finalize(self):
        with self.lock:
            # self.addElement("audioconvert")
            #self.capsfilter2= self.addElement("capsfilter", caps="audio/x-raw,channels="+str(channels))

            self.addElement("audiorate")
            self.sink = self.addElement("jackaudiosink", buffer_time=10, latency_time=10, sync=False,
                                        slave_method=0, port_pattern="fgfcghfhftyrtw5ew453xvrt", client_name=self.name + "_out", connect=0, blocksize=self.channels * 128)

            # I think It doesn't like it if you start without jack
            if self.usingJack:
                t = time.time()
                while(time.time() - t) < 3:
                    if jackmanager.getPorts():
                        break
                if not jackmanager.getPorts():
                    return
        self.start()

    def connect(self, restore=[]):
        self._outputs = []
        for i in self.outputs:
            x = jackmanager.Airwire(
                self.name + "_out", i, forceCombining=(self.channels == 1))
            x.connect()
            self._outputs.append(x)

        self._input = jackmanager.Airwire(
            self.input, self.name + "_in", forceCombining=(self.channels == 1))
        self._input.connect()
        for i in restore:
            for j in i[1]:
                try:
                    jackmanager.connect(i[0], j)
                except:
                    pass
        for i in self.sendAirwires:
            try:
                self.sendAirwires[i].connect()
            except:
                pass

    def stop(self):
        with self.lock:
            for i in self.sendAirwires:
                self.sendAirwires[i].disconnect()
            if self._input:
                self._input.disconnect()
            for i in self._outputs:
                i.disconnect()
        gstwrapper.Pipeline.stop(self)

    def backup(self):
        c = []

        for i in jackmanager.getPorts(self.name + "_in:"):
            c.append((i, jackmanager.getConnections(i)))
        for i in jackmanager.getPorts(self.name + "_out:"):
            c.append((i, jackmanager.getConnections(i)))
        return c

    def setInput(self, input):
        with self.lock:
            self.input = input
            if self._input:
                self._input.disconnect()
            self._input = jackmanager.Airwire(
                self.input, self.name + "_in", forceCombining=(self.channels == 1))
            self._input.connect()

    def setOutputs(self, outputs):
        with self.lock:
            self.outputs = outputs
            for i in self._outputs:
                i.disconnect()

            self._outputs = []
            for i in self.outputs:
                x = jackmanager.Airwire(
                    self.name + "_out", i, forceCombining=(self.channels == 1))
                x.connect()
                self._outputs.append(x)

    def loadData(self, d):
        for i in d['effects']:
            if d.get('bypass', False):
                continue
            if not "id" in i or not i['id']:
                i['id'] = str(uuid.uuid4())
            if i['type'] == "fader":
                self.fader = self.addElement("volume")
                # We have to set it here and can't rely on the tagpoint, it only does anything on *changes*
                self.fader.set_property('volume', 10**(float(d['fader']) / 20))
            # Special case this, it's made of multiple gstreamer blocks and also airwires
            elif i['type'] == "send":
                self.addSend(i['params']['*destination']['value'],
                             i['id'], i['params']['volume']['value'])

            else:

                # Sidechain lets us split off a whole effect chain that does not
                # feed the main chain, such as fir the speech recognition effect
                if i.get('sidechain', 0):
                    linkTo = self.addElement("tee")
                    q = self.addElement("queue")
                    linkTo = self.addElement(
                        "queue", sidechain=True, connectToOutput=linkTo)
                    sidechain = True

                else:
                    # Default link to prev
                    linkTo = None
                    sidechain = False

                supports = []
                if "preSupportElements" in i:
                    for j in i['preSupportElements']:
                        linkTo = self.addElement(j['gstElement'], **j['gstSetup'], sidechain=sidechain,
                                                 connectToOutput=linkTo if (not j.get("noConnectInput", False)) else False)
                        supports.append(linkTo)

                # Prioritize specific mono or stereo version of elements
                if self.channels == 1 and 'monoGstElement' in i:
                    linkTo = self.effectsById[i['id']] = self.addElement(
                        i['monoGstElement'], **i['gstSetup'], sidechain=sidechain, connectToOutput=linkTo if (not i.get("noConnectInput", False)) else False)
                elif self.channels == 2 and 'stereoGstElement' in i:
                    linkTo = self.effectsById[i['id']] = self.addElement(
                        i['stereoGstElement'], **i['gstSetup'], sidechain=sidechain, connectToOutput=linkTo if (not i.get("noConnectInput", False)) else False)
                else:
                    linkTo = self.effectsById[i['id']] = self.addElement(
                        i['gstElement'], **i['gstSetup'], sidechain=sidechain, connectToOutput=linkTo if (not i.get("noConnectInput", False)) else False)

                elmt = linkTo
                linkTo.preSupports = supports

                self.effectDataById[i['id']] = i

                supports = []
                if "postSupportElements" in i:
                    for j in i['postSupportElements']:
                        linkTo = self.addElement(j['gstElement'], **j['gstSetup'], sidechain=sidechain,
                                                 connectToOutput=linkTo if (not j.get("noConnectInput", False)) else False)
                        supports.append(linkTo)
                elmt.postSupports = supports

                for j in i['params']:
                    if j == 'bypass':
                        continue
                    if i['type'] in specialCaseParamCallbacks:
                        x = specialCaseParamCallbacks[i['type']]
                        if x(self.effectsById[i['id']], j, i['params'][j]['value']):
                            self.setProperty(
                                self.effectsById[i['id']], j, i['params'][j]['value'])
                    else:
                        self.setEffectParam(
                            i['id'], j, i['params'][j]['value'])

                # Sidechain FX have a bug where they always cause an output to the system channel, we have to work around
                # That with a hack.  Basically sidechains only exist to let us to alternative outputs anyway.
                if i.get('silenceMainChain', False):
                    self.addElement('volume', volume=0)

        self.faderTag.value = d['fader']
        self.setFader(self.faderTag.value)

        self.setInput(d['input'])
        self.setOutputs(d['output'].split(","))

    def setEffectParam(self, effectId, param, value):
        "Set val after casting, and return properly typed val"
        with self.lock:

            paramData = self.effectDataById[effectId]['params'][param]
            paramData['value'] = value
            t = self.effectDataById[effectId]['type']

            if t == 'float':
                value = float(value)

            if t == 'bool':
                value = value > 0.5

            if t == 'enum':
                value = int(value)

            if t == 'int':
                value = int(value)
            if t == 'string.int':
                try:
                    value = int(value)
                except:
                    value = 0

            # One type of special case
            if param[0] == '*':
                if param == "*destination":
                    # Keep the old origin, just swap the destination
                    if effectId in self.sendAirwires:
                        self.sendAirwires[effectId].disconnect()
                        self.sendAirwires[effectId] = jackmanager.Airwire(
                            self.sendAirwires[effectId].orig, value, forceCombining=(self.channels == 1))
                        try:
                            self.sendAirwires[effectId].connect()
                        except:
                            pass
            elif param == "bypass":
                pass
            else:
                if t in specialCaseParamCallbacks:
                    r = specialCaseParamCallbacks[t](
                        self.effectsById[effectId], param, value)
                    if r:
                        if r == "pause":
                            self.pause()
                        self.setProperty(
                            self.effectsById[effectId], param, value)
                        if r == "pause":
                            self.play()

                else:
                    fx = self.effectsById[effectId]
                    if param.startswith("preSupport."):
                        v = param.split(".", 2)
                        fx = fx.preSupports[int(v[1])]
                        param = v[2]

                    if param.startswith("postSupport."):
                        v = param.split(".", 2)
                        fx = fx.postSupports[int(v[1])]
                        param = v[2]

                    self.setProperty(fx, param, value)
        return value

    def addLevelDetector(self):
        self.addElement("level", post_messages=True,
                        peak_ttl=300 * 1000 * 1000, peak_falloff=60)

    def on_message(self, bus, message, userdata):
        s = message.get_structure()
        if not s:
            return True
        msgtype = s.get_name()
        if msgtype == 'level':
            if self.board:
                l = sum([i for i in s['decay']]) / len(s['decay'])
                rms = sum([i for i in s['rms']]) / len(s['rms'])
                self.levelTag.value = max(rms, -90)
                self.doSoundFuse(rms)
                if l < -45 or abs(l - self.lastLevel) < 6:
                    if time.monotonic() - self.lastPushedLevel < 0.3:
                        return True
                else:
                    if time.monotonic() - self.lastPushedLevel < 0.07:
                        return True
                self.board.channels[self.name]['level'] = l
                self.lastPushedLevel = time.monotonic()
                self.lastLevel = l
                self.board.pushLevel(self.name, l)

        # Speech recognition, forward it on to the message bus.
        elif msgtype == 'pocketsphinx':
            if message.get_structure().get_value('hypothesis'):
                messagebus.postMessage("/system/mixer/channels/" + self.name + "/stt/hypothesis",
                                       (message.get_structure().get_value('hypothesis'),))

            if message.get_structure().get_value('final'):
                messagebus.postMessage("/system/mixer/channels/" + self.name + "/stt/final",
                                       (message.get_structure().get_value('hypothesis'), message.get_structure().get_value('confidence')))

        return True

    def doSoundFuse(self, rms):
        # Highly dynamic stuff is less likely to be feedback.
        # Don't count feedback if there's any decrease
        # Aside from very small decreases, there's likely other stuff happening too.
        # But if we are close to clipping ignore that
        if not (((self.lastRMS < (rms + 1.5)) or rms > -2) and rms > self.soundFuseSetting):
            self.lastNormalVolumeLevel = time.monotonic()
        self.lastRMS = rms
        if time.monotonic() - self.lastNormalVolumeLevel > 0.3:
            # self.loudnessAlert.trip()
            self.alertRatelimitTime = time.monotonic()

            if not self.doingFeedbackCutoff:
                self.doingFeedbackCutoff = True

                def f():
                    "Greatly reduce volume, then slowly increase it, till the user does something about it"
                    try:
                        print("FEEDBACK DETECTED!!!!")
                        l = self.faderTag.value
                        self.setFader(l - 8)
                        c = self.faderTag.value
                        time.sleep(0.25)
                        # Detect manual action
                        if not c == self.faderTag.value:
                            return
                        t = 8
                        # Go down till we find a non horrible level
                        for i in range(24):
                            if(self.levelTag.value > self.soundFuseSetting - 3):
                                self.setFader(l - (i + 8))
                                t = i + 8
                                c = self.faderTag.value
                                time.sleep(0.05)

                                # Detect manual action
                                if not c == self.faderTag.value:
                                    return

                        time.sleep(2.5)
                        # Detect manual action
                        if not c == self.faderTag.value:
                            return

                       # Slowly go back up

                        while t:
                            t -= 1
                            self.setFader(l - t)
                            c = self.faderTag.value

                            # Wait longer on that last one before we exit,
                            # To ensure it worked
                            if(t == 1):
                                time.sleep(1)
                            time.sleep(0.1)
                            # Detect manual action
                            if not c == self.faderTag.value:
                                return

                            if(self.levelTag.value > self.soundFuseSetting - 3):
                                t += 3
                                self.setFader(l - t)
                                c = self.faderTag.value

                                time.sleep(1)
                                # Detect manual action
                                if not c == self.faderTag.value:
                                    return

                        # Return to normal
                        self.setFader(l)
                    finally:
                        print("FEEDBACK HANDLER EXIT")
                        self.doingFeedbackCutoff = False
                workers.do(f)

        elif time.monotonic() - self.alertRatelimitTime > 10:
            # self.loudnessAlert.release()
            self.alertRatelimitTime = time.monotonic()

    def _faderTagHandler(self, level, t, a):
        # Note: We don't set the configured data fader level here.
        if self.fader:
            if level > -60:
                self.fader.set_property('volume', 10**(float(level) / 20))
            else:
                self.fader.set_property('volume', 0)

        self.board.api.send(['fader', self.name, level])

    def setFader(self, level):
        # Let the _faderTagHandler handle it.
        self.faderTag.value = level

    def addSend(self, target, id, volume=-60):
        with self.lock:
            if not isinstance(target, str):
                raise ValueError("Target must be string")

            e = self.makeElement("tee")
            q = self.makeElement("queue")
            q2 = self.makeElement("queue")
            q2.max_size_buffers = 1
            q.max_size_buffers = 1
            q.leaky = 2
            q2.leaky = 2
            l = self.makeElement('volume')
            l.set_property('volume', 10**(volume / 20))
            self.effectsById[id] = l

            e2 = self.makeElement(
                "jackaudiosink", "_send" + str(len(self.sends)))
            e2.set_property("buffer-time", 10)
            e2.set_property("port-pattern", "fdgjkndgmkndfmfgkjkf")
            e2.set_property("sync", False)
            e2.set_property("slave-method", 0)
            e2.set_property('provide-clock', False)
            e2.set_property('connect', False)

            e2.latency_time = 10
            self.effectsById[id] = l
            self.effectsById[id + "*destination"] = e2

            d = effectTemplates['send']
            d['params']['*destination']['value'] = target
            d['params']['volume']['value'] = volume
            self.effectDataById[id] = d

            # Sequentially number the sends
            cname = self.name + "_send" + str(len(self.sends))
            e2.set_property("client-name", cname)

            self.sendAirwires[id] = jackmanager.Airwire(
                cname, target, forceCombining=(self.channels == 1))
            self.sends.append(e2)

            tee_src_pad_template = e.get_pad_template("src_%u")
            tee_audio_pad = e.request_pad(tee_src_pad_template, None, None)
            tee_audio_pad2 = e.request_pad(tee_src_pad_template, None, None)

            if self.elements:
                gstwrapper.link(self.elements[-1], e)
            gstwrapper.link(tee_audio_pad, q)
            gstwrapper.link(tee_audio_pad2, q2)
            self.elements.append(q2)

            gstwrapper.link(q, l)
            gstwrapper.link(l, e2)

            return e


class ChannelInterface():
    def __init__(self, name, effectData={}, mixingboard=None):
        if not mixingboard:
            mixingboard = board
        self.channel = board.createChannel(name, effectData)

    def fader(self):
        return self.board.getFader()

    def __del__(self):
        board.deleteChannel(self.name)


class MixingBoard():
    def __init__(self, *args, **kwargs):
        self.api = widgets.APIWidget()
        self.api.require("/users/mixer.edit")
        self.api.attach(self.f)
        self.channels = {}
        self.channelObjects = {}
        self.lock = threading.RLock()
        self.running = False

        def f(t, v):
            self.running = True
            self.reload()
        messagebus.subscribe("/system/jack/started", f)
        self.reloader = f
        self.loadedPreset = "default"

    def loadData(self, d):
        with self.lock:
            self._loadData(d)

    def reload(self):
        self.loadData(self.channels)

    def _loadData(self, x):
        # Raise an error if it can't be serialized
        json.dumps(x)
        if not isinstance(x, dict):
            raise TypeError("Data must be a dict")

        self.channels = x
        if not self.running:
            return
        for i in self.channels:
            log.info("Creating mixer channel " + i)
            try:
                self._createChannel(i, self.channels[i])
            except:
                messagebus.postMessage(
                    "/system/notifications/errors", "Failed to create mixer channel " + i + " see logs.")
                log.exception("Could not create channel " + i)

    def sendState(self):
        with self.lock:
            inPorts = jackmanager.getPortNamesWithAliases(
                is_audio=True, is_input=True)
            outPorts = jackmanager.getPortNamesWithAliases(
                is_audio=True, is_output=True)
            midiOutPorts = jackmanager.getPortNamesWithAliases(
                is_midi=True, is_output=True)
            midiInPorts = jackmanager.getPortNamesWithAliases(
                is_midi=True, is_input=True)

            self.api.send(['inports', {i: {} for i in inPorts}])
            self.api.send(['outports', {i: {} for i in outPorts}])
            self.api.send(['midiinports', {i: {} for i in midiInPorts}])
            self.api.send(['midioutports', {i: {} for i in midiOutPorts}])

            self.api.send(['channels', self.channels])
            self.api.send(['effectTypes', effectTemplates])

            self.api.send(['loadedPreset', self.loadedPreset])
            self.api.send(['usbalsa', settings.data['usbPeriodSize'], settings.data['usbLatency'],
                           settings.data['usbQuality'], settings.data['usbPeriods']])
            self.sendPresets()

            if recorder:
                self.api.send(['recordingStatus', "recording"])
            else:
                self.api.send(['recordingStatus', "off"])

    def sendPresets(self):
        if os.path.isdir(presetsDir):
            x = [i[:-len('.yaml')]
                 for i in os.listdir(presetsDir) if i.endswith('.yaml')]
        else:
            x = []
        self.api.send(['presets', registry.ls("/system.mixer/presets/") + x])

    def createChannel(self, name, data={}):
        with self.lock:
            self._createChannel(name, data)

    def _createChannel(self, name, data=channelTemplate):
        "Create a channel given the name and the data for it"
        self.channels[name] = data
        self.api.send(['channels', self.channels])
        if not self.running:
            return
        if not 'type' in data or data['type'] == "audio":
            backup = []
            if name in self.channelObjects:
                backup = self.channelObjects[name].backup()
                try:
                    self.channelObjects[name].stop()
                except:
                    log.exception(
                        "Error stopping old channel with that name, continuing")

            time.sleep(0.01)
            time.sleep(0.01)
            time.sleep(0.01)
            time.sleep(0.01)
            time.sleep(0.01)

            p = ChannelStrip(name, board=self, channels=data.get(
                'channels', 2), soundFuse=data.get('soundFuse', 3))
            self.channelObjects[name] = p
            p.fader = None
            p.loadData(data)
            p.addLevelDetector()
            p.finalize()
            p.connect(restore=backup)

        elif data['type'] == "midiConnection":
            self.channels[name] = data
            if name in self.channelObjects:
                self.channelObjects[name].stop()
            self.channelObjects[name] = MidiConnection(
                self, data['input'], data['output'])

    def deleteChannel(self, name):
        with self.lock:
            self._deleteChannel(name)

    def _deleteChannel(self, name):
        if name in self.channels:
            del self.channels[name]
        if name in self.channelObjects:
            self.channelObjects[name].stop()
            del self.channelObjects[name]
        self.api.send(['channels', self.channels])

    def pushLevel(self, cn, d):
        self.api.send(['lv', cn, round(d, 2)])

    def setFader(self, channel, level):
        "Set the fader of a given channel to the given level"
        if not self.running:
            return
        with self.lock:
            c = self.channelObjects[channel]
            c.setFader(level)

            # Push the real current value, not just repeating what was sent
            self.api.send(['fader', channel, c.faderTag.value])

            if c.faderTag.currentSource == 'default':
                self.channels[channel]['fader'] = float(level)

    def savePreset(self, presetName):
        if not presetName:
            raise ValueError("Empty preset name")
        with self.lock:
            util.disallowSpecialChars(presetName)
            persist.save(self.channels, os.path.join(
                presetsDir, presetName + ".yaml"))
            try:
                # Remove legacy way of saving
                registry.delete("/system.mixer/presets/" + presetName)
            except KeyError:
                pass
            self.loadedPreset = presetName
            self.api.send(['loadedPreset', self.loadedPreset])

    def deletePreset(self, presetName):
        registry.delete("/system.mixer/presets/" + presetName)
        if os.path.exists(os.path.join(presetsDir, presetName + ".yaml")):
            os.remove(os.path.join(presetsDir, presetName + ".yaml"))

    def loadPreset(self, presetName):
        with self.lock:
            x = list(self.channels)
            for i in x:
                self._deleteChannel(i)

            if os.path.isfile(os.path.join(presetsDir, presetName + ".yaml")):
                self._loadData(persist.load(
                    os.path.join(presetsDir, presetName + ".yaml")))
            else:
                x = registry.get("/system.mixer/presets/" + presetName, None)
                if x:
                    self._loadData(x)

            self.loadedPreset = presetName
            self.api.send(['loadedPreset', self.loadedPreset])

    def f(self, user, data):
        global recorder

        if data[0] == 'refresh':
            self.sendState()

        if data[0] == 'test':
            from . import sound
            sound.oggSoundTest(output=data[1])

        if data[0] == 'addChannel':
            # No overwrite
            if data[1] in self.channels:
                return
            # No empty names
            if not data[1]:
                return
            util.disallowSpecialChars(data[1])
            c = copy.deepcopy(channelTemplate)
            c['channels'] = data[2]
            self.createChannel(data[1], c)

        if data[0] == 'setEffects':
            "Directly set the effects data of a channel"
            with self.lock:
                self.channels[data[1]]['effects'] = data[2]
                self.api.send(['channels', self.channels])
                self._createChannel(data[1], self.channels[data[1]])

        if data[0] == 'setFuse':
            self.channels[data[1]]['soundFuse'] = float(data[2])
            self.channelObjects[data[1]].soundFuseSetting = float(data[2])

        if data[0] == 'setInput':
            self.channels[data[1]]['input'] = data[2]
            if not self.running:
                return
            self.channelObjects[data[1]].setInput(data[2])

        if data[0] == 'setOutput':
            self.channels[data[1]]['output'] = data[2]

            if not self.running:
                return
            self.channelObjects[data[1]].setOutputs(data[2].split(","))

        if data[0] == 'setFader':
            "Directly set the effects data of a channel"
            self.setFader(data[1], data[2])

        if data[0] == 'setParam':
            "Directly set the effects data of a channel. Packet is channel, effectID, paramname, val"

            for i in self.channels[data[1]]['effects']:
                if i['id'] == data[2]:
                    i['params'][data[3]]['value'] = data[4]
            if not self.running:
                return
            self.channelObjects[data[1]].setEffectParam(
                data[2], data[3], data[4])
            self.api.send(['param', data[1], data[2], data[3], data[4]])

            if[data[3]] == "bypass":
                self._createChannel(data[1], self.channels[data[1]])

        if data[0] == 'addEffect':
            with self.lock:
                fx = copy.deepcopy(effectTemplates[data[2]])

                fx['id'] = str(uuid.uuid4())
                self.channels[data[1]]['effects'].append(fx)
                self.api.send(['channels', self.channels])
                self._createChannel(data[1], self.channels[data[1]])

        if data[0] == 'refreshChannel':
            self._createChannel(data[1], self.channels[data[1]])

        if data[0] == 'rmChannel':
            self.deleteChannel(data[1])

        if data[0] == 'savePreset':
            self.savePreset(data[1])
            self.sendPresets()

        if data[0] == 'loadPreset':
            self.loadPreset(data[1])

        if data[0] == 'deletePreset':
            self.deletePreset(data[1])
            self.sendPresets()

        if data[0] == 'setUSBAlsa':
            settings.set("usbPeriodSize", int(data[1]))
            settings.set("usbLatency", int(data[2]))
            settings.set("usbQuality", int(data[3]))
            settings.set("usbPeriods", int(data[4]))

            self.api.send(['usbalsa', data[1], data[2], data[3], data[4]])
            jackmanager.reloadSettings()
            killUSBCards()

        if data[0] == 'record':
            with self.lock:
                if not recorder:
                    try:
                        recorder = Recorder(
                            pattern=data[1], channels=int(data[2]))
                        recorder.start()
                    except Exception as e:
                        self.api.send(['recordingStatus', str(e)])
                        raise

                self.api.send(['recordingStatus', "recording"])

        if data[0] == 'stopRecord':
            with self.lock:
                try:
                    recorder.sendEOS()
                except:
                    pass

                try:
                    recorder.stop()
                except:
                    pass
                recorder = None
                self.api.send(['recordingStatus', "off"])


def killUSBCards():
    try:
        subprocess.check_call(['killall', 'alsa_in'])
    except:
        pass
    try:
        subprocess.check_call(['killall', 'alsa_out'])
    except:
        pass


board = MixingBoard()

try:
    board.loadPreset('default')
except:
    messagebus.postMessage("Could not load default preset for JACK mixer")
    log.exception(
        "Could not load default preset for JACK mixer. Maybe it doesn't exist?")
