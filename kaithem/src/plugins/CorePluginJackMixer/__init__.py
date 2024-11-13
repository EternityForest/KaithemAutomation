# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import copy
import datetime
import json
import logging
import os
import subprocess
import threading
import time
import traceback
import uuid

import quart
import structlog
from scullery import jacktools, scheduling, workers

from kaithem.src import (
    alerts,
    dialogs,
    directories,
    gstwrapper,
    messagebus,
    modules_state,
    pages,
    quart_app,
    tagpoints,
    util,
    widgets,
)
from kaithem.src.plugins.CorePluginJackMixer import mixerfx

global_api = widgets.APIWidget()
global_api.require("system_admin")

# Configured list of mixer channel strips
channels: dict[str, dict] = {}

log = structlog.get_logger("system.mixer")

presetsDir = os.path.join(directories.mixerdir, "presets")

dummy_src_lock = threading.Lock()

recorder = None


ds = None


def start_dummy_source_if_needed():
    with dummy_src_lock:
        global ds
        if ds:
            return

        for i in range(25):
            if [
                i.name
                for i in jacktools.get_ports()
                if i.name.startswith("SILENCE")
            ]:
                return
            time.sleep(0.1)

        ds = subprocess.Popen(
            "gst-launch-1.0 audiotestsrc volume=0 ! pipewiresink client-name=SILENCE",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True,
        )

        for i in range(25):
            if [
                i.name
                for i in jacktools.get_ports()
                if i.name.startswith("SILENCE")
            ]:
                return
            time.sleep(0.1)

        raise Exception("Failed to start dummy source")


def onPortAdd(t, m):
    # m[1] is true of input
    global_api.send(["newport", m.name, {}, m.isInput])


def onPortRemove(t, m):
    # m[1] is true of input
    global_api.send(["rmport", m.name])


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
        if not gstwrapper.does_element_exist("tee"):
            log.error(
                "Gstreamer or python bindings not installed properly. Mixing will not work"
            )
    except Exception:
        log.exception(
            "Gstreamer or python bindings not installed properly. Mixing will not work"
        )
    if not gstwrapper.does_element_exist("pipewiresrc"):
        log.error("Gstreamer JACK plugin not found. Mixing will not work")

    for i in effectTemplates:
        e = effectTemplates[i]
        if "gstElement" in e:
            if not gstwrapper.does_element_exist(e["gstElement"]):
                log.warning(
                    "GST element "
                    + e["gstElement"]
                    + " not found. Some effects in the mixer will not work."
                )
        if "gstMonoElement" in e:
            if not gstwrapper.does_element_exist(e["gstMonoElement"]):
                log.warning(
                    "GST element "
                    + e["gstMonoElement"]
                    + " not found. Some effects in the mixer will not work."
                )
        if "gstStereoElement" in e:
            if not gstwrapper.does_element_exist(e["gstStereoElement"]):
                log.warning(
                    "GST element "
                    + e["gstStereoElement"]
                    + " not found. Some effects in the mixer will not work."
                )


effectTemplates_data = mixerfx.effectTemplates_data

effectTemplates = effectTemplates_data


def cleanupEffectData(fx):
    x = effectTemplates.get(fx["type"], {})
    for i in x:
        if i not in fx:
            fx[i] == x[i]

    if "help" not in fx:
        fx["help"] = ""
    if "displayName" not in fx:
        fx["displayName"] = fx["type"]
    if "gstSetup" not in fx:
        fx["gstSetup"] = {}


channelTemplate = {
    "type": "audio",
    "effects": [effectTemplates["fader"]],
    "input": "",
    "output": "",
    "fader": -60,
    "soundFuse": 3,
}


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


specialCaseParamCallbacks["3beq"] = beq3
specialCaseParamCallbacks["echo"] = echo
specialCaseParamCallbacks["queue"] = queue

# Returning true enables the default param setting action


def send(e, p, v):
    if v > -60:
        e.set_property("volume", 10 ** (float(v) / 20))
    else:
        e.set_property("volume", 0)


specialCaseParamCallbacks["send"] = send


class BaseChannel:
    pass


class FluidSynthChannel(BaseChannel):
    "Represents one MIDI connection with a single plugin that remaps all channels to one"

    def __init__(self, board, name, input, output, mapToChannel=0):
        self.name = name

        self.input = jacktools.MonoAirwire(input, f"{self.name}-midi:*")
        self.output = jacktools.airwire(self.name, output)

    def start(self):
        if self.map:
            self.process = subprocess.Popen(
                [
                    "fluidsynth",
                    "-a",
                    "jack",
                    "-m",
                    "jack",
                    "-c",
                    "0",
                    "-r",
                    "0",
                    "-o",
                    "audio.jack.id",
                    self.name,
                    "-o",
                    "audio.jack.multi",
                    "True",
                    "-o",
                    "midi.jack.id",
                    f"{self.name}-midi",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )
            self.input.connect()
            self.output.connect()
        else:
            self.airwire.connect()


class Recorder(gstwrapper.Pipeline):
    def __init__(self, name="krecorder", channels=2, pattern="mixer_"):
        gstwrapper.Pipeline.__init__(self, name, realtime=70)

        self.src = self.add_element(
            "pipewiresrc",
            client_name=name,
            do_timestamp=True,
            always_copy=True,
            stream_properties={"node.autoconnect": "false"},
        )
        # It is not ginna start unless we can make the connection to the silence thing
        # Before the thing even exists...
        self.silencein = jacktools.Airwire("SILENCE", name)

        def f():
            for i in range(100):
                try:
                    if [
                        i.name
                        for i in jacktools.get_ports()
                        if i.name.startswith(name)
                    ]:
                        break
                except Exception:
                    print(traceback.format_exc())
                time.sleep(0.1)

                self.silencein.connect()

        workers.do(f)

        self.capsfilter = self.add_element(
            "capsfilter", caps=f"audio/x-raw,channels={str(channels)}"
        )

        filename = os.path.join(
            directories.vardir,
            "recordings",
            "mixer",
            f"{pattern + datetime.datetime.now().isoformat()}.opus",
        )

        if not os.path.exists(
            os.path.join(directories.vardir, "recordings", "mixer")
        ):
            os.makedirs(os.path.join(directories.vardir, "recordings", "mixer"))

        self.add_element("queue")
        self.add_element("audioconvert")
        self.add_element("opusenc", bitrate=96000)

        self.add_element("oggmux")
        self.add_element("filesink", location=filename)


class ChannelStrip(gstwrapper.Pipeline, BaseChannel):
    def __init__(
        self,
        name,
        board: MixingBoard,
        channels=2,
        input=None,
        outputs=[],
        soundFuse=3,
    ):
        try:
            self.name = name
            self.input = input
            self._input = None
            self.outputs = outputs
            self._outputs = []
            self.sends = []
            self.sendAirwires: dict = {}

            gstwrapper.Pipeline.__init__(self, name)

            start_dummy_source_if_needed()
            self.board: MixingBoard = board
            self.levelTag = tagpoints.Tag(f"/jackmixer/channels/{name}.level")
            self.levelTag.min = -90
            self.levelTag.max = 3
            self.levelTag.hi = -3
            self.levelTag.unit = "dB"
            self.levelTag.writable = False
            self.levelTag.expose("view_status")

            # When it changes the thread exits
            self.stopMPVThread = 1

            # Set default
            self.levelTag.value = -90
            self.lastLevel = 0
            self.lastRMS = 0
            self.lastNormalVolumeLevel = time.time()
            # Limit how often we can clear the alert
            self.alertRatelimitTime = time.time() + 10
            self.soundFuseSetting = soundFuse
            self.lastPushedLevel = time.time()
            self.effectsById = {}
            self.effectDataById = {}
            self.faderLevel = -60
            self.channels = channels

            # Are we already doing a loudness cutoff?
            self.doingFeedbackCutoff = False

            self.created_time = time.time()

            if not input or not input.startswith("rtplisten://"):
                self.src = self.add_element(
                    "pipewiresrc",
                    client_name=f"{name}_in",
                    always_copy=True,
                    stream_properties={"node.autoconnect": "false"},
                )

                self.capsfilter = self.add_element(
                    "capsfilter",
                    caps=f"audio/x-raw,channels={str(channels)}",
                )
            else:
                self.src = self.add_element(
                    "udpsrc", port=int(input.split("://")[1])
                )
                self.capsfilter = self.add_element(
                    "capsfilter",
                    caps="application/x-rtp, media=(string)audio, clock-rate=(int)48000, encoding-name=(string)X-GST-OPUS-DRAFT-SPITTKA-00, payload=(int)96, ssrc=(uint)950073154, clock-base=(uint)639610336, seqnum-base=(uint)55488",  # noqa
                )
                self.add_element("rtpjitterbuffer")
                self.add_element("rtpopusdepay")
                self.add_element("opusdec")
                self.add_element("audioconvert")
                self.add_element("audioresample")

            self.faderTag = tagpoints.Tag(f"/jackmixer/channels/{name}.fader")
            self.faderTag.subscribe(self._faderTagHandler)
            self.faderTag.max = 20
            self.faderTag.min = -60
            self.faderTag.lo = -59
            self.faderTag.hi = 3
            self.faderTag.unit = "dB"
            self.faderTag.expose("view_status")

            self.mute = False

            self.effectParamTags = {}

            self.usingJack = True

            self.levelTag.set_alarm(
                "volume", "value>soundFuseSetting", trip_delay=0.3
            )

            # self.loudnessAlert = alerts.Alert(self.name+".abnormalvolume", priority='info')

        except Exception:
            print(traceback.format_exc())
            # Ensure fully cleaned up if any failure
            try:
                self.stop()
            except Exception:
                raise
            raise

    def check_ports(self):
        "Check that the ports actually exist"
        if not [
            i.name
            for i in jacktools.get_ports()
            if i.name.startswith(f"{self.name}_in:")
        ]:
            return False
        if not [
            i.name
            for i in jacktools.get_ports()
            if i.name.startswith(f"{self.name}_out:")
        ]:
            return False
        return True

    def mpv_input_loop(self):
        command = self.input.strip()
        if not (
            (command.startswith(("http://", "https://")))
            and command.endswith(".m3u")
            or command.endswith(".m3u8")
        ):
            return
        from subprocess import Popen

        n = f"{self.name}_src"
        line = [
            "mpv",
            command,
            "--profile=low-latency",
            "--no-cache",
            "--ao=jack",
            f"--jack-port={self.name}_in",
            f"--jack-name={n}",
            "--vo=null",
            "--no-video",
        ]

        x = jacktools.Airwire(
            n, f"{self.name}_in", force_combining=(self.channels == 1)
        )
        x.connect()

        p = Popen(line)

        initial = self.stopMPVThread

        while self.stopMPVThread == initial:
            time.sleep(1)
            rc = p.poll()
            if rc is not None:
                if not rc == 0:
                    for i in range(20):
                        time.sleep(0.25)
                        if not self.stopMPVThread == initial:
                            return

                p = Popen(line)

        p.terminate()

    @property
    def soundFuseSetting(self):
        return self._soundFuseSetting

    @soundFuseSetting.setter
    def soundFuseSetting(self, v):
        self._soundFuseSetting = v
        self.levelTag.eval_context["soundFuseSetting"] = v

    def finalize(self, wait=3):
        with self.lock:
            self.sink = self.add_element(
                "pipewiresink",
                client_name=f"{self.name}_out",
                mode=2,
                **{"async": False},
            )

        # It is not going to start unless we can make the connection to the silence thing
        # Before the thing even exists...
        # so we start it then do the connection in the background
        self.silencein = jacktools.Airwire("SILENCE", f"{self.name}_in")

        def f():
            for i in range(100):
                try:
                    if [
                        i.name
                        for i in jacktools.get_ports()
                        if i.name.startswith(f"{self.name}_in:")
                    ]:
                        break
                except Exception:
                    print(traceback.format_exc())
                time.sleep(0.1)
            self.silencein.connect()

        workers.do(f)

        self.start(timeout=wait)

        for i in range(25):
            try:
                if [
                    i.name
                    for i in jacktools.get_ports()
                    if i.name.startswith(f"{self.name}_in:")
                ]:
                    break
            except Exception:
                print(traceback.format_exc())
            time.sleep(0.2)

        for i in range(25):
            try:
                if [
                    i.name
                    for i in jacktools.get_ports()
                    if i.name.startswith(f"{self.name}_out:")
                ]:
                    break
            except Exception:
                print(traceback.format_exc())
            time.sleep(0.2)

        # do it here, after things are set up
        self.faderTag.value = self.initialFader
        # Call directly, the tag might think we are already at the right level, if we are remaking a channel
        # and had set the element volume to zero directly but not the tag.
        self._faderTagHandler(self.faderTag.value, None, None)

    def connect(self, restore=[]):
        self._outputs = []

        # wait till it exists for real
        for i in range(8):
            pt = jacktools.get_ports()
            p = [i.name for i in pt]
            p2 = [i.clientName for i in pt]
            p = p + p2
            if (f"{self.name}_out" in p) and (f"{self.name}_in") in p:
                break
            else:
                time.sleep(0.5)

        for i in self.outputs:
            x = jacktools.Airwire(
                f"{self.name}_out", i, force_combining=(self.channels == 1)
            )
            x.connect()
            self._outputs.append(x)

        self.setInput(self.input)

        for i in restore:
            for j in i[1]:
                try:
                    jacktools.connect(i[0], j)
                except Exception:
                    log.exception("Failed to conneect airwire")
        for i in self.sendAirwires:
            try:
                self.sendAirwires[i].connect()
            except Exception:
                log.exception("Failed to conneect airwire")

    def stop(self, at_exit=False):
        self.stopMPVThread = None
        with self.lock:
            # At exit don't bother, I don't think it's really needed
            # At all now that pipewire crashes less than the old daemon
            if not at_exit:
                for i in self.sendAirwires:
                    self.sendAirwires[i].disconnect()
                if self._input:
                    self._input.disconnect()
                for i in self._outputs:
                    i.disconnect()

        name = self.name

        gstwrapper.Pipeline.stop(self)

        if not at_exit:
            # wait till jack catches up
            for i in range(15):
                p = [i.name for i in jacktools.get_ports()]
                p2 = [i.clientName for i in jacktools.get_ports()]
                p = p + p2
                # Todo check the sends as well?
                if f"{name}_out" in p:
                    time.sleep(0.5)
                else:
                    # Give a little extra time just in case
                    time.sleep(0.25)
                    break

    def backup(self):
        c = []

        for i in jacktools.get_ports(f"{self.name}_in:"):
            c.append((i, jacktools.get_connections(i)))
        for i in jacktools.get_ports(f"{self.name}_out:"):
            c.append((i, jacktools.get_connections(i)))
        return c

    def setInput(self, input):
        # Stop whatever was there before
        self.stopMPVThread = time.time()
        if (
            "://" in input
            and ("http://" not in input)
            and ("https://" not in input)
        ):
            return
        with self.lock:
            self.input = input
            if self._input:
                self._input.disconnect()
            if "://" not in self.input:
                self._input = jacktools.Airwire(
                    self.input,
                    f"{self.name}_in",
                    force_combining=(self.channels == 1),
                )
                self._input.connect()
            else:
                t = threading.Thread(target=self.mpv_input_loop, daemon=True)
                t.start()

    def setOutputs(self, outputs):
        with self.lock:
            self.outputs = outputs
            for i in self._outputs:
                i.disconnect()

            self._outputs = []
            for i in self.outputs:
                x = jacktools.Airwire(
                    f"{self.name}_out", i, force_combining=(self.channels == 1)
                )
                x.connect()
                self._outputs.append(x)

    def addSend(self, target, id, volume=-60):
        # I hate doing things like this...
        # But senda apparently use a lot of low level pipeline manipulation
        # that has to be done on
        # the other side.
        with self.lock:
            if not isinstance(target, str):
                raise ValueError("Target must be string")

            cname = f"{self.name}_send{str(len(self.sends))}"

            linkTo = self.add_element("tee")
            linkTo = self.add_element(
                "queue", connect_to_output=linkTo, sidechain=True
            )

            linkTo = vl = self.add_element(
                "volume",
                volume=10 ** (volume / 20),
                connect_to_output=linkTo,
                sidechain=True,
            )
            linkTo = self.add_element(
                "audioconvert", connect_to_output=linkTo, sidechain=True
            )

            self.add_element(
                "pipewiresink",
                client_name=cname,
                mode=2,
                connect_to_output=linkTo,
                sidechain=True,
                **{"async": False},
            )

            self.effectsById[id] = vl

            d = effectTemplates["send"]
            d["params"]["*destination"]["value"] = target
            d["params"]["*db_volume"]["value"] = volume
            self.effectDataById[id] = d

            self.sendAirwires[id] = jacktools.Airwire(
                cname, target, force_combining=(self.channels == 1)
            )
            self.sends.append(vl)
            self.sendAirwires[id].connect()
            self.sendAirwires[id].send_source = cname

    def loadData(self, d):
        self.mute = d.get("mute", False)

        end_chain = []

        for i in d["effects"]:
            if d.get("bypass", False):
                continue
            if "id" not in i or not i["id"]:
                i["id"] = str(uuid.uuid4())
            if i["type"] == "fader":
                self.fader = self.add_element("volume")
                # Set to 0 until all is set up
                self.initialFader = d["fader"]
                self.fader.set_property("volume", 0.0)
            # Special case this, it's made of multiple gstreamer blocks and also airwires
            elif i["type"] == "send":
                self.addSend(
                    i["params"]["*destination"]["value"],
                    i["id"],
                    i["params"]["*db_volume"]["value"],
                )

            else:
                # Sidechain lets us split off a whole effect chain that does not
                # feed the main chain, such as fir the speech recognition effect
                if i.get("sidechain", 0):
                    linkTo = self.add_element("tee")
                    self.add_element(
                        "queue",
                        leaky=2,
                        max_size_time=100_0000_0000,
                        name=f"mainchainq_{i['id']}",
                        connect_to_output=linkTo,
                    )
                    linkTo = self.add_element(
                        "queue",
                        leaky=2,
                        sidechain=True,
                        connect_to_output=linkTo,
                        max_size_buffers=1,
                        name=f"sidechainq_{i['id']}",
                    )
                    sidechain = True

                else:
                    # Default link to prev
                    linkTo = None
                    sidechain = False

                supports = []
                if "preSupportElements" in i:
                    for j in i["preSupportElements"]:
                        linkTo = self.add_element(
                            j["gstElement"],
                            **j["gstSetup"] or {},
                            auto_insert_audio_convert=True,
                            sidechain=sidechain,
                            connect_to_output=linkTo
                            if (not j.get("noConnectInput", False))
                            else False,
                        )
                        supports.append(linkTo)

                # Prioritize specific mono or stereo version of elements
                if self.channels == 1 and "monoGstElement" in i:
                    linkTo = self.effectsById[i["id"]] = self.add_element(
                        i["monoGstElement"],
                        **i["gstSetup"] or {},
                        sidechain=sidechain,
                        auto_insert_audio_convert=True,
                        connect_to_output=linkTo
                        if (not i.get("noConnectInput", False))
                        else False,
                        connect_when_available=i.get(
                            "connect_when_available", None
                        ),
                    )
                elif self.channels == 2 and "stereoGstElement" in i:
                    linkTo = self.effectsById[i["id"]] = self.add_element(
                        i["stereoGstElement"],
                        **i["gstSetup"] or {},
                        sidechain=sidechain,
                        auto_insert_audio_convert=True,
                        connect_to_output=linkTo
                        if (not i.get("noConnectInput", False))
                        else False,
                        connect_when_available=i.get(
                            "connect_when_available", None
                        ),
                    )
                else:
                    linkTo = self.effectsById[i["id"]] = self.add_element(
                        i["gstElement"],
                        **i["gstSetup"],
                        sidechain=sidechain,
                        auto_insert_audio_convert=True,
                        connect_to_output=linkTo
                        if (not i.get("noConnectInput", False))
                        else False,
                        connect_when_available=i.get(
                            "connect_when_available", None
                        ),
                    )

                elmt = linkTo
                linkTo.preSupports = supports

                self.effectDataById[i["id"]] = i

                supports = []
                if "postSupportElements" in i:
                    for j in i["postSupportElements"]:
                        linkTo = self.add_element(
                            j["gstElement"],
                            **j["gstSetup"],
                            auto_insert_audio_convert=True,
                            sidechain=sidechain,
                            connect_to_output=linkTo
                            if (not j.get("noConnectInput", False))
                            else False,
                        )
                        supports.append(linkTo)

                if "endChainSupportElements" in i:
                    for j in i["endChainSupportElements"]:
                        end_chain.append(j)

                elmt.postSupports = supports

                for j in i["params"]:
                    if j == "bypass":
                        continue
                    if i["type"] in specialCaseParamCallbacks:
                        x = specialCaseParamCallbacks[i["type"]]
                        if x(
                            self.effectsById[i["id"]],
                            j,
                            i["params"][j]["value"],
                        ):
                            self.set_property(
                                self.effectsById[i["id"]],
                                j,
                                i["params"][j]["value"],
                            )
                    else:
                        self.setEffectParam(i["id"], j, i["params"][j]["value"])

                # Sidechain FX have a bug where they always cause an output to the system channel, we have to work around
                # That with a hack.  Basically sidechains only exist to let us to alternative outputs anyway.
                if i.get("silenceMainChain", False):
                    self.add_element("volume", volume=0)
        for j in end_chain:
            self.add_element(
                j["gstElement"],
                **j["gstSetup"],
                auto_insert_audio_convert=True,
            )

        self.setInput(d["input"])
        self.setOutputs(d["output"].split(","))

    def setEffectParam(self, effectId, param, value):
        "Set val after casting, and return properly typed val"
        with self.lock:
            paramData = self.effectDataById[effectId]["params"][param]
            paramData["value"] = value
            t = paramData["type"]

            if t == "float":
                value = float(value)

            if t == "bool":
                value = value > 0.5

            if t == "enum":
                value = float(value)
                if value % 1 == 0:
                    value = int(value)

            if t == "int":
                value = int(value)

            if t == "string.int":
                try:
                    value = int(value)
                except Exception:
                    value = 0

            # One type of special case
            if param[0] == "*":
                if param == "*destination":
                    # Keep the old origin, just swap the destination
                    if effectId in self.sendAirwires:
                        self.sendAirwires[effectId].disconnect()
                        self.sendAirwires[effectId] = jacktools.Airwire(
                            self.sendAirwires[effectId].send_source,
                            value,
                            force_combining=(self.channels == 1),
                        )
                        try:
                            self.sendAirwires[effectId].connect()
                        except Exception:
                            pass

                elif param == "*db_volume":
                    self.effectsById[effectId].set_property(
                        "volume", 10 ** (value / 20)
                    )

            elif param == "bypass":
                pass
            else:
                if t in specialCaseParamCallbacks:
                    r = specialCaseParamCallbacks[t](
                        self.effectsById[effectId], param, value
                    )
                    if r:
                        if r == "pause":
                            self.pause()
                        self.set_property(
                            self.effectsById[effectId], param, value
                        )
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

                    self.set_property(fx, param, value)
        return value

    def addLevelDetector(self):
        self.levelDetector = self.add_element(
            "level",
            post_messages=True,
            peak_ttl=300 * 1000 * 1000,
            peak_falloff=60,
            interval=10**9 / 24,
        )

    def on_level_message(self, src, rms, level):
        if self.board:
            rms = max(rms, -90)

            self.doSoundFuse(rms)
            if abs(level - self.lastLevel) < 3:
                if time.time() - self.lastPushedLevel < 1:
                    return True
            else:
                if time.time() - self.lastPushedLevel < 0.07:
                    return True

            # Avoid having to do the whole tag lock thing if
            # the value hasn't changed, it's not critcal and the
            # race condition is fine
            if not self.levelTag.last_value == rms:
                self.levelTag.value = rms

            level = max(round(level, 2), -99)
            self.board.channels[self.name]["level"] = level
            self.lastPushedLevel = time.time()
            self.lastLevel = level
            self.board.pushLevel(self.name, level)

    def onSTTMessage(self, v):
        messagebus.post_message(
            f"/system/mixer/channels/{self.name}/stt/hypothesis", (v,)
        )

    def onSTTMessageFinal(self, v):
        messagebus.post_message(
            f"/system/mixer/channels/{self.name}/stt/final", (v,)
        )

    def doSoundFuse(self, rms):
        # Highly dynamic stuff is less likely to be feedback.
        # Don't count feedback if there's any decrease
        # Aside from very small decreases, there's likely other stuff happening too.
        # But if we are close to clipping ignore that
        if not (
            ((self.lastRMS < (rms + 1.5)) or rms > -2)
            and rms > self.soundFuseSetting
        ):
            self.lastNormalVolumeLevel = time.time()
        self.lastRMS = rms
        if time.time() - self.lastNormalVolumeLevel > 0.2:
            # self.loudnessAlert.trip()
            self.alertRatelimitTime = time.time()

            if not self.doingFeedbackCutoff:
                self.doingFeedbackCutoff = True

                def f():
                    "Greatly reduce volume, then slowly increase it, till the user does something about it"
                    try:
                        print("FEEDBACK DETECTED!!!!")
                        faderval = self.faderTag.value
                        self.setFader(faderval - 18)
                        c = self.faderTag.value
                        time.sleep(0.25)
                        # Detect manual action
                        if not c == self.faderTag.value:
                            return
                        t = 18

                        time.sleep(2.5)
                        # Detect manual action
                        if not c == self.faderTag.value:
                            return

                        # Slowly go back up

                        while t:
                            t -= 1
                            self.setFader(faderval - t)
                            c = self.faderTag.value

                            # Wait longer on that last one before we exit,
                            # To ensure it worked
                            if t == 1:
                                time.sleep(1)
                            time.sleep(0.1)
                            # Detect manual action
                            if not c == self.faderTag.value:
                                return

                            if self.levelTag.value > self.soundFuseSetting - 3:
                                t += 3
                                self.setFader(faderval - t)
                                c = self.faderTag.value

                                time.sleep(1)
                                # Detect manual action
                                if not c == self.faderTag.value:
                                    return

                        # Return to normal
                        self.setFader(faderval)
                    finally:
                        print("FEEDBACK HANDLER EXIT")
                        self.doingFeedbackCutoff = False

                workers.do(f)

        elif time.time() - self.alertRatelimitTime > 10:
            # self.loudnessAlert.release()
            self.alertRatelimitTime = time.time()

    def _faderTagHandler(self, level, t, a):
        # Note: We don't set the configured data fader level here.
        self.board.api.send(["fader", self.name, level])

        if self.fader:
            try:
                if self.mute:
                    self.fader.set_property("volume", 0)
                else:
                    if level > -60:
                        self.fader.set_property(
                            "volume", 10 ** (float(level) / 20)
                        )
                    else:
                        self.fader.set_property("volume", 0)
            except Exception:
                self.board.reloadChannel(self.name)

    def setFader(self, level):
        # Let the _faderTagHandler handle it.
        self.faderTag.value = level

    def setMute(self, m):
        self.mute = m
        self._faderTagHandler(self.faderTag.value, 0, 0)
        if self.board:
            self.board.api.send(["mute", self.name, self.mute])


def checkIfProcessRunning(processName):
    """
    Check if there is any running process that contains the given name processName.
    """
    try:
        import psutil
    except Exception:
        return False

    # Iterate over the all the running process
    for proc in psutil.process_iter():
        try:
            # Check if process name contains the given name string.
            if processName.lower() in proc.name().lower():
                return True
        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
            psutil.ZombieProcess,
        ):
            pass
    return False


lastAutoReload = [0]

actionLockout = {}


class MixingBoard:
    def __init__(self, module: str, resource: str, data=None, *args, **kwargs):
        class WrappedLink(widgets.APIWidget):
            def on_new_subscriber(s, user, cid, **kw):
                self.sendState()

        self.module = module
        self.resource = resource

        self.resourcedata: modules_state.ResourceDictType = data or {
            "presets": {}
        }
        if "presets" not in self.resourcedata:
            self.resourcedata["presets"] = {}
        self.api = WrappedLink()
        self.api.require("system_admin")
        self.api.attach(self.f)
        self.channels = {}
        self.channelObjects: dict[str, ChannelStrip] = {}
        self.channelAlerts = {}
        self.lock = threading.RLock()
        self.channelStatus = {}
        self.running = checkIfProcessRunning(
            "pipewire"
        ) or checkIfProcessRunning("jackd")

        def f(t, v):
            self.running = True
            self.reload()

        messagebus.subscribe("/system/jack/started", f)
        self.reloader = f
        self.loadedPreset = "default"

        if "default" in self.resourcedata["presets"]:
            workers.do(lambda: self.loadPreset("default"))

        self.checker = scheduling.scheduler.every_minute(self.poll)

    def loadData(self, d):
        with self.lock:
            self._loadData(d)

    def reload(self):
        self.loadData(self.channels)

    def poll(self):
        if not self.running:
            return

        # This could iterationerror, just ignore it and move on for now
        for name, i in self.channelObjects.items():
            if i.created_time < (time.time() - 60):
                if not i.check_ports():
                    logging.error(
                        f"Ports for {name} not found, remaking channel"
                    )
                    if not actionLockout.get(name, 0) > time.time() - 10:
                        actionLockout[name] = time.time()
                        self._createChannel(name, self.channels[name])
                        actionLockout.pop(name, None)

    def _loadData(self, x):
        # Raise an error if it can't be serialized
        json.dumps(x)
        if not isinstance(x, dict):
            raise TypeError("Data must be a dict")

        self.channels = x
        if not self.running:
            return
        for i in self.channels:
            log.info(f"Creating mixer channel {i}")
            try:
                self._createChannel(i, self.channels[i])
            except Exception as e:
                messagebus.post_message(
                    "/system/notifications/errors",
                    f"Failed to create mixer channel {i} see logs.",
                )
                log.exception(f"Could not create channel {i}")
                self.pushStatus(i, f"error {str(e)}")

    def sendChannels(self):
        m = self.module
        mf = modules_state.getModuleDir(m)
        mf = os.path.join(mf, "__filedata__/media")

        c = copy.deepcopy(self.channels)

        # Placeholder here to not mess up vue rendering
        for i in c:
            c[i]["level"] = -99
            resolved = os.path.join(mf, c[i].get("label_image", ""))
            if os.path.isfile(resolved):
                c[i]["labelImageTimestamp"] = os.path.getmtime(resolved)

        self.api.send(["channels", c])

    def sendState(self):
        if not self.running:
            return
        inPorts = jacktools.get_port_names_with_aliases(
            is_audio=True, is_input=True
        )
        outPorts = jacktools.get_port_names_with_aliases(
            is_audio=True, is_output=True
        )
        midiOutPorts = jacktools.get_port_names_with_aliases(
            is_midi=True, is_output=True
        )
        midiInPorts = jacktools.get_port_names_with_aliases(
            is_midi=True, is_input=True
        )

        self.api.send(["inports", {i: {} for i in inPorts}])
        self.api.send(["outports", {i: {} for i in outPorts}])
        self.api.send(["midiinports", {i: {} for i in midiInPorts}])
        self.api.send(["midioutports", {i: {} for i in midiOutPorts}])

        self.api.send(["effectTypes", effectTemplates])

        if self.lock.acquire(timeout=5):
            try:
                self.sendChannels()

                for i in self.channels:
                    self.pushStatus(i)

                self.api.send(["loadedPreset", self.loadedPreset])

                self.sendPresets()

                if recorder:
                    self.api.send(["recordingStatus", "recording"])
                else:
                    self.api.send(["recordingStatus", "off"])
                self.api.send(["ui_ready"])
            finally:
                self.lock.release()

    def sendPresets(self):
        if os.path.isdir(presetsDir):
            x = [
                i[: -len(".yaml")]
                for i in os.listdir(presetsDir)
                if i.endswith(".yaml")
            ]
        else:
            x = []
        self.api.send(["presets", x])

    def createChannel(self, name, data={}):
        if not self.running:
            return

        with self.lock:
            if name in self.channelObjects:
                self.channelObjects[name].stop()
            self._createChannel(name, data)

    def _createChannel(self, name, data=channelTemplate):
        self.pushStatus(name, "loading")

        if name not in self.channelAlerts:
            self.channelAlerts[name] = alerts.Alert(
                f"Mixer channel {name}",
                priority="error",
                trip_delay=35,
                auto_ack=True,
            )

        for i in range(3):
            try:
                self._createChannelAttempt(name, data, wait=(10))
                self.channelAlerts[name].release()
                self.pushStatus(name, "running")
                break
            except Exception as e:
                self.channelAlerts[name].trip("Failed to load channel")
                log.exception("Failed to create channel, retrying")
                self.pushStatus(name, f"failed {str(e)}")
                time.sleep(1 + i)

    def _createChannelAttempt(self, name, data=channelTemplate, wait=3):
        if not self.running:
            return
        "Create a channel given the name and the data for it"
        self.channels[name] = data
        self.sendChannels()
        for i in self.channels:
            self.pushStatus(i)
        self.pushStatus(name, "loading")

        if not self.running:
            if not (
                checkIfProcessRunning("pipewire")
                or checkIfProcessRunning("jackd")
            ):
                return
            else:
                self.running = True

        if "type" not in data or data["type"] == "audio":
            backup = []
            if name in self.channelObjects:
                self.pushStatus(name, "stopping old")

                backup = self.channelObjects[name].backup()
                try:
                    self.channelObjects[name].stop()
                    time.sleep(1)
                except Exception:
                    log.exception(
                        "Error stopping old channel with that name, continuing"
                    )

            self.pushStatus(name, "loading")

            time.sleep(0.01)
            time.sleep(0.01)
            time.sleep(0.01)
            time.sleep(0.01)
            time.sleep(0.01)
            p = None
            try:
                p = ChannelStrip(
                    name,
                    board=self,
                    channels=data.get("channels", 2),
                    soundFuse=data.get("soundFuse", 3),
                    input=data.get("input"),
                )
                self.channelObjects[name] = p
                p.fader = None
                p.loadData(data)
                p.addLevelDetector()
                p.finalize(wait)

                p.connect(restore=backup)
                self.pushStatus(name, "running")
            except Exception:
                if p:
                    p.stop()
                raise

    def deleteChannel(self, name):
        with self.lock:
            self._deleteChannel(name)

    def _deleteChannel(self, name):
        if name in self.channelObjects:
            try:
                self.channelObjects[name].stop()
            except Exception:
                logging.exception("Exception deleting mixer channel")
            del self.channelObjects[name]

        if name in self.channels:
            del self.channels[name]

        if name in self.channelAlerts:
            self.channelAlerts[name].release()
            del self.channelAlerts[name]

        self.sendChannels()
        for i in self.channels:
            self.pushStatus(i)

    def pushLevel(self, cn, d):
        if not self.running:
            return
        self.api.send(["lv", cn, round(d, 2)])

    def pushStatus(self, cn, s=None):
        if s:
            self.channelStatus[cn] = s
        else:
            s = self.channelStatus.get(cn, "not running")
        self.api.send(["status", cn, s])

    def setFader(self, channel, level):
        "Set the fader of a given channel to the given level"
        if not self.running:
            return
        with self.lock:
            c = self.channelObjects[channel]
            c.setFader(level)

            if c.faderTag.current_source == "default":
                self.channels[channel]["fader"] = float(level)

    def savePreset(self, presetName):
        if not presetName:
            raise ValueError("Empty preset name")
        with self.lock:
            util.disallowSpecialChars(presetName)
            self.resourcedata["presets"][presetName] = copy.deepcopy(
                self.channels
            )
            modules_state.rawInsertResource(
                self.module, self.resource, self.resourcedata
            )

            self.loadedPreset = presetName
            self.api.send(["loadedPreset", self.loadedPreset])

    def deletePreset(self, presetName):
        if os.path.exists(os.path.join(presetsDir, f"{presetName}.yaml")):
            os.remove(os.path.join(presetsDir, f"{presetName}.yaml"))

    def loadPreset(self, presetName: str):
        with self.lock:
            x = list(self.channels)
            for i in x:
                self._deleteChannel(i)

            if presetName in self.resourcedata["presets"]:  # type: ignore
                self._loadData(self.resourcedata["presets"][presetName])  # type: ignore
            else:
                log.error(f"No such preset {str(presetName)}")

            self.loadedPreset = presetName
            self.api.send(["loadedPreset", self.loadedPreset])

    def reloadChannel(self, name):
        # disallow spamming
        if not actionLockout.get(name, 0) > time.time() - 10:
            actionLockout[name] = time.time()
            self._createChannel(name, self.channels[name])
            actionLockout.pop(name, None)

    def f(self, user, data):
        def f2():
            global recorder
            if data[0] == "refresh":
                self.sendState()

            elif data[0] == "test":
                from icemedia import sound_player as sound

                sound.test(output=data[1])

            elif data[0] == "addChannel":
                # No overwrite
                if data[1] in self.channels:
                    return
                # No empty names
                if not data[1]:
                    return
                util.disallowSpecialChars(data[1])
                c = copy.deepcopy(channelTemplate)
                c["channels"] = data[2]
                self.createChannel(data[1], c)

            elif data[0] == "setEffects":
                "Directly set the effects data of a channel"
                with self.lock:
                    self.channels[data[1]]["effects"] = data[2]
                    self.sendChannels()
                    for i in self.channels:
                        self.pushStatus(i)
                    self._createChannel(data[1], self.channels[data[1]])

            elif data[0] == "setFuse":
                self.channels[data[1]]["soundFuse"] = float(data[2])
                self.channelObjects[data[1]].soundFuseSetting = float(data[2])

            elif data[0] == "setInput":
                self.channels[data[1]]["input"] = data[2]
                if not self.running:
                    return
                self.channelObjects[data[1]].setInput(data[2])

            elif data[0] == "setMute":
                self.channels[data[1]]["mute"] = bool(data[2])
                if not self.running:
                    return
                self.channelObjects[data[1]].setMute(data[2])

            elif data[0] == "setOutput":
                self.channels[data[1]]["output"] = data[2]

                if not self.running:
                    return
                self.channelObjects[data[1]].setOutputs(data[2].split(","))

            elif data[0] == "setFader":
                "Directly set the effects data of a channel"
                self.setFader(data[1], data[2])

            elif data[0] == "setParam":
                "Directly set the effects data of a channel. Packet is channel, effectID, paramname, val"

                for i in self.channels[data[1]]["effects"]:
                    if i["id"] == data[2]:
                        i["params"][data[3]]["value"] = data[4]
                if not self.running:
                    return
                self.channelObjects[data[1]].setEffectParam(
                    data[2], data[3], data[4]
                )
                self.api.send(["param", data[1], data[2], data[3], data[4]])

                if [data[3]] == "bypass":
                    self._createChannel(data[1], self.channels[data[1]])

            elif data[0] == "addEffect":
                with self.lock:
                    fx = copy.deepcopy(effectTemplates[data[2]])

                    fx["id"] = str(uuid.uuid4())
                    self.channels[data[1]]["effects"].append(fx)
                    self.sendChannels()
                    for i in self.channels:
                        self.pushStatus(i)
                    self._createChannel(data[1], self.channels[data[1]])

            elif data[0] == "refreshChannel":
                self.reloadChannel(data[1])

            elif data[0] == "rmChannel":
                self.deleteChannel(data[1])

            elif data[0] == "savePreset":
                self.savePreset(data[1])
                self.sendPresets()

            elif data[0] == "loadPreset":
                self.loadPreset(data[1])

            elif data[0] == "deletePreset":
                self.deletePreset(data[1])
                self.sendPresets()

            elif data[0] == "record":
                with self.lock:
                    if not recorder:
                        try:
                            recorder = Recorder(
                                name="recorder_"
                                + self.module
                                + "_"
                                + self.resource,
                                pattern=data[1],
                                channels=int(data[2]),
                            )
                            recorder.start()
                        except Exception as e:
                            self.api.send(["recordingStatus", str(e)])
                            raise

                    self.api.send(["recordingStatus", "recording"])

            elif data[0] == "stopRecord":
                with self.lock:
                    try:
                        recorder.sendEOS()
                    except Exception:
                        pass

                    try:
                        recorder.stop()
                    except Exception:
                        pass
                    recorder = None
                    self.api.send(["recordingStatus", "off"])

            elif data[0] == "set_label_image":
                self.channels[data[1]]["label_image"] = data[2]
                self.sendChannels()

            else:
                raise ValueError("Unknown command: " + data[0])

        workers.do(f2)

    def stop(self):
        # Shut down in opposite order we started in
        with self.lock:
            self.running = False
            for i in list(self.channelObjects.keys()):
                self.channelObjects[i].stop(at_exit=True)


def STOP(*a):
    global ds
    # Shut down in opposite order we started in
    for board in boards.values():
        with board.lock:
            board.running = False
            for i in board.channelObjects:
                board.channelObjects[i].stop(at_exit=True)

    try:
        if ds:
            ds.terminate()
            ds = None
    except Exception:
        logging.exception("Exception stopping dummy source")


messagebus.subscribe("/system/shutdown", STOP)


td = os.path.join(os.path.dirname(__file__), "html", "mixer.html")


@quart_app.app.route("/settings/mixer/<boardname>/<channel>/image")
async def get_label_image(boardname: str, channel: int):
    pages.require("system_admin")

    @quart.ctx.copy_current_request_context
    def f():
        c = boards[boardname].channels[channel].get("label_image", "")
        m = boards[boardname].module
        mf = modules_state.getModuleDir(m)
        mf = os.path.join(mf, "__filedata__/media")

        if os.path.isfile(os.path.join(mf, c)):
            return os.path.join(mf, c)

    fn = await f()
    return await quart.send_file(fn)


@quart_app.app.route(
    "/settings/mixer/<boardname>/<channel>/set_channel_img", methods=["POST"]
)
async def set_mixer_channel_label(boardname: str, channel: int):
    pages.require("system_admin")
    kw = dict(await quart.request.form)
    kw.update(quart.request.args)

    fn = kw["resource"][len("media/") :]

    boards[boardname].channels[channel]["label_image"] = fn

    workers.do(boards[boardname].sendChannels)

    return "OK"


@quart_app.app.route("/settings/mixer/<boardname>")
def handle_mixer_plugin(boardname: str):
    from kaithem.src import directories

    pages.require("system_admin")
    return pages.get_template(td).render(
        os=os,
        board=boards[boardname],
        global_api=global_api,
        directories=directories,
    )


boards: dict[str, MixingBoard] = {}


class MixingBoardType(modules_state.ResourceType):
    def blurb(self, module, resource, data):
        return f"""
        <div class="tool-bar">
            <a href="/settings/mixer/{module}:{resource}">
            Mixing Board</a>
        </div>
        """

    def on_load(self, module, resource, data):
        x = boards.pop(f"{module}:{resource}", None)
        boards[f"{module}:{resource}"] = MixingBoard(module, resource, data)
        if x:
            x.stop()

    def on_move(self, module, resource, to_module, to_resource, data):
        x = boards.pop(f"{module}:{resource}", None)
        if x:
            boards[f"{to_module}:{to_resource}"] = x

    def on_update(self, module, resource, data):
        self.on_load(module, resource, data)

    def on_delete(self, module, name, value):
        boards[f"{module}:{name}"].stop()
        del boards[f"{module}:{name}"]

    def on_create_request(self, module, name, kwargs):
        d = {"resource_type": self.type}
        return d

    def on_update_request(self, module, resource, resourceobj, kwargs):
        d = resourceobj
        kwargs.pop("name", None)
        kwargs.pop("Save", None)
        return d

    def create_page(self, module, path):
        d = dialogs.SimpleDialog("New Mixer")
        d.text_input("name", title="Resource Name")

        d.submit_button("Save")
        return d.render(self.get_create_target(module, path))

    def edit_page(self, module, name, value):
        d = dialogs.SimpleDialog("Editing Mixer")
        d.text("Edit the board in the mixer UI")

        return d.render(self.get_update_target(module, name))


drt = MixingBoardType(
    "mixing_board",
    mdi_icon="tune-vertical-variant",
    title="Mixing Board",
    priority=10,
)
modules_state.additionalTypes["mixing_board"] = drt
