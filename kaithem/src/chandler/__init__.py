import time
import random
import weakref
import os
import threading
import uuid
import logging
import traceback
import yaml
import copy
import json
import collections
import datetime
import pytz
from decimal import Decimal
from tinytag import TinyTag
from typeguard import typechecked
import urllib
import numpy
import base64

from ..kaithemobj import kaithem
from . import core
from . import universes
from . import blendmodes
from . import fixtureslib

import recur


def dt_to_ts(dt, tz=None):
    "Given a datetime in tz, return unix timestamp"
    if tz:
        utc = pytz.timezone('UTC')
        return ((tz.localize(dt.replace(tzinfo=None)) - datetime.datetime(1970, 1, 1, tzinfo=utc)) / datetime.timedelta(seconds=1))

    else:
        # Local Time
        ts = time.time()
        offset = (datetime.datetime.fromtimestamp(ts) -
                  datetime.datetime.utcfromtimestamp(ts)).total_seconds()
        return ((dt - datetime.datetime(1970, 1, 1)) / datetime.timedelta(seconds=1)) - offset


# https://gist.github.com/devxpy/063968e0a2ef9b6db0bd6af8079dad2a
NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
OCTAVES = list(range(11))
NOTES_IN_OCTAVE = len(NOTES)


def number_to_note(number: int) -> str:
    octave = number // NOTES_IN_OCTAVE
    note = NOTES[number % NOTES_IN_OCTAVE]

    return note + str(octave)


def nbr():
    return (50, '<a href="/chandler/commander"><i class="icofont-cheer-leader"></i>Chandler</a>')


kaithem.web.navBarPlugins['chandler'] = nbr


def nbr2():
    return (50, '<a href="/chandler/editor"><i class="icofont-pencil"></i>Editor</a>')


kaithem.web.navBarPlugins['chandler2'] = nbr2

logger = logging.getLogger("system.chandler")

soundLock = threading.Lock()


soundActionSerializer = threading.RLock()

soundActionQueue = []


# We must serialize sound actions to avoid a race condition where the stop
# Happens before the start, causing the sound to keep going
def doSoundAction(g):
    soundActionQueue.append(g)

    def f():
        if soundActionSerializer.acquire(timeout=25):
            try:
                while soundActionQueue:
                    x = soundActionQueue.pop(False)
                    x()
            finally:
                soundActionSerializer.release()

    kaithem.misc.do(f)


def playSound(*args, **kwargs):
    if core.ratelimit.limit():
        def doFunction():
            kaithem.sound.play(*args, **kwargs)
            #kaithem.sound.wait()
        doSoundAction(doFunction)


def stopSound(*args, **kwargs):
    if core.ratelimit.limit():
        def doFunction():
            kaithem.sound.stop(*args, **kwargs)
        doSoundAction(doFunction)


def fadeSound(*args, **kwargs):
    if core.ratelimit.limit():
        def doFunction():
            kaithem.sound.fadeTo(*args, **kwargs)
        doSoundAction(doFunction)
    else:
        # A bit of a race condition here, if the sound had not started yet. But if we are triggering rate limit we
        # have other issues.
        kaithem.sound.stop(kwargs['handle'])


float = float
abs = abs
int = int
max = max
min = min

allowedCueNameSpecials = '_~.'


rootContext = kaithem.chandlerscript.ChandlerScriptContext()
fixtureslock = threading.RLock()
core.fixtures = {}


cueTransitionsLimitCount = 0
cueTransitionsHorizon = 0


def doTransitionRateLimit():
    global cueTransitionsHorizon, cueTransitionsLimitCount
    # This doesn't need locking. It can tolerate being approximate.
    if time.monotonic() > cueTransitionsHorizon - 0.3:
        cueTransitionsHorizon = time.monotonic()
        cueTransitionsLimitCount = 0

    # Limit to less than 2 per 100ms
    if cueTransitionsLimitCount > 6:
        raise RuntimeError(
            "Too many cue transitions extremely fast.  You may have a problem somewhere.")
    cueTransitionsLimitCount += 2


def refresh_scenes(t, v):
    """Stop and restart all active scenes, because some caches might need to be updated
        when a new universes is added
    """
    with core.lock:
        for i in core.activeScenes:
            # Attempt to restart all scenes.
            # Try to put them back in the same state
            # A lot of things are written assuming the list stays constant,
            # this is needed for refreshing.
            x = i.started
            y = i.enteredCue
            i.stop()
            i.go()
            i.render()
            i.started = x
            i.enteredCue = y


kaithem.message.subscribe("/chandler/command/refreshScenes", refresh_scenes)


def refreshFixtures(topic, val):
    # Deal with fixtures in this universe that aren't actually attached to this object yet.
    for i in range(0, 5):
        try:
            with fixtureslock:
                for i in core.fixtures:
                    f = core.fixtures[i]()
                    if not f:
                        continue
                    if f.universe == val or val is None:
                        f.assign(f.universe, f.startAddress)
        except RuntimeError:
            # Should there be some kind of dict changed size problem, retry
            time.sleep(0.1)


kaithem.message.subscribe("/chandler/command/refreshFixtures", refreshFixtures)


def mapUniverse(u):
    if not u.startswith("@"):
        return u

    u = u.split('[')[0]

    try:
        x = core.fixtures[u[1:]]()
        if not x:
            return None
    except KeyError:
        return None
    return x.universe


def mapChannel(u, c):
    index = 1

    if isinstance(c, str):
        if c.startswith("__"):
            return None
        # Handle the notation for repeating fixtures
        if '[' in c:
            c, index = c.split('[')
            index = int(index.split(']')[0].strip())

    if not u.startswith("@"):
        if isinstance(c, str):
            universe = getUniverse(u)
            if universe:
                c = universe.channelNames.get(c, None)
                if not c:
                    return None
                else:
                    return u, int(c)
        else:
            return u, int(c)

    try:
        f = core.fixtures[u[1:]]()
        if not f:
            return None

    except KeyError:
        return None
    x = f.assignment
    if not x:
        return

    # Index advance @fixture[5] means assume @fixture is the first of 5 identical fixtures and you want #5
    return x[0], int(x[1] + f.nameToOffset[c] + ((index - 1) * len(f.channels)))


def fnToCueName(fn):

    isNum = False
    try:
        int(fn.split(".")[0])
        isNum = True
    except Exception:
        print(traceback.format_exc())

    # Nicely Handle stuff of the form "84. trackname"
    if isNum and len(fn.split(".")) > 2:
        fn = fn.split(".", 1)[-1]

    fn = fn.split(".")[0]

    fn = fn.replace("-", "_")
    fn = fn.replace("_", " ")
    fn = fn.replace(":", " ")
    for i in r"""\~!@#$%^&*()+`-=[]\{}|;':"./,<>?""":
        if i not in allowedCueNameSpecials:
            fn = fn.replace(i, "")
    return fn


# when the last time we logged an error, so we can ratelimit
lastSysloggedError = 0


def rl_log_exc(m):
    print(m)
    global lastSysloggedError
    if lastSysloggedError < time.monotonic() - 5 * 60:
        logging.exception(m)
    lastSysloggedError = time.monotonic()


boardsListLock = threading.Lock()

core._activeScenes = []
core.activeScenes = []

# Index Cues by codes that we use to jump to them. This is a dict of lists of cues with that short code,
shortcut_codes = {}

core.runningTracks = weakref.WeakValueDictionary()

core.scenes = weakref.WeakValueDictionary()
core.scenes_by_name = weakref.WeakValueDictionary()



def codeCommand(code=""):
    "Activates any cues with the matching shortcut code in any scene"
    shortcutCode(code)
    return True


def gotoCommand(scene="=SCENE", cue=""):
    "Triggers a scene to go to a cue.  Ends handling of any further bindings on the current event"

    # Ignore empty
    if not cue.strip():
        return True

    # Track layers of recursion
    newcause = 'script.0'
    if kaithem.chandlerscript.contextInfo.event[0] in ('cue.enter', 'cue.exit'):
        cause = kaithem.chandlerscript.contextInfo.event[1][1]
        # Nast hack, but i don't thing we need more layers and parsing might be slower.
        if cause == 'script.0':
            newcause = 'script.1'

        elif cause == 'script.1':
            newcause = 'script.2'

        elif cause == 'script.2':
            raise RuntimeError(
                "More than 3 layers of redirects in cue.enter or cue.exit")

    # We don't want to handle other bindings after a goto, leaving a scene stops execution.
    core.scenes_by_name[scene].scriptContext.stopAfterThisHandler()
    core.scenes_by_name[scene].gotoCue(cue, cause=newcause)
    return True


gotoCommand.completionTags = {
    "scene": "gotoSceneNamesCompleter", "cue": "gotoSceneCuesCompleter"}


def setAlphaCommand(scene="=SCENE", alpha=1):
    "Set the alpha value of a scene"
    core.scenes_by_name[scene].setAlpha(float(alpha))
    return True


def ifCueCommand(scene, cue):
    "True if the scene is running that cue"
    return True if core.scenes_by_name[scene].active and core.scenes_by_name[scene].cue.name == cue else None


ifCueCommand.summaryTemplate = "True if cue is running"


def eventCommand(scene="=SCENE", ev="DummyEvent", value=""):
    "Send an event to a scene, or to all scenes if scene is __global__"
    if scene == "__global__":
        event(ev, value)
    else:
        core.scenes_by_name[scene].event(ev, value)
    return True


rootContext.commands['shortcut'] = codeCommand
rootContext.commands['goto'] = gotoCommand
rootContext.commands['setAlpha'] = setAlphaCommand
rootContext.commands['ifCue'] = ifCueCommand
rootContext.commands['sendEvent'] = eventCommand

rootContext.commands['setTag'].completionTags = {
    "tagName": 'tagPointsCompleter'}


def sendMqttMessage(topic, message):
    "JSON encodes message, and publishes it to the scene's MQTT server"
    raise RuntimeError(
        "This was supposed to be overridden by a scene specific version")


rootContext.commands['sendMQTT'] = sendMqttMessage


def listsoundfolder(path):
    " return format [ [subfolderfolder,displayname],[subfolder2,displayname]  ], [file,file2,etc]"
    soundfolders = core.getSoundFolders()

    if not path:
        return [[[i + ('/' if not i.endswith('/') else ''), soundfolders[i]] for i in soundfolders], []]

    if not path.endswith("/"):
        path = path + "/"
    # If it's not one of the sound folders return for security reasons
    match = False
    for i in soundfolders:
        if not i.endswith("/"):
            i = i + "/"
        if path.startswith(i):
            match = True
    if not match:
        return [[[i + ('/' if not i.endswith('/') else ''), soundfolders[i]] for i in soundfolders], []]

    # if not os.path.exists(path):
    #    return [[],[]]

    #x = os.listdir(path)
    x = kaithem.assetpacks.ls(path)

    return (
        sorted([[os.path.join(path, i), os.path.join(path, i)]
               for i in x if i.endswith("/")]),
        sorted([i for i in x if not i.endswith("/")])
    )


def searchPaths(s, paths):
    if not len(s) > 2:
        return []

    words = [i.strip() for i in s.lower().split(" ")]

    results = []
    paths = [i for i in paths]
    paths.append(core.musicLocation)

    for path in paths:
        if not path[-1] == "/":
            path = path + '/'

        for dir, dirs, files in os.walk(path):
            relpath = dir[len(path):]
            for i in files:
                match = True
                for j in words:
                    if not j in i.lower():
                        if not j in relpath.lower():
                            match = False
                if not match:
                    continue
                results.append((path, os.path.join(relpath, i)))
    return results


def getSerPorts():
    try:
        import serial.tools.list_ports
        if os.path.exists("/dev/serial/by-path"):
            return [os.path.join('/dev/serial/by-path', i) for i in os.listdir("/dev/serial/by-path")]
        else:
            return [i.device for i in serial.tools.list_ports.comports()]
    except Exception:
        return [str(traceback.format_exc())]


def disallow_special(s, allow='', replaceMode=None):
    for i in '[]{}()!@#$%^&*()<>,./;\':"-=_+\\|`~?\r\n\t':
        if i in s and i not in allow:
            if replaceMode is None:
                raise ValueError(
                    "Special char " + i + " not allowed in this context(full str starts with " + s[:100] + ")")
            else:
                s = s.replace(i, replaceMode)
    return s


def pollsounds():
    for i in core.activeScenes:
        # If the cuelen isn't 0 it means we are using the newer version that supports randomizing lengths.
        # We keep this in case we get a sound format we can'r read the length of in advance
        if i.cuelen == 0:
            # Forbid any crazy error loopy business with too short sounds
            if (time.time() - i.enteredCue) > 1 / 5:
                if i.cue.sound and i.cue.rel_length:
                    if not kaithem.sound.isPlaying(str(i.id)) and not i.sound_end:
                        i.sound_end = time.time()
                    if i.sound_end and (time.time() - i.sound_end > (i.cue.length * i.bpm)):
                        i.nextCue(cause='sound')


class ObjPlugin():
    pass


k_interface = ObjPlugin()
kaithem.chandler = k_interface

core.controlValues = weakref.WeakValueDictionary()


def number_to_shortcut(number):
    s = str((Decimal(number) / 1000).quantize(Decimal("0.001")))
    # https://stackoverflow.com/questions/11227620/drop-trailing-zeros-from-decimal
    s = s.rstrip('0').rstrip('.') if '.' in s else s
    return s


def getControlValue(cv, default=None):
    "Return numbers as is, or resolve values in the form of Universe:3 to the current value from that universe "
    if isinstance(cv, (float, int)):
        return cv
    else:
        try:
            cv = cv.split(":")
            x = cv[1].split("*")
            if len(x) > 1:
                multiplier = float(x[1])
            else:
                multiplier = 1.0
            u = getUniverse(cv[0])
            return u.values[int(x[0])] * multiplier
        except Exception:
            if not default is None:
                return default
            raise


core.fixtureschanged = {}


def getUniverse(u):
    "Get strong ref to universe if it exists, else get none."
    try:
        oldUniverseObj = universes.universes[u]()
    except KeyError:
        oldUniverseObj = None
    return oldUniverseObj


def getUniverses():
    "Returns dict of strong refs to universes, filtered to exclude weak refs"
    m = universes.universes
    u = {}
    for i in m:
        x = m[i]()
        if x:
            u[i] = x

    return u


def rerenderUniverse(i):
    universe = getUniverse(i)
    if universe:
        universe.full_rerender = True


def unpack_np_vals(v):
    "Given a set of dicts that might contain either lists or np arrays, convert to normal lists of numbers"
    return {j: [float(k) for k in v[j]] for j in v}


class Fixture():
    def __init__(self, name, data=None):
        """Represents a contiguous range of channels each with a defined role in one universe.

            data is the definition of the type of fixture. It can be a list of channels, or
            a dict having a 'channels' property.

            Each channel must be described by a [name, type, [arguments]] list, where type is one of:

            red
            green
            blue
            value
            dim
            custom
            fine
            fog
            hue

            The name must be unique per-fixture.
            If a channel has the type "fine" it will be interpreted as the fine value of
            the immediately preceding coarse channel, and should automatically get its value from the fractional part.
            If the coarse channel is not the immediate preceding channel, use the first argument to specify the number of the coarse channel,
            with 0 being the fixture's first channel.        
        """
        if data:
            # Normalize and raise errors on nonsense
            channels = json.loads(json.dumps(data))

            if not isinstance(channels, list):
                channels = channels['channels']
            self.channels = channels

        else:
            channels = []

        self.channels = channels
        self.universe = None
        self.startAddress = 0
        self.assignment = None
        disallow_special(name, ".")

        self.nameToOffset = {}

        # Used for looking up channel by name
        for i in range(len(channels)):
            self.nameToOffset[channels[i][0]] = i

        with fixtureslock:
            if name in core.fixtures:
                raise ValueError("Name in Use")
            else:
                core.fixtures[name] = weakref.ref(self)
                self.name = name

    def getChannelByName(self, name):
        if self.startAddress:
            return self

    def __del__(self):
        with fixtureslock:
            del core.fixtures[self.name]

        ID = id(self)

        def f():
            try:
                if id(core.fixtures[self.name]()) == id(ID):
                    self.assign(None, None)
                    self.rm()
            except Exception:
                print(traceback.format_exc())
        kaithem.misc.do(f)

    def rm(self):
        try:
            del core.fixtures[self.name]
        except Exception:
            print(traceback.format_exc())

    def assign(self, universe, channel):
        with core.lock:
            # First just clear the old assignment, if any
            if self.universe and self.startAddress:
                oldUniverseObj = getUniverse(self.universe)

                if oldUniverseObj:
                    # Delete current assignments
                    for i in range(self.startAddress, self.startAddress + len(self.channels)):
                        if i in oldUniverseObj.channels:
                            if oldUniverseObj.channels[i]() and oldUniverseObj.channels[i]() is self:
                                del oldUniverseObj.channels[i]
                                # We just unassigned it, so it's not a hue channel anymore
                                oldUniverseObj.hueBlendMask[i] = 0
                            else:
                                print("Unexpected channel data corruption",
                                      universe, i, oldUniverseObj.channels[i]())

            self.assignment = universe, channel

            self.universe = universe
            self.startAddress = channel

            universeObj = getUniverse(universe)

            if not universeObj:
                return

            core.fixtureschanged = {}

            universeObj.channelsChanged()

            if not channel:
                return
            # 2 separate loops, first is just to check, so that we don't have half-completed stuff
            for i in range(channel, channel + len(self.channels)):
                if i in universeObj.channels:
                    if universeObj.channels[i] and universeObj.channels[i]():
                        if not self.name == universeObj.channels[i]().name:
                            raise ValueError("channel " + str(i) + " of " + self.name +
                                             " would overlap with " + universeObj.channels[i]().name)

            cPointer = 0
            for i in range(channel, channel + len(self.channels)):
                universeObj.channels[i] = weakref.ref(self)
                if self.channels[cPointer][1] in ('hue', 'sat', 'custom'):
                    # Mark it as a hue channel that blends slightly differently
                    universeObj.hueBlendMask[i] = 1
                    cPointer += 1


core.Fixture = Fixture


def fixturesFromOldListStyle(l):
    "Convert fixtures from the older list of tuples style to the new dict style"
    return {i[0]: {'name': i[0], 'type': i[1], 'universe': i[2], 'addr': i[3]} for i in l if len(i) == 4}


class DebugScriptContext(kaithem.chandlerscript.ChandlerScriptContext):
    def onVarSet(self, k, v):
        try:
            if not k == "_" and self.sceneObj().rerenderOnVarChange:
                self.sceneObj().recalcCueVals()
                self.sceneObj().rerender = True

        except Exception:
            rl_log_exc("Error handling var set notification")
            print(traceback.format_exc())

        try:
            if not k.startswith("_"):
                for i in core.boards:
                    if isinstance(v, (str, int, float, bool)):
                        i().link.send(['varchange', self.scene, k, v])
                    elif isinstance(v, collections.defaultdict):
                        v = json.dumps(v)[:160]
                        i().link.send(['varchange', self.scene, k, v])
                    else:
                        v = str(v)[:160]
                        i().link.send(['varchange', self.scene, k, v])
        except Exception:
            rl_log_exc("Error handling var set notification")
            print(traceback.format_exc())

    def event(self, e, v=None):
        kaithem.chandlerscript.ChandlerScriptContext.event(self, e, v)
        try:
            for i in core.boards:
                i().pushEv(e, self.sceneName, time.time(), value=v)
        except Exception:
            rl_log_exc("error handling event")
            print(traceback.format_exc())

    def onTimerChange(self, timer, run):
        self.sceneObj().runningTimers[timer] = run
        try:
            for i in core.boards:
                i().link.send(['scenetimers', self.scene,
                               self.sceneObj().runningTimers])
        except Exception:
            rl_log_exc("Error handling timer set notification")
            print(traceback.format_exc())

    def canGetTagpoint(self, t):
        if not t in self.tagpoints and len(self.tagpoints) > 128:
            raise RuntimeError("Too many tagpoints in one scene")
        return t


def checkPermissionsForSceneData(data, user):
    """Check if used can upload or edit the scene, ekse raise an error if it uses advanced features that would prevent that action.
        We disallow delete because we don't want unprivelaged users to delete something important that they can't fix.

    """
    if 'page' in data and (data['page']['html'].strip() or data['page']['js'].strip() or data['page'].get('rawhtml', '').strip()):
        if not kaithem.users.checkPermission(user, "/admin/modules.edit"):
            raise ValueError(
                "You cannot do this action on this scene without /admin/modules.edit, because it uses advanced features: pages. User:" + str(kaithem.web.user()))
    if 'mqttServer' in data and data['mqttServer'].strip():
        if not kaithem.users.checkPermission(user, "/admin/modules.edit"):
            raise ValueError(
                "You cannot do this action on this scene without /admin/modules.edit, because it uses advanced features: MQTT:" + str(kaithem.web.user()))


class ChandlerConsole():
    "Represents a web GUI board. Pretty much the whole GUI app is part of this class"

    def loadProject(self):

        for i in self.scenememory:
            self.scenememory[i].stop()
            self.scenememory[i].close()
        self.scenememory = {}

        for i in self.configuredUniverses:
            self.configuredUniverses[i].close()

        self.configuredUniverses = {}
        self.fixtureClasses = {}
        self.fixtureAssignments = {}

        saveLocation = os.path.join(
            kaithem.misc.vardir, "chandler", "universes")
        if os.path.isdir(saveLocation):
            for i in os.listdir(saveLocation):
                fn = os.path.join(saveLocation, i)
                if os.path.isfile(fn) and fn.endswith(".yaml"):
                    self.configuredUniverses[i[:-
                                               len('.yaml')]] = kaithem.persist.load(fn)

        saveLocation = os.path.join(
            kaithem.misc.vardir, "chandler", "fixturetypes")
        if os.path.isdir(saveLocation):
            for i in os.listdir(saveLocation):
                fn = os.path.join(saveLocation, i)
                if os.path.isfile(fn) and fn.endswith(".yaml"):
                    self.fixtureClasses[i[:-len('.yaml')]
                                        ] = kaithem.persist.load(fn)

        saveLocation = os.path.join(
            kaithem.misc.vardir, "chandler", "fixtures")
        if os.path.isdir(saveLocation):
            for i in os.listdir(saveLocation):
                fn = os.path.join(saveLocation, i)
                if os.path.isfile(fn) and fn.endswith(".yaml"):
                    self.fixtureAssignments[i[:-
                                              len('.yaml')]] = kaithem.persist.load(fn)

        # This used to be a list of [name, fixturetype, startAddress] triples
        if not isinstance(self.fixtureAssignments, dict):
            self.fixtureAssignments = fixturesFromOldListStyle(
                self.fixtureAssignments)
        try:
            self.createUniverses(self.configuredUniverses)
        except Exception:
            logger.exception("Error creating universes")
            print(traceback.format_exc(6))

        d = {}

        saveLocation = os.path.join(kaithem.misc.vardir, "chandler", "scenes")
        if os.path.isdir(saveLocation):
            for i in os.listdir(saveLocation):
                fn = os.path.join(saveLocation, i)

                if os.path.isfile(fn) and fn.endswith(".yaml"):
                    d[i[:-len('.yaml')]] = kaithem.persist.load(fn)

        self.loadDict(d)

        if self.link:
            self.link.send(['refreshPage', self.fixtureAssignments])

    def __init__(self, count=65536):

        self.newDataFunctions = []

        self.id = uuid.uuid4().hex
        self.link = kaithem.widget.APIWidget("api_link")
        self.link.require("users.chandler.admin")
        self.link.echo = False
        # mutable and immutable versions of the active scenes list.
        self._activeScenes = []
        self.activeScenes = []

        # This light board's scene memory, or the set of scenes 'owned' by this board.
        self.scenememory = {}

        self.ext_scenes = {}

        self.count = count
        # Bound method weakref nonsense prevention
        self.onmsg = lambda x, y: self._onmsg(x, y)
        self.link.attach(self.onmsg)
        self.lock = threading.RLock()

        self.configuredUniverses = {}
        self.fixtureAssignments = {}
        self.fixtures = {}

        self.universeObjs = {}
        self.fixtureClasses = copy.deepcopy(fixtureslib.genericFixtureClasses)

        self.loadProject()

        self.refreshFixtures()

        def f(self, *dummy):
            self.link.send(
                ['soundoutputs', [i for i in kaithem.sound.outputs()]])

        self.callback_jackports = f
        kaithem.message.subscribe("/system/jack/newport/", f)
        kaithem.message.subscribe("/system/jack/delport/", f)

        # Use only for stuff in background threads, to avoid pileups that clog the
        # Whole worker pool
        self.guiSendLock = threading.Lock()

        # For logging ratelimiting
        self.lastLoggedGuiSendError = 0

    def refreshFixtures(self):
        with core.lock:
            self.ferrs = ''
            try:
                for i in self.fixtures:
                    self.fixtures[i].assign(None, None)
                    self.fixtures[i].rm()
            except Exception:
                self.ferrs += 'Error deleting old assignments:\n' + traceback.format_exc()
                print(traceback.format_exc())

            try:
                del i
            except Exception:
                pass

            self.fixtures = {}

            for i in self.fixtureAssignments.values():
                try:
                    x = Fixture(i['name'], self.fixtureClasses[i['type']])
                    self.fixtures[i['name']] = x
                    self.fixtures[i['name']].assign(
                        i['universe'], int(i['addr']))
                    core.fixtures[i['name']] = weakref.ref(x)
                except Exception:
                    logger.exception("Error setting up fixture")
                    print(traceback.format_exc())
                    self.ferrs += str(i) + '\n' + traceback.format_exc()

            for u in universes.universes:
                self.pushChannelNames(u)

            with fixtureslock:
                for f in core.fixtures:
                    if f:
                        self.pushChannelNames("@" + f)

            self.ferrs = self.ferrs or 'No Errors!'
            self.pushfixtures()

    def createUniverses(self, data):
        for i in self.universeObjs:
            self.universeObjs[i].close()

        self.universeObjs = {}
        import gc
        gc.collect()
        l = {}
        u = data
        for i in u:
            if u[i]['type'] == 'enttecopen' or u[i]['type'] == 'rawdmx':
                l[i] = core.EnttecOpenUniverse(i, channels=int(u[i].get('channels', 128)), portname=u[i].get(
                    'interface', None), framerate=float(u[i].get('framerate', 44)))
            elif u[i]['type'] == 'enttec':
                l[i] = core.EnttecUniverse(i, channels=int(u[i].get('channels', 128)), portname=u[i].get(
                    'interface', None), framerate=float(u[i].get('framerate', 44)))
            elif u[i]['type'] == 'artnet':
                l[i] = core.ArtNetUniverse(i, channels=int(u[i].get('channels', 128)), address=u[i].get(
                    'interface', "255.255.255.255:6454"), framerate=float(u[i].get('framerate', 44)), number=int(u[i].get('number', 0)))
            elif u[i]['type'] == 'tagpoints':
                l[i] = core.TagpointUniverse(i, channels=int(u[i].get('channels', 128)), tagpoints=u[i].get(
                    'channelConfig', {}), framerate=float(u[i].get('framerate', 44)), number=int(u[i].get('number', 0)))
            else:
                event("system.error", "No universe type: " + u[i]['type'])
        self.universeObjs = l

        try:
            core.discoverColorTagDevices()
        except Exception:
            event("system.error", traceback.format_exc())
            print(traceback.format_exc())

        self.pushUniverses()

    def loadShow(self, showName):
        saveLocation = os.path.join(
            kaithem.misc.vardir, "chandler", "shows", showName)
        d = {}
        if os.path.isdir(saveLocation):
            for i in os.listdir(saveLocation):
                fn = os.path.join(saveLocation, i)

                if os.path.isfile(fn) and fn.endswith(".yaml"):
                    d[i[:-len('.yaml')]] = kaithem.persist.load(fn)

        self.loadDict(d)
        self.refreshFixtures()

    def loadSetup(self, setupName):
        saveLocation = os.path.join(
            kaithem.misc.vardir, "chandler", "setups", setupName, "universes")
        if os.path.isdir(saveLocation):
            for i in os.listdir(saveLocation):
                fn = os.path.join(saveLocation, i)
                if os.path.isfile(fn) and fn.endswith(".yaml"):
                    self.configuredUniverses[i[:-
                                               len('.yaml')]] = kaithem.persist.load(fn)

        self.universeObjs = {}
        self.fixtureAssignments = {}
        self.fixtures = {}

        self.fixtureAssignments = {}

        saveLocation = os.path.join(
            kaithem.misc.vardir, "chandler", "setups", setupName, "fixtures")
        if os.path.isdir(saveLocation):
            for i in os.listdir(saveLocation):
                fn = os.path.join(saveLocation, i)
                if os.path.isfile(fn) and fn.endswith(".yaml"):
                    self.fixtureAssignments[i[:-
                                              len('.yaml')]] = kaithem.persist.load(fn)

        self.refreshFixtures()
        self.createUniverses(self.configuredUniverses)

    def loadSetupFile(self, data, _asuser=False, filename=None, errs=False):

        if not kaithem.users.checkPermission(kaithem.web.user(), "/admin/modules.edit"):
            raise ValueError(
                "You cannot change the setup without /admin/modules.edit")
        data = yaml.load(data)

        if 'fixtureTypes' in data:
            self.fixtureClasses.update(data['fixtureTypes'])

        if 'universes' in data:
            self.configuredUniverses = data['universes']
            self.createUniverses(self.configuredUniverses)

        if 'fixtures' in data:
            self.fixtureAssignments = data['fixtures']
            self.refreshFixtures()

    def getSetupFile(self):
        with core.lock:
            return ({

                "fixtureTypes": self.fixtureClasses,
                "universes": self.configuredUniverses,
                "fixures": self.fixtureAssignments
            })

    def loadLibraryFile(self, data, _asuser=False, filename=None, errs=False):
        data = yaml.load(data)

        if 'fixtureTypes' in data:
            self.fixtureClasses.update(data['fixtureTypes'])
        else:
            raise ValueError("No fixture types in that file")

    def getLibraryFile(self):
        with core.lock:
            return ({
                "fixtureTypes": self.fixtureClasses,
                "universes": self.configuredUniverses,
                "fixures": self.fixtureAssignments
            })

    def loadSceneFile(self, data, _asuser=False, filename=None, errs=False):

        data = yaml.load(data)

        # Detect if the user is trying to upload a single scenefile, if so, wrap it in a multi-dict of scenes to keep the reading code
        # The same for both
        if 'uuid' in data and isinstance(data['uuid'], str):
            # Remove the .yaml
            data = {filename[:-5]: data}
        for i in data:
            checkPermissionsForSceneData(data, kaithem.web.user())

        with core.lock:
            for i in self.scenememory:
                checkPermissionsForSceneData(
                    self.scenememory[i].toDict(), kaithem.web.user())

            self.loadDict(data, errs)

    def loadDict(self, data, errs=False):
        with core.lock:
            for i in data:

                # New versions don't have a name key at all, the name is the key
                if 'name' in data[i]:
                    pass
                else:
                    data[i]['name'] = i
                n = data[i]['name']

                # Delete existing scenes we own
                if n in core.scenes_by_name:
                    if core.scenes_by_name[n].id in self.scenememory:
                        self.scenememory[core.scenes_by_name[n].id].stop()
                        del self.scenememory[core.scenes_by_name[n].id]
                        del core.scenes_by_name[n]
                    else:
                        raise ValueError(
                            "Scene " + i + " already exists. We cannot overwrite, because it was not created through this board")
                try:
                    # Kinda brittle and hacky, because loadinga new default scene isn't well
                    # supported
                    cues = data[i]['cues']
                    del data[i]['cues']
                    x = False
                    if 'defaultActive' in data[i]:
                        x = data[i]['defaultActive']
                        del data[i]['defaultActive']
                    if 'active' in data[i]:
                        x = data[i]['active']
                        del data[i]['active']

                    # Older versions indexed by UUID
                    if 'uuid' in data[i]:
                        uuid = data[i]['uuid']
                        del data[i]['uuid']
                    else:
                        uuid = i

                    s = Scene(id=uuid, defaultCue=False,
                              defaultActive=x, **data[i])
                    for j in cues:
                        Cue(s, f=True, name=j, **cues[j])
                    s.cue = s.cues['default']
                    # s.gotoCue("default")

                    self.scenememory[uuid] = s
                    if x:
                        s.go()
                        s.rerender = True
                except Exception:
                    if not errs:
                        logger.exception(
                            "Failed to load scene " + str(i) + " " + str(data[i].get('name', '')))
                        print("Failed to load scene " + str(i) + " " +
                              str(data[i].get('name', '')) + ": " + traceback.format_exc(3))
                    else:
                        raise

    def addScene(self, scene):
        if not isinstance(scene, Scene):
            raise ValueError("Arg must be a Scene")
        self.scenememory[scene.id] = scene

    def rmScene(self, scene):
        try:
            del self.scenememory[scene.id]
        except Exception:
            print(traceback.format_exc())

    def pushEv(self, event, target, t=None, value=None, info=""):

        # TODO: Do we want a better way of handling this? We don't want to clog up the semi-re
        def f():
            if self.guiSendLock.acquire(timeout=5):
                try:
                    self.link.send(
                        ['event', [event, target, kaithem.time.strftime(t or time.time()), value, info]])
                except Exception:
                    if time.monotonic() - self.lastLoggedGuiSendError < 60:
                        logger.exception(
                            "Error when reporting event. (Log ratelimit: 30)")
                        self.lastLoggedGuiSendError = time.monotonic()
                finally:
                    self.guiSendLock.release()
            else:
                if time.monotonic() - self.lastLoggedGuiSendError < 60:
                    logger.error(
                        "Timeout getting lock to push event. (Log ratelimit: 60)")
                    self.lastLoggedGuiSendError = time.monotonic()

        kaithem.misc.do(f)

    def pushfixtures(self):
        "Errors in fixture list"
        self.link.send(["ferrs", self.ferrs])
        try:
            self.link.send(['fixtures', {i: [core.fixtures[i]().universe, core.fixtures[i](
            ).startAddress, core.fixtures[i]().channels] for i in core.fixtures}])
        except Exception:
            print(traceback.format_exc())

    def pushUniverses(self):
        snapshot = getUniverses()

        self.link.send(["universes", {i: {'count': len(snapshot[i].values),
                                          'status':snapshot[i].status,
                                          'ok':snapshot[i].ok, "telemetry":snapshot[i].telemetry} for i in snapshot}])

    def getScenes(self):
        "Return serializable version of scenes list"
        with core.lock:
            sd = {}
            for i in self.scenememory:
                x = self.scenememory[i]
                sd[x.name] = x.toDict()

            return sd

    def saveAsFiles(self, dirname, data, legacyKey=None):
        sd = data
        saveLocation = os.path.join(kaithem.misc.vardir, "chandler", dirname)
        if not os.path.exists(saveLocation):
            os.makedirs(saveLocation, mode=0o755)

        saved = {}
        # Lock used to prevent conflict, saving over each other with nonsense data.
        with core.lock:
            for i in sd:
                saved[i + ".yaml"] = True
                kaithem.persist.save(
                    sd[i], os.path.join(saveLocation, i + ".yaml"))

        # Delete everything not in folder
        for i in os.listdir(saveLocation):
            fn = os.path.join(saveLocation, i)
            if os.path.isfile(fn) and i.endswith(".yaml"):
                if i not in saved:
                    os.remove(fn)

    def pushTracks(self):
        self.link.send(
            ['tracks', {i: core.runningTracks[i].name for i in core.runningTracks}])

    def pushChannelNames(self, u):
        "This has expanded to push more data than names"
        if not u[0] == '@':

            uobj = getUniverse(u)

            if not uobj:
                return

            d = {}
            for i in uobj.channels:
                fixture = uobj.channels[i]()
                if not fixture:
                    return

                if not fixture.startAddress:
                    return
                data = [fixture.name] + \
                    fixture.channels[i - fixture.startAddress]
                d[i] = data
            self.link.send(['cnames', u, d])
        else:
            d = {}
            if u[1:] in core.fixtures:
                f = core.fixtures[u[1:]]()
                for i in range(0, len(f.channels)):
                    d[f.channels[i][0]] = [u[1:]] + f.channels[i]
            self.link.send(['cnames', u, d])

    def pushMeta(self, sceneid, statusOnly=False, keys=None):
        "Statusonly=only the stuff relevant to a cue change. Keys is iterabe of what to send, or None for all"
        scene = core.scenes[sceneid]

        v = {}
        if scene.scriptContext:
            try:
                for j in scene.scriptContext.variables:
                    if not j == "_":
                        if isinstance(scene.scriptContext.variables[j], (int, float, str, bool)):
                            v[j] = scene.scriptContext.variables[j]
                        else:
                            v[j] = '__PYTHONDATA__'
            except Exception:
                print(traceback.format_exc())

        if not statusOnly:
            data = {
                'ext': not sceneid in self.scenememory,
                'dalpha': scene.defaultalpha,
                'alpha': scene.alpha,
                'active': scene.isActive(),
                'defaultActive': scene.defaultActive,
                'name': scene.name,
                'bpm': round(scene.bpm, 6),
                'blend': scene.blend,
                'blendArgs': scene.blendArgs,
                'blendDesc': core.getblenddesc(scene.blend),
                'blendParams': scene.blendClass.parameters if hasattr(scene.blendClass, "parameters") else {},
                'priority': scene.priority,
                'started': scene.started,
                'enteredCue': scene.enteredCue,
                'backtrack': scene.backtrack,
                'cue': scene.cue.id if scene.cue else scene.cues['default'].id,
                'cuelen': scene.cuelen,
                'midiSource': scene.midiSource,
                'defaultNext': scene.defaultNext,
                'commandTag': scene.commandTag,
                'soundOutput': scene.soundOutput,
                'slideOverlayURL': scene.slideOverlayURL,
                'eventButtons': scene.eventButtons,
                'infoDisplay': scene.infoDisplay,
                'utility': scene.utility,
                'displayTags': scene.displayTags,
                'displayTagValues': scene.displayTagValues,
                'displayTagMeta': scene.displayTagMeta,
                'vars': v,
                'timers': scene.runningTimers,
                'notes': scene.notes,
                "mqttServer": scene.mqttServer,
                'crossfade': scene.crossfade,
                'status': scene.getStatusString()
            }
        else:
            data = {
                'alpha': scene.alpha,
                'active': scene.isActive(),
                'defaultActive': scene.defaultActive,
                'displayTagValues': scene.displayTagValues,
                'enteredCue': scene.enteredCue,
                'cue': scene.cue.id if scene.cue else scene.cues['default'].id,
                'cuelen': scene.cuelen,
                'status': scene.getStatusString()
            }
        if keys:
            for i in keys:
                if i not in data:
                    raise KeyError(i)
        self.link.send(["scenemeta", sceneid, {
                       i: data[i] for i in data if (not keys or (i in keys))}])

    def pushCueMeta(self, cueid):
        try:
            cue = cues[cueid]
            self.link.send(["cuemeta", cueid,
                            {
                                'fadein': cue.fadein,
                                'alpha': cue.alpha,
                                'length': cue.length,
                                'lengthRandomize': cue.lengthRandomize,
                                'next': cue.nextCue if cue.nextCue else '',
                                'name': cue.name,
                                'id': cueid,
                                'sound': cue.sound,
                                'slide': cue.slide,
                                'soundOutput': cue.soundOutput,
                                'soundStartPosition': cue.soundStartPosition,
                                'mediaSpeed': cue.mediaSpeed,
                                'mediaWindup': cue.mediaWindup,
                                'mediaWinddown': cue.mediaWinddown,
                                'rel_len': cue.rel_length,
                                'track': cue.track,
                                'notes': cue.notes,
                                'scene': cue.scene().id,
                                'shortcut': cue.shortcut,
                                'number': cue.number / 1000.0,
                                'defaultNext': cue.scene().getAfter(cue.name),
                                'prev': cue.scene().getParent(cue.name),
                                'probability': cue.probability,
                                'rules': cue.rules,
                                'reentrant': cue.reentrant,
                                'inheritRules': cue.inheritRules,
                                "soundFadeOut": cue.soundFadeOut,
                                "soundFadeIn": cue.soundFadeIn,
                                'soundVolume': cue.soundVolume,
                                'soundLoops': cue.soundLoops

                            }])
        except Exception:
            rl_log_exc("Error pushing cue data")
            print("cue data push error", cueid, traceback.format_exc())

    def pushCueMetaAttr(self, cueid, attr):
        "Be careful with this, some attributes can't be sent directly and need preprocessing"
        try:
            cue = cues[cueid]
            self.link.send(["cuemetaattr", cueid,
                            {attr: getattr(cue, attr)}])
        except Exception:
            rl_log_exc("Error pushing cue data")
            print("cue data push error", cueid, traceback.format_exc())

    def pushCueData(self, cueid):
        self.link.send(["cuedata", cues[cueid].id, cues[cueid].values])

    def pushConfiguredUniverses(self):
        self.link.send(["confuniverses", self.configuredUniverses])

    def pushCueList(self, scene):
        s = core.scenes[scene]
        x = list(s.cues.keys())
        # split list into messages of 100 because we don't want to exceed the widget send limit
        while x:
            self.link.send(["scenecues", scene, {
                           i: (s.cues[i].id, s.cues[i].number / 1000.0) for i in x[:100]}])
            x = x[100:]

    def _onmsg(self, user, msg):
        # Adds a light to a scene
        try:

            if msg[0] == "saveScenes":
                self.saveAsFiles('scenes', self.getScenes(), "lighting/scenes")

            if msg[0] == "saveShow":
                self.saveAsFiles(os.path.join(
                    'shows', msg[1], 'scenes', self.getScenes()))

            if msg[0] == "loadShow":
                self.loadShow(msg[1])

            if msg[0] == "saveSetup":
                self.saveAsFiles(
                    'fixturetypes', self.fixtureClasses, "lighting/fixtureclasses")
                self.saveAsFiles(
                    'universes', self.configuredUniverses, "lighting/universes")
                self.saveAsFiles(
                    'fixtures', self.fixtureAssignments, "lighting/fixtures")

                saveLocation = os.path.join(kaithem.misc.vardir, "chandler")
                if not os.path.exists(saveLocation):
                    os.makedirs(saveLocation, mode=0o755)

                kaithem.persist.save(core.config, os.path.join(
                    saveLocation, "config.yaml"))

            if msg[0] == "saveSetupPreset":
                self.saveAsFiles('fixturetypes', self.fixtureClasses,
                                 "lighting/fixtureclasses", noRm=True)
                self.saveAsFiles(os.path.join(
                    'setups', msg[1], 'universes'), self.configuredUniverses)
                self.saveAsFiles(os.path.join(
                    'setups', msg[1], 'fixtures'), self.fixtureAssignments)

            if msg[0] == "saveLibrary":
                self.saveAsFiles(
                    'fixturetypes', self.fixtureClasses, "lighting/fixtureclasses")

            if msg[0] == "addscene":
                s = Scene(msg[1].strip())
                self.scenememory[s.id] = s
                self.link.send(["newscene", msg[1].strip(), s.id])
                self.pushMeta(s.id)

            if msg[0] == "addmonitor":
                s = Scene(msg[1].strip(), blend="monitor",
                          priority=100, active=True)
                self.scenememory[s.id] = s
                self.link.send(["newscene", msg[1].strip(), s.id])

            if msg[0] == "getserports":
                self.link.send(["serports", getSerPorts()])

            if msg[0] == "getCommands":
                c = rootContext.commands.scriptcommands
                l = {}
                for i in c:
                    f = c[i]
                    l[i] = kaithem.chandlerscript.getFunctionInfo(f)
                self.link.send(["commands", l])

            if msg[0] == "getconfuniverses":
                self.pushConfiguredUniverses()

            if msg[0] == "setconfuniverses":
                if kaithem.users.checkPermission(user, "/admin/settings.edit"):
                    self.configuredUniverses = msg[1]
                    self.createUniverses(self.configuredUniverses)
                else:
                    raise RuntimeError("User does not have permission")

            if msg[0] == "setfixtureclass":
                l = []
                for i in msg[2]:
                    if i[1] not in ['custom', 'fine', 'fixed']:
                        l.append(i[:2])
                    else:
                        l.append(i)
                self.fixtureClasses[msg[1]] = l
                self.refreshFixtures()

            if msg[0] == "setfixtureclassopz":
                x = []

                for i in msg[2]['channels']:
                    if i in ('red', 'green', 'blue', 'intensity', "white", "fog"):
                        x.append([i, i])

                    elif i.isnumeric:
                        x.append(['fixed', 'fixed', i])

                    elif i == 'color':
                        x.append(['hue', 'hue'])

                l = []
                for i in x:
                    if i[1] not in ['custom', 'fine', 'fixed']:
                        l.append(i[:2])
                    else:
                        l.append(i)
                self.fixtureClasses[msg[1].replace(
                    "-", " ").replace("/", " ")] = l
                self.refreshFixtures()

            if msg[0] == "rmfixtureclass":
                del self.fixtureClasses[msg[1]]
                self.refreshFixtures()

            if msg[0] == "setFixtureAssignment":
                self.fixtureAssignments[msg[1]] = msg[2]
                self.link.send(['fixtureAssignments', self.fixtureAssignments])
                self.refreshFixtures()

            if msg[0] == "getcuehistory":
                self.link.send(
                    ['cuehistory', msg[1], core.scenes[msg[1]].cueHistory])

            if msg[0] == "rmFixtureAssignment":
                del self.fixtureAssignments[msg[1]]

                self.link.send(['fixtureAssignments', self.fixtureAssignments])
                self.link.send(['fixtureAssignments', self.fixtureAssignments])

                self.refreshFixtures()

            if msg[0] == "getfixtureassg":
                self.link.send(['fixtureAssignments', self.fixtureAssignments])
                self.pushfixtures()

            if msg[0] == "clonecue":
                cues[msg[1]].clone(msg[2])

            if msg[0] == "jumptocue":
                if not cues[msg[1]].scene().active:
                    cues[msg[1]].scene().go()

                cues[msg[1]].scene().gotoCue(cues[msg[1]].name, cause='manual')

            if msg[0] == "jumpbyname":
                core.scenes_by_name[msg[1]].gotoCue(msg[2], cause='manual')

            if msg[0] == "nextcue":
                core.scenes[msg[1]].nextCue(cause='manual')

            if msg[0] == "prevcue":
                core.scenes[msg[1]].nextCue(cause='manual')

            if msg[0] == "nextcuebyname":
                core.scenes_by_name[msg[1]].nextCue(cause='manual')

            if msg[0] == "shortcut":
                shortcutCode(msg[1])

            if msg[0] == "event":
                event(msg[1], msg[2])

            if msg[0] == "setshortcut":
                cues[msg[1]].setShortcut(msg[2][:128])
            if msg[0] == "setnumber":
                cues[msg[1]].setNumber(msg[2])

            if msg[0] == "setrellen":
                cues[msg[1]].rel_length = msg[2]
                self.pushCueMeta(msg[1])

            if msg[0] == "setsoundout":
                cues[msg[1]].soundOutput = msg[2]
                self.pushCueMeta(msg[1])

            if msg[0] == "setNotes":
                core.scenes[msg[1]].notes = msg[2]
                self.pushMeta(msg[1], keys={'notes'})

            if msg[0] == "seteventbuttons":
                core.scenes[msg[1]].eventButtons = msg[2]
                self.pushMeta(msg[1], keys={'eventButtons'})

            if msg[0] == "setinfodisplay":
                core.scenes[msg[1]].infoDisplay = msg[2]
                self.pushMeta(msg[1], keys={'infoDisplay'})

            if msg[0] == "setutility":
                core.scenes[msg[1]].utility = msg[2]
                self.pushMeta(msg[1], keys={'utility'})

            if msg[0] == "setdisplaytags":
                core.scenes[msg[1]].setDisplayTags(msg[2])
                self.pushMeta(msg[1], keys={'displayTags'})

            if msg[0] == "setMqttServer":
                if kaithem.users.checkPermission(user, "/admin/modules.edit"):
                    core.scenes[msg[1]].setMqttServer(msg[2])
                    self.pushMeta(msg[1], keys={'mqttServer'})

            if msg[0] == "clonescene":
                s = Scene(msg[2])
                self.scenememory[s.id] = s
                s0 = core.scenes[msg[1]]
                s.fadein = s0.fadein
                s.length = s0.length
                s.defaultalpha = s0.defaultalpha
                s.alpha = s0.alpha
                s.track = s0.track
                s.setBlend(s0.blend)
                s.blendArgs = s0.blendArgs.copy()

                self.link.send(["newscene", msg[1], s.id])

            if msg[0] == "getcnames":
                self.pushChannelNames(msg[1])

            if msg[0] == "namechannel":
                if msg[3]:
                    universes.universes[msg[1]]().channels[msg[2]] = msg[3]
                else:
                    del universes.universes[msg[1]]().channels[msg[2]]

            if msg[0] == "addcueval":
                if hasattr(cues[msg[1]].scene().blendClass, 'default_channel_value'):
                    val = cues[msg[1]].scene().blendClass.default_channel_value
                else:
                    val = 0
                # Allow number:name format, but we only want the name
                cues[msg[1]].setValue(msg[2], str(msg[3]).split(":")[-1], val)

            if msg[0] == "setcuevaldata":

                # Verify correct data
                for i in msg[2]:
                    for j in msg[2][i]:
                        float(msg[2][i][j])

                cues[msg[1]].clearValues()

                for i in msg[2]:
                    for j in msg[2][i]:
                        try:
                            ch = int(j)
                        except Exception:
                            ch = j
                        # Hack. because JSON and yaml are giving us strings
                        cues[msg[1]].setValue(i, j, msg[2][i][j])

            if msg[0] == "addcuef":
                cue = cues[msg[1]]

                # Can add a length and start point to the cue.
                #index = int(msg[3])
                length = int(msg[4])
                spacing = int(msg[5])

                # Get rid of any index part, treat it like it's part of the same fixture.
                x = core.fixtures[msg[2].split('[')[0]]()
                # Add every non-unused channel.  Fixtures
                # Are stored as if they are their own universe, starting with an @ sign.
                # Channels are stored by name and not by number.
                for i in x.channels:
                    if not i[1] in ("unused", "fixed"):
                        if hasattr(cue.scene().blendClass, 'default_channel_value'):
                            val = cue.scene().blendClass.default_channel_value
                        else:
                            val = 0
                        # i[0] is the name of the channel
                        cue.setValue("@" + msg[2], i[0], val)

                if length > 1:
                    # Set the length as if it were a ficture property
                    cue.setValue("@" + msg[2], "__length__", length)
                    cue.setValue("@" + msg[2], "__spacing__", spacing)

                    # The __dest__ channels represet the color at the end of the channel
                    for i in x.channels:
                        if not i[1] in ("unused", "fixed"):
                            if hasattr(cue.scene().blendClass, 'default_channel_value'):
                                val = cue.scene().blendClass.default_channel_value
                            else:
                                val = 0
                            # i[0] is the name of the channel
                            cue.setValue(
                                "@" + msg[2], "__dest__." + str(i[0]), val)

                self.link.send(["cuedata", msg[1], cue.values])

            if msg[0] == "rmcuef":
                s = cues[msg[1]]

                x = list(s.values[msg[2]].keys())

                for i in x:
                    s.setValue(msg[2], i, None)
                self.link.send(["cuedata", msg[1], s.values])

            if msg[0] == "setscenelight":
                universes.universes[msg[1]]()[msg[2]] = float(msg[3])

            if msg[0] == "gsd":
                # Could be long-running, so we offload to a workerthread
                # Used to be get scene data, Now its a general get everything to show pags thing
                def f():
                    s = core.scenes[msg[1]]
                    self.pushCueList(s.id)
                    self.pushMeta(msg[1])
                    self.pushfixtures()
                kaithem.misc.do(f)

            if msg[0] == "getallcuemeta":
                def f():
                    for i in core.scenes[msg[1]].cues:
                        self.pushCueMeta(core.scenes[msg[1]].cues[i].id)
                kaithem.misc.do(f)

            if msg[0] == "getcuedata":
                s = cues[msg[1]]
                self.link.send(["cuedata", msg[1], s.values])
                self.pushCueMeta(msg[1])

            if msg[0] == "getfixtureclass":
                self.link.send(
                    ["fixtureclass", msg[1], self.fixtureClasses[msg[1]]])

            if msg[0] == "getfixtureclasses":
                # Send placeholder lists
                self.link.send(
                    ["fixtureclasses", {i: [] for i in self.fixtureClasses.keys()}])

            if msg[0] == 'listsoundfolder':
                self.link.send(
                    ["soundfolderlisting", msg[1], listsoundfolder(msg[1])])

            if msg[0] == "getcuemeta":
                s = cues[msg[1]]
                self.pushCueMeta(msg[1])

            if msg[0] == "gasd":
                with core.lock:
                    self.pushUniverses()
                    self.pushfixtures()
                    for i in self.scenememory:
                        s = self.scenememory[i]
                        self.pushCueList(s.id)
                        self.pushMeta(i)
                        if self.scenememory[i].cue:
                            try:
                                self.pushCueMeta(self.scenememory[i].cue.id)
                            except Exception:
                                print(traceback.format_exc())
                        try:
                            self.pushCueMeta(
                                self.scenememory[i].cues['default'].id)
                        except Exception:
                            print(traceback.format_exc())

                        try:
                            for j in self.scenememory[i].cues:
                                self.pushCueMeta(
                                    self.scenememory[i].cues[j].id)
                        except Exception:
                            print(traceback.format_exc())

                    for i in core.activeScenes:
                        # Tell clients about any changed alpha values and stuff.
                        if not i.id in self.scenememory:
                            self.pushMeta(i.id)
                    self.pushConfiguredUniverses()
                self.link.send(["serports", getSerPorts()])

                shows = os.path.join(kaithem.misc.vardir, "chandler", "shows")
                if os.path.isdir(shows):
                    self.link.send(['shows', [i for i in os.listdir(
                        shows) if os.path.isdir(os.path.join(shows, i))]])

                setups = os.path.join(
                    kaithem.misc.vardir, "chandler", "setups")
                if os.path.isdir(setups):
                    self.link.send(['setups', [i for i in os.listdir(
                        setups) if os.path.isdir(os.path.join(setups, i))]])

            # There's such a possibility for an iteration error if universes changes.
            # I'm not going to worry about it, this is only for the GUI list of universes.
            if msg[0] == "getuniverses":
                self.pushUniverses()

            if msg[0] == "scv":
                ch = msg[3]
                # If it looks like an int, it should be an int.
                if isinstance(ch, str):
                    try:
                        ch = int(ch)
                    except Exception:
                        pass

                v = msg[4]

                if isinstance(v, str):
                    try:
                        v = float(v)
                    except Exception:
                        pass

                cues[msg[1]].setValue(msg[2], ch, v)
                self.link.send(["scv", msg[1], msg[2], ch, v])

            if msg[0] == "setMidiSource":
                core.scenes[msg[1]].setMidiSource(msg[2])
            if msg[0] == "setDefaultNext":
                core.scenes[msg[1]].defaultNext = str(msg[2])[:256]
            if msg[0] == "tap":
                core.scenes[msg[1]].tap(msg[2])
            if msg[0] == "setbpm":
                core.scenes[msg[1]].setBPM(msg[2])

            if msg[0] == "setalpha":
                core.scenes[msg[1]].setAlpha(msg[2])

            if msg[0] == "setcrossfade":
                core.scenes[msg[1]].crossfade = float(msg[2])

            if msg[0] == "setdalpha":
                core.scenes[msg[1]].setAlpha(msg[2], sd=True)

            if msg[0] == "addcue":
                n = msg[2].strip()
                if not msg[2] in core.scenes[msg[1]].cues:
                    core.scenes[msg[1]].addCue(n)

            if msg[0] == "searchsounds":
                self.link.send(['soundsearchresults', msg[1],
                               searchPaths(msg[1], core.getSoundFolders())])

            if msg[0] == "newFromSound":
                bn = os.path.basename(msg[2])
                bn = fnToCueName(bn)
                try:
                    tags = TinyTag.get(msg[2])
                    if tags.artist and tags.title:
                        bn = tags.title + " ~ " + tags.artist
                except Exception:
                    print(traceback.format_exc())
                # Empty string is probably going to look best for that char
                bn = bn.replace("'", "")
                # Also the double quotesif they show up
                bn = bn.replace('"', "")
                bn = bn.replace('(', "")
                bn = bn.replace(')', "")
                bn = bn.replace('[', "")
                bn = bn.replace(']', "")

                # Sometimes used as a stylized S
                bn = bn.replace('$', "S")
                bn = bn.replace('@', " at ")

                # Usually going to be the number sign, we can ditch
                bn = bn.replace("#", "")

                # Handle spaces already there or not
                bn = bn.replace(" & ", " and ")
                bn = bn.replace("&", " and ")

                bn = disallow_special(bn, "_~", replaceMode=" ")
                if not bn in core.scenes[msg[1]].cues:
                    core.scenes[msg[1]].addCue(bn)
                    core.scenes[msg[1]].cues[bn].rel_length = True
                    core.scenes[msg[1]].cues[bn].length = 0.01

                    soundfolders = core.getSoundFolders()

                    for i in soundfolders:
                        s = msg[2]
                        # Make paths relative.
                        if not i.endswith("/"):
                            i = i + "/"
                        if s.startswith(i):
                            s = s[len(i):]
                            break
                    core.scenes[msg[1]].cues[bn].sound = s
                    core.scenes[msg[1]].cues[bn].namedForSound = True

                    self.pushCueMeta(core.scenes[msg[1]].cues[bn].id)

            if msg[0] == "newFromSlide":
                bn = os.path.basename(msg[2])
                bn = fnToCueName(bn)

                # Empty string is probably going to look best for that char
                bn = bn.replace("'", "")
                # Also the double quotesif they show up
                bn = bn.replace('"', "")
                bn = bn.replace('(', "")
                bn = bn.replace(')', "")
                bn = bn.replace('[', "")
                bn = bn.replace(']', "")

                # Sometimes used as a stylized S
                bn = bn.replace('$', "S")
                bn = bn.replace('@', " at ")

                # Usually going to be the number sign, we can ditch
                bn = bn.replace("#", "")

                # Handle spaces already there or not
                bn = bn.replace(" & ", " and ")
                bn = bn.replace("&", " and ")

                bn = disallow_special(bn, "_~", replaceMode=" ")
                if not bn in core.scenes[msg[1]].cues:
                    core.scenes[msg[1]].addCue(bn)
                    soundfolders = core.getSoundFolders()

                    for i in soundfolders:
                        s = msg[2]
                        # Make paths relative.
                        if not i.endswith("/"):
                            i = i + "/"
                        if s.startswith(i):
                            s = s[len(i):]
                            break
                    core.scenes[msg[1]].cues[bn].slide = s

                    self.pushCueMeta(core.scenes[msg[1]].cues[bn].id)

            if msg[0] == "gotonext":
                if cues[msg[1]].nextCue:
                    try:
                        cues[msg[1]].scene().nextCue(cause='manual')
                    except Exception:
                        print(traceback.format_exc())

            if msg[0] == "rmcue":
                c = cues[msg[1]]
                c.scene().rmCue(c.id)

            if msg[0] == "setfadein":
                try:
                    v = float(msg[2])
                except Exception:
                    v = msg[2]
                cues[msg[1]].fadein = v
                self.pushCueMeta(msg[1])

            if msg[0] == "setSoundFadeOut":
                try:
                    v = float(msg[2])
                except Exception:
                    v = msg[2]
                cues[msg[1]].soundFadeOut = v
                self.pushCueMeta(msg[1])

            if msg[0] == "setCueVolume":
                try:
                    v = float(msg[2])
                except Exception:
                    v = msg[2]
                cues[msg[1]].soundVolume = v
                self.pushCueMeta(msg[1])
                cues[msg[1]].scene().setAlpha(cues[msg[1]].scene().alpha)

            if msg[0] == "setCueLoops":
                try:
                    v = float(msg[2])
                except Exception:
                    v = msg[2]
                cues[msg[1]].soundLoops = v if (
                    not v == -1) else 99999999999999999

                self.pushCueMeta(msg[1])
                cues[msg[1]].scene().setAlpha(cues[msg[1]].scene().alpha)

            if msg[0] == "setSoundFadeIn":
                try:
                    v = float(msg[2])
                except Exception:
                    v = msg[2]
                cues[msg[1]].soundFadeIn = v
                self.pushCueMeta(msg[1])

            if msg[0] == "setreentrant":
                v = bool(msg[2])

                cues[msg[1]].reentrant = v
                self.pushCueMeta(msg[1])

            if msg[0] == "setCueRules":
                cues[msg[1]].setRules(msg[2])
                self.pushCueMeta(msg[1])

            if msg[0] == "setCueInheritRules":
                cues[msg[1]].setInheritRules(msg[2])
                self.pushCueMeta(msg[1])

            if msg[0] == "setcuesound":
                # If it's a cloud asset, get it first
                kaithem.assetpacks.ensure_file(msg[2])

                soundfolders = core.getSoundFolders()

                for i in soundfolders:
                    s = msg[2]
                    # Make paths relative.
                    if not i.endswith("/"):
                        i = i + "/"
                    if s.startswith(i):
                        s = s[len(i):]
                        break

                if s.strip() and cues[msg[1]].sound and cues[msg[1]].namedForSound:
                    self.pushCueMeta(msg[1])
                    raise RuntimeError(
                        "This cue was named for a specific sound file, forbidding change to avoid confusion.  To override, set to no sound first")
                cues[msg[1]].sound = s
                self.pushCueMeta(msg[1])

            if msg[0] == "setcueslide":
                kaithem.assetpacks.ensure_file(msg[2])
                soundfolders = core.getSoundFolders()

                for i in soundfolders:
                    s = msg[2]
                    # Make paths relative.
                    if not i.endswith("/"):
                        i = i + "/"
                    if s.startswith(i):
                        s = s[len(i):]
                        break

                cues[msg[1]].slide = s
                self.pushCueMeta(msg[1])

            if msg[0] == "setcuesoundoutput":
                cues[msg[1]].soundOutput = msg[2].strip()
                self.pushCueMeta(msg[1])

            if msg[0] == "setcuesoundstartposition":
                cues[msg[1]].soundStartPosition = float(msg[2].strip())
                self.pushCueMeta(msg[1])

            if msg[0] == "setcuemediaspeed":
                cues[msg[1]].mediaSpeed = float(msg[2].strip())
                self.pushCueMeta(msg[1])

            if msg[0] == "setcuemediawindup":
                cues[msg[1]].mediaWindup = float(msg[2].strip())
                self.pushCueMeta(msg[1])

            if msg[0] == "setcuemediawinddown":
                cues[msg[1]].mediaWinddown = float(msg[2].strip())
                self.pushCueMeta(msg[1])

            # if msg[0]=="setlninfluences":
            #     cues[msg[1]].setLivingNightInfluences(msg[2])
            #     self.pushCueMeta(msg[1])

            # if msg[0]=="setlnassosiations":
            #     cues[msg[1]].setLivingNightAssociatoind(msg[2])
            #     self.pushCueMeta(msg[1])

            if msg[0] == "settrack":
                cues[msg[1]].setTrack(msg[2])
                self.pushCueMeta(msg[1])

            if msg[0] == "setcuenotes":
                cues[msg[1]].notes = msg[2].strip()
                self.pushCueMeta(msg[1])

            if msg[0] == "setdefaultactive":
                core.scenes[msg[1]].defaultActive = bool(msg[2])
                self.pushMeta(msg[1], keys={'active'})

            if msg[0] == "setbacktrack":
                core.scenes[msg[1]].setBacktrack(bool(msg[2]))
                self.pushMeta(msg[1], keys={'backtrack'})

            if msg[0] == "setscenesoundout":
                core.scenes[msg[1]].soundOutput = msg[2]
                self.pushMeta(msg[1], keys={'soundOutput'})

            if msg[0] == "setsceneslideoverlay":
                core.scenes[msg[1]].slideOverlayURL = msg[2]
                self.pushMeta(msg[1], keys={'slideOverlayURL'})

            if msg[0] == "setscenecommandtag":
                core.scenes[msg[1]].setCommandTag(msg[2])

                self.pushMeta(msg[1], keys={'commandTag'})

            if msg[0] == "setlength":
                try:
                    v = float(msg[2])
                except Exception:
                    v = msg[2][:256]
                cues[msg[1]].length = v
                cues[msg[1]].scene().recalcCueLen()
                self.pushCueMeta(msg[1])

            if msg[0] == "setrandomize":
                try:
                    v = float(msg[2])
                except Exception:
                    v = msg[2][:256]
                cues[msg[1]].lengthRandomize = v
                cues[msg[1]].scene().recalcRandomizeModifier()
                self.pushCueMeta(msg[1])

            if msg[0] == "setnext":
                if msg[2][:1024]:
                    c = msg[2][:1024].strip()
                else:
                    c = None
                cues[msg[1]].nextCue = c
                self.pushCueMeta(msg[1])

            if msg[0] == "setprobability":
                cues[msg[1]].probability = msg[2][:2048]
                self.pushCueMeta(msg[1])

            if msg[0] == "setblend":
                core.scenes[msg[1]].setBlend(msg[2])
            if msg[0] == "setblendarg":
                core.scenes[msg[1]].setBlendArg(msg[2], msg[3])

            if msg[0] == "setpriority":
                core.scenes[msg[1]].setPriority(msg[2])

            if msg[0] == "setscenename":
                core.scenes[msg[1]].setName(msg[2])

            if msg[0] == "del":
                # X is there in case the activeScenes listing was the last string reference, we want to be able to push the data still
                x = core.scenes[msg[1]]
                checkPermissionsForSceneData(x.toDict(), user)

                x.stop()
                self.delscene(msg[1])

            if msg[0] == "go":
                core.scenes[msg[1]].go()
                self.pushMeta(msg[1])

            if msg[0] == "gobyname":
                core.scenes_by_name[msg[1]].go()
                self.pushMeta(core.scenes_by_name[msg[1]].id)

            if msg[0] == "stopbyname":
                core.scenes_by_name[msg[1]].stop()
                self.pushMeta(msg[1], statusOnly=True)

            if msg[0] == "togglebyname":
                if core.scenes_by_name[msg[1]].isActive():
                    core.scenes_by_name[msg[1]].stop()
                else:
                    core.scenes_by_name[msg[1]].go()
                self.pushMeta(msg[1],)

            if msg[0] == "stop":
                x = core.scenes[msg[1]]
                x.stop()
                self.pushMeta(msg[1], statusOnly=True)

            if msg[0] == "next":
                try:
                    core.runningTracks[msg[1]].end()
                except Exception:
                    print(traceback.format_exc())

            if msg[0] == "testSoundCard":
                kaithem.sound.oggTest(output=msg[1])

        except Exception:
            rl_log_exc("Error handling command")
            self.pushEv('board.error', "__this_lightboard__",
                        time.time(), traceback.format_exc(8))
            print(msg, traceback.format_exc(8))

    def setChannelName(self, id, name="Untitled"):
        self.channelNames[id] = name

    def delscene(self, sc):
        i = None
        with core.lock:
            if sc in self.scenememory:
                i = self.scenememory.pop(sc)
        if i:
            i.stop()
            core.scenes_by_name.pop(i.name)
            self.link.send(["del", i.id])

    def guiPush(self):
        with core.lock:
            for i in self.newDataFunctions:
                i(self)
            self.newDataFunctions = []
            snapshot = getUniverses()
            for i in snapshot:
                if not self.id in snapshot[i].statusChanged:
                    self.link.send(
                        ["universe_status", i, snapshot[i].status, snapshot[i].ok, snapshot[i].telemetry])
                    snapshot[i].statusChanged[self.id] = True

            for i in self.scenememory:
                # Tell clients about any changed alpha values and stuff.
                if not self.id in self.scenememory[i].hasNewInfo:
                    self.pushMeta(i, statusOnly=True)
                    self.scenememory[i].hasNewInfo[self.id] = False

                # special case the monitor scenes.
                if self.scenememory[i].blend == "monitor" and self.scenememory[i].isActive() and self.id not in self.scenememory[i].valueschanged:
                    self.scenememory[i].valueschanged[self.id] = True
                    # Numpy scalars aren't serializable, so we have to un-numpy them in case
                    self.link.send(
                        ["cuedata", self.scenememory[i].cue.id, self.scenememory[i].cue.values])

            for i in core.activeScenes:
                # Tell clients about any changed alpha values and stuff.
                if not self.id in i.hasNewInfo:
                    self.pushMeta(i.id)
                    i.hasNewInfo[self.id] = False


def composite(background, values, alphas, alpha):
    "In place compositing of one universe as a numpy array on a background.  Returns background."
    background = background * (1 - (alphas * alpha)) + values * alphas * alpha
    return background


def applyLayer(universe, uvalues, scene, uobj):
    "May happen in place, or not, but always returns the new version"

    if not universe in scene.canvas.v2:
        return uvalues

    vals = scene.canvas.v2[universe]
    alphas = scene.canvas.a2[universe]

    # The universe may need to know when it's current fade should end,
    # if it handles fading in a different way.
    # This will look really bad for complex things, to try and reduce them to a series of fades,
    # but we just do the best we can, and assume there's mostly only 1 scene at a time affecting things
    uobj.fadeEndTime = max(
        uobj.fadeEndTime, scene.cue.fadein + scene.enteredCue)

    ualphas = uobj.alphas

    if scene.blend == "normal":
        # todo: is it bad to multiply by bool?
        unsetVals = (ualphas == 0.0)
        fade = numpy.maximum(scene.alpha, unsetVals & uobj.hueBlendMask)

        uvalues = composite(uvalues, vals, alphas, fade)
        # Essetially calculate remaining light percent, then multiply layers and convert back to alpha
        ualphas = 1 - ((1 - (alphas * fade)) * (1 - (ualphas)))

    elif scene.blend == "HTP":
        uvalues = numpy.maximum(uvalues, vals * (alphas * scene.alpha))
        ualphas = (alphas * scene.alpha) > 0

    elif scene.blend == "inhibit":
        uvalues = numpy.minimum(uvalues, vals * (alphas * scene.alpha))
        ualphas = (alphas * scene.alpha) > 0

    elif scene.blend == "gel" or scene.blend == "multiply":
        if scene.alpha:
            # precompute constants
            c = 255 / scene.alpha
            uvalues = (uvalues * (1 - alphas * scene.alpha)) + \
                (uvalues * vals) / c

            # COMPLETELY incorrect, but we don't use alpha for that much, and the real math
            # Is compliccated. #TODO
            ualphas = (alphas * scene.alpha) > 0

    elif scene._blend:
        try:
            uvalues = scene._blend.frame(
                universe, uvalues, vals, alphas, scene.alpha)
            # Also incorrect-ish, but treating modified vals as fully opaque is good enough.
            ualphas = (alphas * scene.alpha) > 0
        except Exception:
            print("Error in blend function")
            print(traceback.format_exc())
    uobj.alphas = ualphas
    return uvalues


def pre_render():
    "Reset all universes to either the all 0s background or the cached layer, depending on if the cache layer is still valid"
    # Here we find out what universes can be reset to a cached layer and which need to be fully rerendered.
    changedUniverses = {}
    to_reset = {}

    universes = getUniverses()

    # Important to reverse, that way scenes that need a full reset come after and don't get overwritten
    for i in reversed(core.activeScenes):
        for u in i.affect:
            if u in universes:
                universe = universes[u]
                universe.all_static = True
                if i.rerender:
                    changedUniverses[u] = (0, 0)

                    # We are below the cached layer, we need to fully reset
                    if ((i.priority, i.started) <= universe.prerendered_layer):
                        to_reset[u] = 1
                    else:
                        # We are stacking on another layer or changing the top layer. We don't need
                        # To rerender the entire stack, we just start from the prerendered_layer
                        # Set the universe to the state it was in just after the prerendered layer was rendered.
                        # Since the values are mutable, we need to set this back every frame

                        # Don't overwrite a request to reset the entire thing
                        if not to_reset.get(u, 0) == 1:
                            to_reset[u] = 2
    for u in universes:
        if universes[u].full_rerender:
            to_reset[u] = 1

        universes[u].fadeEndTime = 0
        universes[u].interpolationTime = 0

    for u in to_reset:
        if (to_reset[u] == 1) or not universes[u].prerendered_layer[1]:
            universes[u].reset()
            changedUniverses[u] = (0, 0)
        else:
            universes[u].reset_to_cache()
            changedUniverses[u] = (0, 0)
    return changedUniverses


def render(t=None):
    "This is the primary rendering function"
    changedUniverses = pre_render()

    t = t or time.time()

    universesSnapshot = getUniverses()

    # Remember that scenes get rendered in ascending priority order here
    for i in core.activeScenes:

        # We don't need to call render() if the frame is a static scene and the opacity
        # and all that is the same, we can just re-layer it on top of the values
        if i.rerender or (i.cue.length and ((time.time() - i.enteredCue) > i.cuelen * (60 / i.bpm))):
            i.rerender = False
            i.render()

        if i.blend == "monitor":
            i.updateMonitorValues()
            continue

        data = i.affect

        # Loop over universes the scene affects
        for u in data:
            if u.startswith("__") and u.endswith("__"):
                continue

            if not u in universesSnapshot:
                continue

            universeObject = universesSnapshot[u]

            # If this is above the prerendered stuff we try to avoid doing every frame
            if (i.priority, i.started) > universeObject.top_layer:
                # If this layer we are about to render was found to be the highest layer that likely won't need rerendering,
                # Save the state just befor we apply that layer.
                if (universeObject.save_before_layer == (i.priority, i.started)) and not ((i.priority, i.started) == (0, 0)):
                    universeObject.save_prerendered(
                        universeObject.top_layer[0], universeObject.top_layer[1])

                changedUniverses[u] = (i.priority, i.started)
                universeObject.values = applyLayer(
                    u, universeObject.values, i, universeObject)
                universeObject.top_layer = (i.priority, i.started)

                # If this is the first nonstatic layer, meaning it's render function requested a rerender next frame
                # or if this is the last one, mark it as the one we should save just before
                if i.rerender or (i is core.activeScenes[-1]):
                    if universeObject.all_static:
                        # Copy it and set to none as a flag that we already found it
                        universeObject.all_static = False
                        universeObject.save_before_layer = universeObject.top_layer

    for i in changedUniverses:
        try:
            if i in universesSnapshot:
                x = universesSnapshot[i]
                x.preFrame()
                x.onFrame()
        except Exception:
            raise

    for i in universesSnapshot:
        universesSnapshot[i].full_rerender = False
    changedUniverses = {}


def makeBlankArray(l):
    x = [0] * l
    return numpy.array(x, dtype="f4")


class FadeCanvas():
    def __init__(self):
        "Handles calculating the effect of one scene over a background. This doesn't do blend modes, it just interpolates."
        self.v = {}
        self.a = {}
        self.v2 = {}
        self.a2 = {}

    def paint(self, fade, vals=None, alphas=None):
        """
        Makes v2 and a2 equal to the current background overlayed with values from scene which is any object that has dicts of dicts of vals and and
        alpha.

        Should you have cached dicts of arrays vals and alpha channels(one pair of arrays per universe), put them in vals and arrays
        for better performance.

        fade is the fade amount from 0 to 1 (from background to the new)

        defaultValue is the default value for a universe. Usually 0.

        """

        # We assume a lot of these lists have the same set of universes. If it gets out of sync you
        # probably have to stop and restart the scenes.
        for i in vals:
            effectiveFade = fade
            obj = getUniverse(i)

            # Add existing universes to canvas, skip non existing ones
            if i not in self.v:
                if obj:
                    l = len(obj.values)
                    self.v[i] = makeBlankArray(l)
                    self.a[i] = makeBlankArray(l)
                    self.v2[i] = makeBlankArray(l)
                    self.a2[i] = makeBlankArray(l)

            # Some universes can disable local fading, like smart bulbs wehere we have remote fading.
            # And we would rather use that. Of course, the disadvantage is we can't properly handle
            # Multiple things fading all at once.
            if not obj.localFading:
                effectiveFade = 1

            # We don't want to fade any values that have 0 alpha in the scene,
            # because that's how we mark "not present", and we want to track the old val.
            #faded = self.v[i]*(1-(fade*alphas[i]))+ (alphas[i]*fade)*vals[i]
            faded = self.v[i] * (1 - effectiveFade) + (effectiveFade * vals[i])

            # We always want to jump straight to the value if alpha was previously 0.
            # That's because a 0 alpha would mean the last scene released that channel, and there's
            # nothing to fade from, so we want to fade in from transparent not from black
            is_new = self.a == 0
            self.v2[i] = numpy.where(is_new, vals[i], faded)

        # Now we calculate the alpha values. Including for
        # Universes the cue doesn't affect.
        for i in self.a:
            effectiveFade = fade
            obj = getUniverse(i)
            if not obj.localFading:
                effectiveFade = 1
            if i not in alphas:
                aset = 0
            else:
                aset = alphas[i]
            self.a2[i] = self.a[i] * (1 - effectiveFade) + effectiveFade * aset

    def save(self):
        self.v = copy.deepcopy(self.v2)
        self.a = copy.deepcopy(self.a2)

    def clean(self, affect):
        for i in list(self.a.keys()):
            if i not in affect:
                del self.a[i]

        for i in list(self.a2.keys()):
            if i not in affect:
                del self.a2[i]

        for i in list(self.v.keys()):
            if i not in affect:
                del self.v[i]

        for i in list(self.v2.keys()):
            if i not in affect:
                del self.v2[i]


def getAllDeviceTagPoints():
    o = {}
    for i in kaithem.devices:
        o[i] = {}
        for j in kaithem.devices[i].tagpoints:
            o[i][j] = [kaithem.devices[i].tagpoints[j].name,
                       kaithem.devices[i].tagpoints[j].subtype]


def shortcutCode(code, limitScene=None):
    "API to activate a cue by it's shortcut code"
    print("SC code " + code)
    if not limitScene:
        event("shortcut." + str(code)[:64], None)

    with core.lock:
        if code in shortcut_codes:
            for i in shortcut_codes[code]:
                try:
                    x = i.scene()
                    if limitScene:
                        if (not x is limitScene) and not (x.name == limitScene):
                            print('skip ' + x.name, limitScene)
                            continue
                        x.event("shortcut." + str(code)[:64])

                    if x:
                        x.go()
                        x.gotoCue(i.name, cause='manual')
                except Exception:
                    print(traceback.format_exc())


cues = weakref.WeakValueDictionary()

core.cuesByID = cues

cueDefaults = {

    "fadein": 0,
    "soundFadeOut": 0,
    "soundFadeIn": 0,
    "length": 0,
    "track": True,
    "nextCue": '',
    "sound": "",
    "slide": "",
    'notes': '',
    "soundOutput": '',
    "soundStartPosition": 0,
    "mediaSpeed": 1,
    "mediaWindup": 0,
    "mediaWinddown": 1,
    "rel_length": False,
    "lengthRandomize": 0,
    'inheritRules': '',
    'rules': [],
    'probability': '',
    'values': {},
    'soundVolume': 1,
    'soundLoops': 0,

    'namedForSound': False
}


class Cue():
    "A static set of values with a fade in and out duration"
    __slots__ = ['id', 'changed', 'next_ll', 'alpha', 'fadein', 'length', 'lengthRandomize', 'name', 'values', 'scene',
                 'nextCue', 'track', 'notes', 'shortcut', 'number', 'inherit', 'sound', 'slide', 'rel_length',
                 'soundOutput', 'soundStartPosition', 'mediaSpeed', "mediaWindup", "mediaWinddown", 'onEnter', 'onExit', 'influences', 'associations', "rules", "reentrant", "inheritRules", "soundFadeIn", "soundFadeOut", "soundVolume", 'soundLoops', 'namedForSound', 'probability',
                 '__weakref__']

    def __init__(self, parent, name, f=False, values=None, alpha=1, fadein=0, length=0, track=True, nextCue=None, shortcut='', sound='', slide='', soundOutput='', soundStartPosition=0, mediaSpeed=1, mediaWindup=0, mediaWinddown=0, rel_length=False, id=None, number=None,
                 lengthRandomize=0, script='', onEnter=None, onExit=None, rules=None, reentrant=True, soundFadeIn=0, notes='', soundFadeOut=0, inheritRules='', soundVolume=1, soundLoops=0, namedForSound=False, probability='', **kw):
        # This is so we can loop through them and push to gui
        self.id = uuid.uuid4().hex
        self.name = name

        # Now unused
        #self.script = script
        self.onEnter = onEnter
        self.onExit = onExit
        self.inheritRules = inheritRules or ''
        self.reentrant = True
        self.soundVolume = soundVolume
        self.soundLoops = soundLoops
        self.namedForSound = namedForSound
        self.probability = probability
        self.notes = ''

        # Rules created via the GUI logic editor
        self.rules = rules or []

        disallow_special(name, allowedCueNameSpecials)
        if name[0] in '1234567890 \t_':
            name = 'x' + name

        if id:
            disallow_special(id)
        self.inherit = None
        cues[self.id] = self
        # Odd circular dependancy
        try:
            self.number = number or parent.cues_ordered[-1].number + 5000
        except Exception:
            self.number = 5000
        self.next_ll = None
        parent._addCue(self, f=f)
        self.changed = {}
        self.alpha = alpha
        self.fadein = fadein
        self.soundFadeOut = soundFadeOut
        self.soundFadeIn = soundFadeIn

        self.length = length
        self.rel_length = rel_length
        self.lengthRandomize = lengthRandomize
        self.values = values or {}
        self.scene = weakref.ref(parent)
        self.nextCue = nextCue or ''
        # Note: This refers to tracking as found on lighting gear, not the old concept of track from
        # the first version
        self.track = track
        self.shortcut = None
        self.sound = sound or ''
        self.slide = slide or ''
        self.soundOutput = soundOutput or ''
        self.soundStartPosition = soundStartPosition
        self.mediaSpeed = mediaSpeed
        self.mediaWindup = mediaWindup
        self.mediaWinddown = mediaWinddown

        # Used for the livingnight algorithm
        # Aspect, value tuples
        #self.influences = {}

        # List if tuples(type, aspect, effect)
        # Type is what parameter if the cue is being affected
        #self.associations = []

        self.setShortcut(shortcut, False)

        self.push()

    # def setInfluences(self, influences):
    #     self.influences = influences
    #     self.scene.recalcLivingNight()

    # def getProbabilty(self):
    #     """
    #     When randomly selecting a cue, this modifies the probability of each cue
    #     based on LivingNight parameters
    #     """
    #     s = 1
    #     for i in self.associations:
    #         if i[0]== 'probability':
    #             s= core.lnEffect(s,i[1],i[2])

    #     return s

    def serialize(self):
        x = {"fadein": self.fadein, "length": self.length, 'lengthRandomize': self.lengthRandomize, "shortcut": self.shortcut, "values": self.values,
             "nextCue": self.nextCue, "track": self.track, 'notes': self.notes, "number": self.number, 'sound': self.sound, 'soundOutput': self.soundOutput,
             'soundStartPosition': self.soundStartPosition, 'slide': self.slide, 'mediaSpeed': self.mediaSpeed, 'mediaWindup': self.mediaWindup, 'mediaWinddown': self.mediaWinddown,
             'rel_length': self.rel_length, 'probability': self.probability, 'rules': self.rules,
             'reentrant': self.reentrant, 'inheritRules': self.inheritRules, "soundFadeIn": self.soundFadeIn, "soundFadeOut": self.soundFadeOut, "soundVolume": self.soundVolume, "soundLoops": self.soundLoops, 'namedForSound': self.namedForSound
             }

        # Cleanup defaults
        if x['shortcut'] == number_to_shortcut(self.number):
            del x['shortcut']
        for i in cueDefaults:
            if str(x[i]) == str(cueDefaults[i]):
                del x[i]
        return x

    def push(self):
        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(lambda s: s.pushCueMeta(self.id))

    def pushData(self):
        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(lambda s: s.pushCueData(self.id))

    def pushoneval(self, u, ch, v):
        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(
                    lambda s: s.link.send(["scv", self.id, u, ch, v]))

    def clone(self, name):
        name = self.scene().evalExpr(name)

        if name in self.scene().cues:
            raise RuntimeError("Cannot duplicate cue names in one scene")

        c = Cue(self.scene(), name, fadein=self.fadein, length=self.length, lengthRandomize=self.lengthRandomize,
                values=copy.deepcopy(self.values), nextCue=self.nextCue, rel_length=self.rel_length)

        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(lambda s: s.pushCueMeta(c.id))
        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(lambda s: s.pushCueData(c.id))

    def setTrack(self, val):
        self.track = bool(val)
        self.scene().rerender = True

    def setNumber(self, n):
        "Can take a string representing a decimal number for best accuracy, saves as *1000 fixed point"
        if self.shortcut == number_to_shortcut(self.number):
            self.setShortcut(number_to_shortcut(
                int((Decimal(n) * Decimal(1000)).quantize(1))))
        self.number = int((Decimal(n) * Decimal(1000)).quantize(1))

        # re-sort the cuelist
        self.scene().insertSorted(None)

        self.push()

    def setRules(self, r):
        self.rules = r
        self.scene().refreshRules()

    def setInheritRules(self, r):
        self.inheritRules = r
        self.scene().refreshRules()

    def setShortcut(self, code, push=True):
        disallow_special(code, allow="._")

        if code == '__generate__from__number__':
            code = number_to_shortcut(self.number)
        with core.lock:
            if self.shortcut in shortcut_codes:
                try:
                    shortcut_codes[code].remove(self)
                except Exception:
                    print(traceback.format_exc())

            if random.random() < 1:
                # Do a full GC pass of the shortcut codes list
                torm = []
                for i in shortcut_codes:
                    if not shortcut_codes[i]:
                        torm.append(i)
                    else:
                        for j in list(shortcut_codes[i]):
                            if not j.scene():
                                shortcut_codes[i].remove(j)
                for i in torm:
                    del shortcut_codes[i]

            if code:
                if code in shortcut_codes:
                    shortcut_codes[code].append(self)
                else:
                    shortcut_codes[code] = [self]

            self.shortcut = code
            if push:
                self.push()

    def setValue(self, universe, channel, value):
        disallow_special(universe, allow="_@.")

        try:
            value = float(value)
        except Exception:
            print(traceback.format_exc())

        if isinstance(channel, (int, float)):
            pass
        elif isinstance(channel, str):

            x = channel.strip()
            if not x == channel:
                raise ValueError(
                    "Channel name cannot begin or end with whitespace")

            # If it looks like an int, cast it even if it's a string,
            # We get a lot of raw user input that looks like that.
            try:
                channel = float(channel)
            except Exception:
                pass
        else:
            raise Exception("Only str or int channel numbers allowed")

        # Assume anything that can be an int, is meant to be
        if isinstance(channel, str):
            try:
                channel = int(channel)
            except Exception:
                pass

        with core.lock:
            if universe == "__variables__":
                self.scene().scriptContext.setVar(channel, self.scene().evalExpr(value))

            reset = False
            if not (value is None):
                if not universe in self.values:
                    self.values[universe] = {}
                    reset = True
                if not channel in self.values[universe]:
                    reset = True
                self.values[universe][channel] = value
            else:
                empty = False
                if channel in self.values[universe]:
                    del self.values[universe][channel]
                if not self.values[universe]:
                    empty = True
                    del self.values[universe]
                if empty:
                    self.pushData()
            self.pushoneval(universe, channel, value)

            unmappeduniverse = universe

            x = mapChannel(universe, channel)

            if self.scene().cue == self and self.scene().isActive():
                self.scene().rerender = True

                # If we change something in a pattern effect we just do a full recalc since those are complicated.
                if unmappeduniverse in self.values and '__length__' in self.values[unmappeduniverse]:
                    self.scene().cueValsToNumpyCache(self, False)

                    # The FadeCanvas needs to know about this change
                    self.scene().render(force_repaint=True)

                # Otherwise if we are changing a simple mapped channel we optimize
                elif x:
                    universe, channel = x[0], x[1]

                    if (not universe in self.scene().cue_cached_alphas_as_arrays) and not value is None:
                        uobj = getUniverse(universe)
                        if uobj:
                            self.scene().cue_cached_vals_as_arrays[universe] = numpy.array(
                                [0.0] * len(uobj.values), dtype="f4")
                            self.scene().cue_cached_alphas_as_arrays[universe] = numpy.array(
                                [0.0] * len(uobj.values), dtype="f4")
                    if universe in self.scene().cue_cached_alphas_as_arrays:
                        self.scene(
                        ).cue_cached_alphas_as_arrays[universe][channel] = 1 if not value is None else 0
                        self.scene().cue_cached_vals_as_arrays[universe][channel] = self.scene(
                        ).evalExpr(value if not value is None else 0)
                    if not universe in self.scene().affect:
                        self.scene().affect.append(universe)

                    # The FadeCanvas needs to know about this change
                    self.scene().render(force_repaint=True)

            self.scene().rerender = True

            # For blend modes that don't like it when you
            # change the list of values without resetting
            if reset:
                self.scene().setBlend(self.scene().blend)


class ClosedScene():
    pass


class Scene():
    "An objecting representing one scene. DefaultCue says if you should auto-add a default cue"

    def __init__(self, name=None, values=None, active=False, alpha=1, priority=50, blend="normal", id=None, defaultActive=True,
                 blendArgs=None, backtrack=True, defaultCue=True, bpm=60,
                 soundOutput='', eventButtons=[], displayTags=[], infoDisplay="", utility=False, notes='',
                 mqttServer='', crossfade=0, midiSource='', defaultNext='', commandTag='',
                 slideOverlayURL='',

                 **ignoredParams):

        if name and name in core.scenes_by_name:
            raise RuntimeError("Cannot have 2 scenes sharing a name: " + name)

        if not name.strip():
            raise ValueError("Invalid Name")

        self.mqttConnection = None

        disallow_special(name)

        self.eventButtons = eventButtons[:]
        self.infoDisplay = infoDisplay
        self.utility = bool(utility)

        # This is used for the remote media triggers feature.
        self.mediaLink = kaithem.widget.APIWidget("media_link")
        self.mediaLink.echo = False

        self.slideOverlayURL = slideOverlayURL

        # The active media file being played through the remote playback mechanism.
        self.allowMediaUrlRemote = None

        def handleMediaLink(u, v):
            if v[0] == 'ask':
                self.mediaLink.send(['volume', self.alpha])
                self.mediaLink.send(['mediaURL', self.allowMediaUrlRemote, self.enteredCue, max(
                    0, self.cue.soundFadeIn or self.crossfade)])
                self.mediaLink.send(["slide", self.cue.slide, self.enteredCue, max(
                    0, self.cue.fadein or self.crossfade)])
                self.mediaLink.send(["overlay", self.slideOverlayURL])

            if v[0] == 'error':
                self.event(
                    "system.error", "Web media playback error in remote browser: " + v[1])

        self.mediaLink.attach(handleMediaLink)
        self.lock = threading.RLock()
        self.randomizeModifier = 0

        self.commandTagSubscriptions = []
        self.commandTag = commandTag

        self.displayTagSubscriptions = []
        self.displayTags = []
        self.displayTagValues = {}
        self.displayTagMeta = {}
        self.setDisplayTags(displayTags)

        self.notes = notes
        self.midiSource = ''
        self.defaultNext = str(defaultNext).strip()

        self.id = id or uuid.uuid4().hex

        # TagPoint for managing the current cue
        self.cueTag = kaithem.tags.StringTag(
            "/chandler/scenes/" + name + ".cue")
        self.cueTag.expose("users.chandler.admin", "users.chandler.admin")

        self.cueTagClaim = self.cueTag.claim(
            "__stopped__", "Scene", 50, annotation="SceneObject")

        self.cueVolume = 1

        # Allow GotoCue
        def cueTagHandler(val, timestamp, annotation):
            # We generated this event, that means we don't have to respond to it
            if annotation == "SceneObject":
                return

            if val == "__stopped__":
                self.stop()
            else:
                # Just goto the cue
                self.gotoCue(val, cause='tagpoint')
        self.cueTagHandler = cueTagHandler

        self.cueTag.subscribe(cueTagHandler)

        # This is used to expose the state of the music cue mostly.
        self.cueInfoTag = kaithem.tags.ObjectTag(
            "/chandler/scenes/" + name + ".cueInfo")
        self.cueInfoTag.value = {"audio.meta": {}}
        self.cueInfoTag.expose("users.chandler.admin", "users.chandler.admin")

        self.albumArtTag = kaithem.tags.StringTag(
            "/chandler/scenes/" + name + ".albumArt")
        self.albumArtTag.expose("users.chandler.admin")

        # Used to determine the numbering of added cues
        self.topCueNumber = 0
        # Only used for monitor scenes
        self.valueschanged = {}
        # Place to stash a blend object for new blending mode
        self._blend = None
        self.blendClass = None
        self.alpha = alpha
        self.crossfade = crossfade

        self.cuelen = 0

        # TagPoint for managing the current alpha
        self.alphaTag = kaithem.tags["/chandler/scenes/" + name + ".alpha"]
        self.alphaTag.min = 0
        self.alphaTag.max = 1
        self.alphaTag.expose("users.chandler.admin", "users.chandler.admin")

        self.alphaTagClaim = self.alphaTag.claim(
            self.alpha, "Scene", 50, annotation="SceneObject")

        # Allow setting the alpha
        def alphaTagHandler(val, timestamp, annotation):
            # We generated this event, that means we don't have to respond to it
            if annotation == "SceneObject":
                return
            self.setAlpha(val)

        self.alphaTag.subscribe(alphaTagHandler)
        self.alphaTagHandler = alphaTagHandler

        self.active = False
        self.defaultalpha = alpha
        self.name = name

        #self.values = values or {}
        self.canvas = None
        self.backtrack = backtrack
        self.bpm = bpm
        self.soundOutput = soundOutput

        self.cue = None

        # Used for the tap tempo algorithm
        self.lastTap = 0
        self.tapSequence = 0

        # The list of cues as an actual list that is maintained sorted by number
        self.cues_ordered = []
        # This flag is used to avoid having to repaint the canvas if we don't need to
        self.fadeInCompleted = False
        # A pointer into that list pointing at the current cue. We have to update all this
        # every time we change the lists
        self.cuePointer = 0

        # Used for storing when the sound file ended. 0 indicates a sound file end event hasn't
        # happened since the cue started
        self.sound_end = 0

        self.cues = {}
        if defaultCue:
            self.cue = Cue(self, "default", values)
            self.cueTagClaim.set(self.cue.name, annotation="SceneObject")

        # Used to avoid an excessive number of repeats in random cues
        self.cueHistory = []

        # List of universes we should be affecting.
        # Based on what values are in the cue and what values are inherited
        self.affect = []

        # Lets us cache the lists of values as numpy arrays with 0 alpha for not present vals
        # which are faster that dicts for some operations
        self.cue_cached_vals_as_arrays = {}
        self.cue_cached_alphas_as_arrays = {}

        self.rerenderOnVarChange = False

        self.enteredCue = 0

        # Map event name to runtime as unix timestamp
        self.runningTimers = {}

        self.priority = priority
        # Used by blend modes
        self.blendArgs = blendArgs or {}
        self.setBlend(blend)
        self.defaultActive = defaultActive

        # Used to indicate that the most recent frame has changed something about the scene
        # Metadata that GUI clients need to know about.
        self.hasNewInfo = {}

        # Set to true every time the alpha value changes or a scene value changes
        # set to false at end of rendering
        self.rerender = False

        # Last time the scene was started. Not reset when stopped
        self.started = 0

        self.chandlerVars = {}

        # List the active LivingNight influences
        self.influences = {}

        # self.recalcLivingNight()

        if name:
            core.scenes_by_name[self.name] = self
        if not name:
            name = self.id
        core.scenes[self.id] = self

        # The bindings for script commands that might be in the cue metadata
        # Used to be made on demand, now we just always have it
        self.scriptContext = None
        self.refreshRules()

        self.mqttServer = mqttServer
        self.activeMqttServer = None

        self.setMidiSource(midiSource)

        if defaultCue:
            # self.gotoCue('default',sendSync=False)
            pass

        if active:
            self.gotoCue('default', sendSync=False, cause='start')
            self.go()
            if isinstance(active, float):
                self.started = time.time() - active

        else:
            self.cueTagClaim.set("__stopped__", annotation="SceneObject")

        self.subscribeCommandTags()

    def toDict(self):
        return {
            'bpm': self.bpm,
            'alpha': self.defaultalpha,
            'cues': {j: self.cues[j].serialize() for j in self.cues},
            'priority': self.priority,
            'active': self.defaultActive,
            'blend': self.blend,
            'blendArgs': self.blendArgs,
            'backtrack': self.backtrack,
            'soundOutput': self.soundOutput,
            'slideOverlayURL': self.slideOverlayURL,
            'eventButtons': self.eventButtons,
            'infoDisplay': self.infoDisplay,
            'utility': self.utility,
            'displayTags': self.displayTags,
            'midiSource': self.midiSource,
            'defaultNext': self.defaultNext,
            'commandTag': self.commandTag,
            'uuid': self.id,
            'notes': self.notes,
            'mqttServer': self.mqttServer,
            'crossfade': self.crossfade
        }

    def __del__(self):
        pass

    def getStatusString(self):
        x = ''
        if self.mqttConnection:
            if not self.mqttConnection.statusTag.value == "connected":
                x += "MQTT Disconnected "
        return x

    def close(self):
        "Unregister the scene and delete it from the lists"
        with core.lock:
            self.stop()
            if core.scenes_by_name.get(self.name, None) is self:
                del core.scenes_by_name[self.name]
            if core.scenes.get(self.id, None) is self:
                del core.scenes_by_name[self.id]

    def evalExpr(self, s):
        """Given A string, return a number if it looks like one, evaluate the expression if it starts with =, otherwise
            return the input.

            Given a number, return it.

            Basically, implements something like the logic from a spreadsheet app.
        """
        return self.scriptContext.preprocessArgument(s)

    # def recalcLivingNight(self):
    #     "This is called whenever a relevant change happens to LivingNight."
    #     with self.lock:
    #         if self.cue:
    #             #When the cue changes we alsi
    #             x = self.cue.influences

    #             for i in self.influences:
    #                 if i not in x:
    #                     del self.influences[i]

    #             for i in x:
    #                 if i in self.influences:
    #                     self.influences[i].update(x[i])
    #                 else:
    #                     self.influences[i]=core.lnInfluence(i,x[i])

    def insertSorted(self, c):
        "Insert a None to just recalt the whole ordering"
        with core.lock:

            if c:
                self.cues_ordered.append(c)

            self.cues_ordered.sort(key=lambda i: i.number)
            if self.cue:
                try:
                    self.cuePointer = self.cues_ordered.index(self.cue)
                except Exception:
                    print(traceback.format_exc())
            else:
                self.cuePointer = 0

            # Regenerate linked list by brute force when a new cue is added.
            for i in range(len(self.cues_ordered) - 1):
                self.cues_ordered[i].next_ll = self.cues_ordered[i + 1]
            self.cues_ordered[-1].next_ll = None

    def getDefaultNext(self):
        if self.defaultNext.strip():
            return self.defaultNext.strip()
        try:
            return self.cues_ordered[self.cuePointer + 1].name
        except Exception:
            return None

    def getAfter(self, cue):
        x = self.cues[cue].next_ll
        return x.name if x else None

    def getParent(self, cue):
        "Return the cue that this cue name should inherit values from or None"
        with core.lock:
            if not self.cues[cue].track:
                return None
            if self.cues[cue].inherit:
                if self.cues[cue].inherit in self.cues and not self.cues[cue].inherit == cue:
                    return self.cues[cue].inherit
                else:
                    return None

            # This is an optimization for if we already know the index
            if self.cue and cue == self.cue.name:
                v = self.cuePointer
            else:
                v = self.cues_ordered.index(self.cues[cue])

            if not v == 0:
                x = self.cues_ordered[v - 1]
                if not x.nextCue or x.nextCue == cue:
                    return x.name
            return None

    def rmCue(self, cue):
        with core.lock:
            if not len(self.cues) > 1:
                raise RuntimeError("Cannot have scene with no cues")

            if cue in cues:
                if cues[cue].name == "default":
                    raise RuntimeError("Cannot delete the cue named default")

            if self.cue and self.name == cue:
                try:
                    self.gotoCue("default", cause='deletion')
                except Exception:
                    self.gotoCue(self.cues_ordered[0].name, cause='deletion')

            if cue in cues:
                id = cue
                name = cues[id].name
            elif cue in self.cues:
                name = cue
                id = self.cues[cue].id
            self.cues_ordered.remove(self.cues[name])

            if cue in cues:
                id = cue
                self.cues[cues[cue].name].setShortcut('')
                del self.cues[cues[cue].name]
            elif cue in self.cues:
                id = self.cues[cue].id
                self.cues[cue].setShortcut('')
                del self.cues[cue]

            for i in core.boards:
                if len(i().newDataFunctions) < 100:
                    i().newDataFunctions.append(
                        lambda s: s.link.send(["delcue", id]))
            try:
                self.cuePointer = self.cues_ordered.index(self.cue)
            except Exception:
                print(traceback.format_exc())
        # Regenerate linked list by brute force when a new cue is added.
        for i in range(len(self.cues_ordered) - 1):
            self.cues_ordered[i].next_ll = self.cues_ordered[i + 1]
        self.cues_ordered[-1].next_ll = None

    # I think we can delete this
    def pushCues(self):
        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(lambda s: self.pushCueList(i.id))

    def _addCue(self, cue, prev=None, f=True):
        name = cue.name
        self.insertSorted(cue)
        if name in self.cues and not f:
            raise RuntimeError("Cue would overwrite existing.")
        self.cues[name] = cue
        if prev and prev in self.cues:
            self.cues[prev].nextCue = self.cues[name]

        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(
                    lambda s: s.pushCueMeta(self.cues[name].id))
        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(lambda s: s.pushCueData(cue.id))

    def pushMeta(self, cue=False, statusOnly=False, keys=None):
        # Push cue first so the client already has that data when we jump to the new display
        if cue and self.cue:
            for i in core.boards:
                if len(i().newDataFunctions) < 100:
                    i().newDataFunctions.append(lambda s: s.pushCueMeta(self.cue.id))

        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(lambda s: s.pushMeta(
                    self.id, statusOnly=statusOnly, keys=keys))

    def event(self, s, value=None, info=''):
        # No error loops allowed!
        if not s == "script.error":
            self._event(s, value, info)

    def _event(self, s, value=None, info=''):
        "Manually trigger any script bindings on an event"
        try:
            if self.scriptContext:
                self.scriptContext.event(s, value)
        except Exception:
            rl_log_exc("Error handling event: " + str(s))
            print(traceback.format_exc(6))

    def pickRandomCueFromNames(self, cues):
        names = []
        weights = []

        for i in cues:
            i = i.strip()
            if i in self.cues:
                weights.append(self.evalExpr(
                    self.cues[i].probability.strip() or 1))
                names.append(i)

        return random.choices(names, weights=weights)[0]

    def _parseCueName(self, cue):
        if cue == "__shuffle__":
            x = [i.name for i in self.cues_ordered if not (
                i.name == self.cue.name)]
            for i in list(reversed(self.cueHistory[-15:])):
                if len(x) < 3:
                    break
                elif i[0] in x:
                    x.remove(i[0])
            cue = self.pickRandomCueFromNames(x)

        elif cue == "__random__":
            x = [i.name for i in self.cues_ordered if not i.name == self.cue.name]
            cue = self.pickRandomCueFromNames(x)

        else:
            # Handle random selection option cues
            if "|" in cue:
                x = cue.split("|")
                if random.random() > 0.3:
                    for i in reversed(self.cueHistory[-15:]):
                        if len(x) < 3:
                            break
                        elif i[0] in x:
                            x.remove(i)
                cue = self.pickRandomCueFromNames(x)

            elif "*" in cue:
                import fnmatch
                x = []

                if cue.startswith("shuffle:"):
                    cue = cue[len("shuffle:"):]
                    shuffle = True
                else:
                    shuffle = False

                for i in self.cues_ordered:
                    if fnmatch.fnmatch(i.name, cue):
                        x.append(i.name)
                if not x:
                    raise ValueError("No matching cue for pattern: " + cue)

                if shuffle:
                    # Do the "Shuffle logic" that avoids  recently used cues.
                    # Eliminate until only two remain, the min to not get stuck in
                    # A fixed pattern.
                    optionsNeeded = 2
                    for i in reversed(self.cueHistory[-50:]):
                        if len(x) <= optionsNeeded:
                            break
                        elif i[0] in x:
                            x.remove(i)
                cue = cue = self.pickRandomCueFromNames(x)

        cue = cue.split("?")[0]

        if not cue in self.cues:
            try:
                cue = float(cue)
            except Exception:
                raise ValueError("No such cue " + str(cue))
            for i in self.cues_ordered:
                if i.number - (float(cue) * 1000) < 0.001:
                    cue = i.name
                    break
        return cue

    def gotoCue(self, cue, t=None, sendSync=True, generateEvents=True, cause='generic'):
        "Goto cue by name, number, or string repr of number"
        # Globally raise an error if there's a big horde of cue transitions happening
        doTransitionRateLimit()

        if self.cue:
            oldSoundOut = self.cue.soundOutput
        else:
            oldSoundOut = None
        if not oldSoundOut:
            oldSoundOut = self.soundOutput

        cue = str(self.evalExpr(cue))

        if '?' in cue:
            cue, args = cue.split("?")
            kwargs = urllib.parse.parse_qs(args)
        else:
            kwargs = {}

        for i in kwargs:
            if len(kwargs[i]) == 1:
                kwargs[i] = kwargs[i][0]

        kwargs = collections.defaultdict(lambda: "", kwargs)

        self.scriptContext.setVar("KWARGS", kwargs)

        with core.lock:
            with self.lock:
                if not self.active:
                    return

                if self.canvas:
                    self.canvas.save()

                # There might be universes we affect that we don't anymore,
                # We need to rerender those because otherwise the system might think absolutely nothing has changed.
                # A full rerender on every cue change isn't the most efficient, but it shouldn't be too bad
                # since most frames don't have a cue change in them
                for i in self.affect:
                    rerenderUniverse(i)

                if cue == "__stop__":
                    self.stop()
                    return

                cue = self._parseCueName(cue)

                cobj = self.cues[cue]

                if self.cue:
                    if cobj == self.cue:
                        if not cobj.reentrant:
                            return
                else:
                    # Act like we actually we in the default cue, but allow reenter no matter what since
                    # We weren't in any cue
                    self.cue = self.cues['default']
                    self.cueTagClaim.set(
                        self.cue.name, annotation="SceneObject")

                self.enteredCue = time.time()

                # Allow specifying an "Exact" time to enter for zero-drift stuff, so things stay in sync
                # I don't know if it's fully correct to set the timestamp before exit...
                # However we really don't want to queue up a bazillion transitions
                # If we can't keep up, so we limit that to 3s
                # if t and t>time.time()-3:
                # Also, limit to 500ms in the future, seems like there could be bugs otherwise
                #   self.enteredCue = min(t,self.enteredCue+0.5)

                entered = self.enteredCue

                if not (cue == self.cue.name):
                    if generateEvents:
                        if self.active and self.scriptContext:
                            self.event("cue.exit", value=[
                                       self.cue.name, cause])

                # We return if some the enter transition already
                # Changed to a new cue
                if not self.enteredCue == entered:
                    return

                self.cueHistory.append((cue, time.time()))
                self.cueHistory = self.cueHistory[-1024:]
                self.sound_end = 0

                try:
                    # Take rules from new cue, don't actually set this as the cue we are in
                    # Until we succeed in running all the rules that happen as we enter
                    self.refreshRules(cobj)
                except Exception:
                    rl_log_exc("Error handling script")
                    print(traceback.format_exc(6))

                if self.active:
                    if self.cue.onExit:
                        self.cue.onExit(t)

                    if cobj.onEnter:
                        cobj.onEnter(t)

                    if generateEvents:
                        self.event('cue.enter', [cobj.name, cause])

        # We return if some the enter transition already
                # Changed to a new cue
                if not self.enteredCue == entered:
                    return

                # We don't fully reset until after we are done fading in and have rendered.
                # Until then, the affect list has to stay because it has stuff that prev cues affected.
                # Even if we are't tracking, we still need to know to rerender them without the old effects,
                # And the fade means we might still affect them for a brief time.

                # TODO backtracking these variables?
                cuevars = self.cues[cue].values.get("__variables__", {})
                for i in cuevars:
                    try:
                        self.scriptContext.setVar(i, self.evalExpr(cuevars[i]))
                    except Exception:
                        print(traceback.format_exc())
                        rl_log_exc("Error with cue variable " + i)

                if self.cues[cue].track:
                    self.applyTrackedValues(cue)

                self.mediaLink.send(["slide", self.cues[cue].slide, self.enteredCue, max(
                    0, self.cues[cue].fadein or self.crossfade)])

                # optimization, try to se if we can just increment if we are going to the next cue, else
                # we have to actually find the index of the new cue
                if self.cuePointer < (len(self.cues_ordered) - 1) and self.cues[cue] is self.cues_ordered[self.cuePointer + 1]:
                    self.cuePointer += 1
                else:
                    self.cuePointer = self.cues_ordered.index(self.cues[cue])

                if not self.cues[cue].sound == "__keep__":
                    # Don't stop audio of we're about to crossfade to the next track
                    if not (self.crossfade and self.cues[cue].sound):
                        if self.cues[cue].soundFadeOut or self.cues[cue].mediaWinddown:
                            fadeSound(None, length=self.cues[cue].soundFadeOut, handle=str(
                                self.id), winddown=self.cues[cue].mediaWinddown)
                        else:
                            stopSound(str(self.id))

                    self.allowMediaUrlRemote = None

                    out = self.cues[cue].soundOutput
                    if not out:
                        out = self.soundOutput
                    if not out:
                        out = None

                    if oldSoundOut == "scenewebplayer" and not out == "scenewebplayer":
                        self.mediaLink.send(['volume', self.alpha])
                        self.mediaLink.send(['mediaURL', None, self.enteredCue, max(
                            0, self.cues[cue].fadein or self.crossfade)])

                    if self.cues[cue].sound and self.active:

                        sound = self.cues[cue].sound
                        try:
                            self.cueVolume = min(
                                5, max(0, float(self.evalExpr(self.cues[cue].soundVolume))))
                        except Exception:
                            self.event(
                                "script.error", self.name + " in cueVolume eval:\n" + traceback.format_exc())
                            self.cueVolume = 1
                        try:
                            sound = self.resolveSound(sound)
                        except Exception:
                            print(traceback.format_exc())

                        if os.path.isfile(sound):

                            if not out == "scenewebplayer":

                                # Always fade in if the face in time set.
                                # Also fade in for crossfade, but in that case we only do it if there is something to fade in from.
                                if not (((self.crossfade > 0) and kaithem.sound.isPlaying(str(self.id))) or self.cues[cue].soundFadeIn or self.cues[cue].mediaWindup):
                                    spd = self.scriptContext.preprocessArgument(
                                        self.cues[cue].mediaSpeed)
                                    playSound(sound, handle=str(self.id), volume=self.alpha * self.cueVolume, output=out,
                                              loop=self.cues[cue].soundLoops, start=self.cues[cue].soundStartPosition, speed=spd)
                                else:
                                    fadeSound(sound, length=max(self.crossfade, self.cues[cue].soundFadeIn), handle=str(self.id), volume=self.alpha * self.cueVolume, output=out, loop=self.cues[cue].soundLoops,
                                              start=self.cues[cue].soundStartPosition, windup=self.cues[cue].mediaWindup, winddown=self.cues[cue].mediaWinddown)

                            else:
                                self.allowMediaUrlRemote = sound
                                self.mediaLink.send(['volume', self.alpha])
                                self.mediaLink.send(['mediaURL', sound, self.enteredCue, max(
                                    0, self.cues[cue].fadein or self.crossfade)])

                            try:
                                soundMeta = TinyTag.get(sound, image=True)

                                currentAudioMetadata = {
                                    "title": soundMeta.title or 'Unknown',
                                    "artist": soundMeta.artist or 'Unknown',
                                    "album": soundMeta.album or 'Unknown',
                                    "year": soundMeta.year or 'Unknown'
                                }
                                t = soundMeta.get_image()
                            except Exception:
                                # Not support, but it might just be an unsupported type. if mp3, its a real error, we should alert
                                if sound.endswith('.mp3'):
                                    self.event(
                                        "error", "Reading metadata for: " + sound + traceback.format_exc())
                                t = None
                                currentAudioMetadata = {
                                    'title': "", 'artist': '', "album": '', 'year': ''}

                            self.cueInfoTag.value = {
                                "audio.meta": currentAudioMetadata
                            }

                            if t and len(t) < 3 * 10**6:
                                self.albumArtTag.value = "data:image/jpeg;base64," + \
                                    base64.b64encode(t).decode()
                            else:
                                self.albumArtTag.value = ""

                        else:
                            self.event(
                                "error", "File does not exist: " + sound)

                self.cue = self.cues[cue]
                self.cueTagClaim.set(self.cues[cue].name, annotation="SceneObject")

                self.recalcRandomizeModifier()
                self.recalcCueLen()

                # Recalc what universes are affected by this scene.
                # We don't clear the old universes, we do that when we're done fading in.
                for i in self.cues[cue].values:
                    i = mapUniverse(i)
                    if i and i in universes.universes:
                        if i not in self.affect:
                            self.affect.append(i)

                self.cueValsToNumpyCache(self.cue, not self.cue.track)
                self.fadeInCompleted = False

                # We don't render here. Very short cues coupt create loops of rerendering and goto
                # self.render(force_repaint=True)

                # Instead we set the flag
                self.rerender = True
                self.pushMeta(statusOnly=True)

                self.preloadNextCueSound()

    def applyTrackedValues(self, cue):
        # When jumping to a cue that isn't directly the next one, apply and "parent" cues.
        # We go backwards until we find a cue that has no parent. A cue has a parent if and only if it has either
        # an explicit parent or the previous cue in the numbered list either has the default next cue or explicitly
        # references this cue.
        cobj = self.cues[cue]

        if self.backtrack and not cue == (self.cue.nextCue or self.getDefaultNext()) and cobj.track:
            l = []
            seen = {}
            safety = 10000
            x = self.getParent(cue)
            while x:
                # No l00ps
                if x in seen:
                    break

                # Don't backtrack past the current cue for no reason
                if x is self.cue:
                    break

                l.append(self.cues[x])
                seen[x] = True
                x = self.getParent(x)
                safety -= 1
                if not safety:
                    break

            # Apply all the lighting changes we would have seen if we had gone through the list one at a time.
            for cuex in reversed(l):
                self.cueValsToNumpyCache(cuex)

    def preloadNextCueSound(self):
        # Preload the next cue's sound if we know what it is
        nextCue = None
        if self.cue.nextCue == '':
            nextCue = self.getDefaultNext()
        elif self.cue.nextCue in self.cues:
            nextCue = self.cue.nextCue

        if nextCue and nextCue in self.cues:
            c = self.cues[nextCue]
            sound = c.sound
            try:
                sound = self.resolveSound(sound)
            except Exception:
                return
            if os.path.isfile(sound):
                out = self.cue.soundOutput
                if not out:
                    out = self.soundOutput
                if not out:
                    out = "@auto"

                try:
                    kaithem.sound.preload(sound, out)
                except Exception:
                    print(traceback.format_exc())

    def resolveSound(self, sound):
        return core.resolveSound(sound)

    def recalcRandomizeModifier(self):
        "Recalculate the random variance to apply to the length"
        self.randomizeModifier = random.triangular(
            -float(self.cue.lengthRandomize), +float(self.cue.lengthRandomize))

    def recalcCueLen(self):
        "Calculate the actual cue len, without changing the randomizeModifier"
        if not self.active:
            return
        cuelen = self.scriptContext.preprocessArgument(self.cue.length)
        v = cuelen or 0

        if str(cuelen).startswith('@'):
            selector = recur.getConstraint(cuelen[1:])
            ref = datetime.datetime.now()
            nextruntime = selector.after(ref, True)

            # Workaround for "every hour" and the like, which would normally return the start of the current hour,
            # But in this case we want the next one.  We don't want exclusive matching all the either as that seems a bit buggy.
            if nextruntime <= ref:
                nextruntime = selector.after(nextruntime, False)

            t2 = dt_to_ts(nextruntime, selector.tz)

            nextruntime = t2

            v = nextruntime - time.time()

        else:
            if self.cue.sound and self.cue.rel_length:
                path = self.resolveSound(self.cue.sound)
                if path.endswith(".png") or path.endswith(".jpg") or path.endswith(".webp") or path.endswith(".png") or path.endswith(".heif") or path.endswith(".tiff") or path.endswith(".gif") or path.endswith(".svg"):
                    v = 0
                else:
                    try:
                        # If we are doing crossfading, we have to stop slightly early for
                        # The crossfade to work
                        slen = (TinyTag.get(path).duration -
                                self.crossfade) + cuelen
                        v = max(0, self.randomizeModifier + slen)
                    except Exception:
                        logging.exception(
                            "Error getting length for sound " + str(path))
                        # Default to 5 mins just so it's obvious there is a problem, and so that the cue actually does end eventually
                        self.cuelen = 300
                        return

        if v <= 0:
            self.cuelen = 0
        else:
            # never go below 0.1*the setting or else you could go to zero and get a never ending cue
            self.cuelen = max(0,float(v*0.1) , self.randomizeModifier + float(v))

    def recalcCueVals(self):
        self.cueValsToNumpyCache(self.cue, not self.cue.track)

    def cueValsToNumpyCache(self, cuex, clearBefore=False):
        """Apply everything from the cue to the fade canvas"""
        # Loop over universes in the cue
        if clearBefore:
            self.cue_cached_vals_as_arrays = {}
            self.cue_cached_alphas_as_arrays = {}

        for i in cuex.values:
            universe = mapUniverse(i)
            if not universe:
                continue

            fixture = None
            try:
                if i[1:] in core.fixtures:
                    f = core.fixtures[i[1:]]()
                    if f:
                        fixture = f
            except KeyError:
                print(traceback.format_exc())

            chCount = 0

            if fixture:
                chCount = len(fixture.channels)

            if '__length__' in cuex.values[i]:
                repeats = int(cuex.values[i]['__length__'])
            else:
                repeats = 1

            if '__spacing__' in cuex.values[i]:
                chCount = int(cuex.values[i]['__spacing__'])

            uobj = getUniverse(universe)

            if not uobj:
                continue

            if not universe in self.cue_cached_vals_as_arrays:
                l = len(uobj.values)
                self.cue_cached_vals_as_arrays[universe] = numpy.array(
                    [0.0] * l, dtype="f4")
                self.cue_cached_alphas_as_arrays[universe] = numpy.array(
                    [0.0] * l, dtype="f4")

            if not universe in self.affect:
                self.affect.append(universe)

            self.rerenderOnVarChange = False

            dest = {}

            for j in cuex.values[i]:
                if isinstance(j, str) and j.startswith("__dest__."):
                    dest[j[9:]] = self.evalExpr(
                        cuex.values[i][j] if not cuex.values[i][j] == None else 0)

            for idx in range(repeats):
                for j in cuex.values[i]:
                    if isinstance(j, str) and j.startswith("__"):
                        continue

                    cuev = cuex.values[i][j]

                    evaled = self.evalExpr(cuev if not cuev == None else 0)

                    # Do the blend thing
                    if j in dest:
                        # Repeats is a count, idx is zero based, we want diveder to be 1 on the last index of the set
                        divider = idx / (max(repeats - 1, 1))
                        evaled = (evaled * (1 - divider)) + (dest[j] * divider)

                    x = mapChannel(i, j)
                    if x:
                        universe, channel = x[0], x[1]
                        try:
                            self.cue_cached_alphas_as_arrays[universe][channel + (
                                idx * chCount)] = 1.0 if not cuev == None else 0
                            self.cue_cached_vals_as_arrays[universe][channel + (
                                idx * chCount)] = evaled
                        except Exception:
                            print("err", traceback.format_exc())
                            self.event("script.error", self.name + " cue " + cuex.name + " Val " + str(
                                (universe, channel)) + "\n" + traceback.format_exc())

                    if isinstance(cuev, str) and cuev.startswith("="):
                        self.rerenderOnVarChange = True

    def refreshRules(self, rulesFrom=None):
        with core.lock:
            # We copy over the event recursion depth so that we can detct infinite loops
            if not self.scriptContext:
                self.scriptContext = DebugScriptContext(
                    rootContext, variables=self.chandlerVars, gil=core.lock)

                self.scriptContext.addNamespace("pagevars")

                self.scriptContext.scene = self.id
                self.scriptContext.sceneObj = weakref.ref(self)
                self.scriptContext.sceneName = self.name

                def sendMQTT(t, m):
                    self.sendMqttMessage(t, m)
                    return True
                self.wrMqttCmdSendWrapper = sendMQTT
                self.scriptContext.commands['sendMQTT'] = sendMQTT

            self.scriptContext.clearBindings()

            self.scriptContext.setVar("SCENE", self.name)
            self.runningTimers = {}

            if self.active:
                self.scriptContext.setVar("CUE", (rulesFrom or self.cue).name)

                # Actually add the bindings
                self.scriptContext.addBindings((rulesFrom or self.cue).rules)

                loopPrevent = {(rulesFrom or self.cue.name): True}

                x = (rulesFrom or self.cue).inheritRules
                while x and x.strip():
                    # Avoid infinite loop should the user define a cycle of cue inheritance
                    if x.strip() in loopPrevent:
                        break
                    loopPrevent[x.strip()] = True

                    self.scriptContext.addBindings(self.cues[x].rules)
                    x = self.cues[x].inheritRules

                self.scriptContext.startTimers()
                self.doMqttSubscriptions()

            try:
                for i in core.boards:
                    i().link.send(['scenetimers', self.id, self.runningTimers])
            except Exception:
                rl_log_exc("Error handling timer set notification")

    def onMqttMessage(self, topic, message):
        try:
            self.event("$mqtt:" + topic, json.loads(message.decode("utf-8")))
        except Exception:
            self.event("$mqtt:" + topic, message)

    def doMqttSubscriptions(self, keepUnused=120):
        if self.mqttConnection and self.scriptContext:

            # Subscribe to everything we aren't subscribed to
            for i in self.scriptContext.eventListeners:
                if i.startswith("$mqtt:"):
                    x = i.split(":", 1)
                    if not x[1] in self.mqttSubscribed:
                        self.mqttConnection.subscribe(
                            x[1], self.onMqttMessage, encoding="raw")
                        self.mqttSubscribed[x[1]] = True

            # Unsubscribe from no longer used things
            torm = []

            for i in self.mqttSubscribed:
                if not "$mqtt:" + i in self.scriptContext.eventListeners:
                    if i not in self.unusedMqttTopics:
                        self.unusedMqttTopics[i] = time.monotonic()
                        continue
                    elif self.unusedMqttTopics[i] > time.monotonic() - keepUnused:
                        continue
                    self.mqttConnection.unsubscribe(i, self.onMqttMessage)
                    del self.unusedMqttTopics[i]
                    torm.append(i)
                else:
                    if i in self.unusedMqttTopics:
                        del self.unusedMqttTopics[i]

            for i in torm:
                del self.mqttSubscribed[i]

    def clearMQTT(self, keepUnused=120):
        if self.mqttConnection and self.scriptContext:

            torm = []

            for i in self.mqttSubscribed:
                self.mqttConnection.unsubscribe(i, self.onMqttMessage)
                torm.append(i)

            for i in torm:
                del self.mqttSubscribed[i]

    def sendMqttMessage(self, topic, message):
        "JSON encodes message, and publishes it to the scene's MQTT server"
        self.mqttConnection.publish(topic, message, encoding='json')

    def clearDisplayTags(self):
        with core.lock:
            for i in self.displayTagSubscriptions:
                i[0].unsubscribe(i[1])
            self.displayTagSubscriptions = []
            self.displayTagValues = {}
            self.displayTagMeta = {}

    def displayTagSubscriber(self, n):

        t = n[1]
        if not self.scriptContext.canGetTagpoint(t):
            raise ValueError("Not allowed tag " + t)

        t = kaithem.tags[n[1]]
        sn = n[1]
        self.displayTagMeta[sn] = {}
        self.displayTagMeta[sn]['min'] = t.min
        self.displayTagMeta[sn]['max'] = t.max
        self.displayTagMeta[sn]['hi'] = t.hi
        self.displayTagMeta[sn]['lo'] = t.lo
        self.displayTagMeta[sn]['unit'] = t.unit
        self.displayTagMeta[sn]['subtype'] = t.subtype

        self.pushMeta(keys=["displayTagMeta"])

        def f(v, t, a):
            self.displayTagValues[sn] = v
            self.pushMeta(keys=["displayTagValues"])

        t.subscribe(f)
        self.displayTagValues[sn] = t.value
        self.pushMeta(keys=["displayTagValues"])

        return t, f

    def setDisplayTags(self, dt):
        dt = dt[:]
        with core.lock:
            self.clearDisplayTags()
            try:
                for i in dt:
                    self.displayTagSubscriptions.append(
                        self.displayTagSubscriber(i))
            except Exception:
                print(traceback.format_exc())
            self.displayTags = dt

    def clearConfiguredTags(self):
        with core.lock:
            for i in self.commandTagSubscriptions:
                i[0].unsubscribe(i[1])
            self.commandTagSubscriptions = []

    def commandTagSubscriber(self):
        sn = self.name

        def f(v, t, a):
            v = v[0]

            if v.startswith("launch:"):
                shortcutCode(str(v[len("launch:"):]), sn)

            elif v == 'Rev':
                self.prevCue(cause="ECP")

            elif v == 'Fwd':
                self.nextCue(cause="ECP")

            elif v == "VolumeUp":
                self.setAlpha(self.alpha + 0.07)

            elif v == "VolumeDown":
                self.setAlpha(self.alpha - 0.07)

            elif v == "VolumeMute":
                self.setAlpha(0)

            elif v == "Play":
                if self.active:
                    self.stop()
                else:
                    self.go()

            elif v == "VolumeMute":
                self.setAlpha(0)

            if v.startswith('Lit_'):
                self.event("button." + v[4:])

        return f

    def subscribeCommandTags(self):
        if not self.commandTag.strip():
            return
        with core.lock:
            for i in [self.commandTag]:
                t = kaithem.tags.ObjectTag(i)
                s = self.commandTagSubscriber()
                self.commandTagSubscriptions.append([t, s])
                t.subscribe(s)

    def setCommandTag(self, st):
        st = st.strip()

        self.clearConfiguredTags()

        self.commandTag = st

        if st:
            st = kaithem.tags.ObjectTag(st)
            if st.subtype and not st.subtype == 'event':
                raise ValueError("That tag does not have the event subtype")

            self.subscribeCommandTags()

    def nextCue(self, t=None, cause='generic'):
        with core.lock:
            if self.cue.nextCue and ((self.evalExpr(self.cue.nextCue).split("?")[0] in self.cues) or self.cue.nextCue.startswith("__") or "|" in self.cue.nextCue or "*" in self.cue.nextCue):
                self.gotoCue(self.cue.nextCue, t, cause=cause)
            elif not self.cue.nextCue:
                x = self.getDefaultNext()
                if x:
                    self.gotoCue(x, t)

    def prevCue(self, cause="generic"):
        with core.lock:
            if len(self.cueHistory) > 1:
                c = self.cueHistory[-2]
                c = c[0]
                self.gotoCue(c, cause)

    def setupBlendArgs(self):
        if hasattr(self.blendClass, "parameters"):
            for i in self.blendClass.parameters:
                if i not in self.blendArgs:
                    self.blendArgs[i] = self.blendClass.parameters[i][3]

    def go(self, nohandoff=False):

        self.setDisplayTags(self.displayTags)

        with core.lock:
            if self in core.activeScenes:
                return

            self.canvas = FadeCanvas()

            self.manualAlpha = False
            self.active = True

            if not self.cue:
                self.gotoCue('default', sendSync=False, cause='start')
            else:
                # Re-enter cue to create the cache
                self.gotoCue(self.cue.name, cause='start')
            # Bug workaround for bug where scenes do nothing when first activated
            self.canvas.paint(0, vals=self.cue_cached_vals_as_arrays,
                              alphas=self.cue_cached_alphas_as_arrays)

            self.enteredCue = time.time()

            if self.blend in core.blendmodes:
                self._blend = core.blendmodes[self.blend](self)

            self.effectiveValues = None

            self.hasNewInfo = {}
            self.started = time.time()

            if not self in core._activeScenes:
                core._activeScenes.append(self)
            core._activeScenes = sorted(
                core._activeScenes, key=lambda k: (k.priority, k.started))
            core.activeScenes = core._activeScenes[:]

            self.setMqttServer(self.mqttServer)

            # Minor inefficiency rendering twice the first frame
            self.rerender = True
            # self.render()

    def isActive(self):
        return self.active

    def setPriority(self, p):
        self.hasNewInfo = {}
        self.priority = p
        with core.lock:
            core._activeScenes = sorted(
                core._activeScenes, key=lambda k: (k.priority, k.started))
            core.activeScenes = core._activeScenes[:]
            try:
                for i in self.affect:
                    rerenderUniverse(i)
            except Exception:
                print(traceback.format_exc())

    def mqttStatusEvent(self, value, timestamp, annotation):
        if value == "connected":
            self.event("board.mqtt.connect")
        else:
            self.event("board.mqtt.disconnect")

        self.pushMeta(statusOnly=True)

    @typechecked
    def setMqttServer(self, mqttServer: str):
        with self.lock:
            x = mqttServer.split(":")
            server = x[0]
            if len(x) > 1:
                port = int(x[1])
            else:
                port = 1883

            if mqttServer == self.activeMqttServer:
                return

            # Do after so we can get the err on bad format first
            self.mqttServer = self.activeMqttServer = mqttServer

            self.unusedMqttTopics = {}
            if mqttServer:
                if self in core.activeScenes:

                    # Get rid of old before we change over to new
                    if self.mqttConnection:
                        self.clearMQTT()

                    self.mqttConnection = None
                    self.mqttConnection = kaithem.mqtt.Connection(
                        server, port, alertPriority='warning', connectionID=str(uuid.uuid4()))
                    self.mqttSubscribed = {}

                    t = self.mqttConnection.statusTag

                    if t.value:
                        self.event("board.mqtt.connect")
                    else:
                        self.event("board.mqtt.disconnect")
                    t.subscribe(self.mqttStatusEvent)

            else:
                self.mqttConnection = None
                self.mqttSubscribed = {}

            self.doMqttSubscriptions()

    def setName(self, name):
        disallow_special(name)
        if self.name == "":
            raise ValueError("Cannot name scene an empty string")
        if not isinstance(name, str):
            raise TypeError("Name must be str")
        with core.lock:
            if name in core.scenes_by_name:
                raise ValueError("Name in use")
            if self.name in core.scenes_by_name:
                del core.scenes_by_name[self.name]
            self.name = name
            core.scenes_by_name[name] = self
            self.hasNewInfo = {}
            self.scriptContext.setVar("SCENE", self.name)

    def setBacktrack(self, b):
        b = bool(b)
        if self.backtrack == b:
            return
        else:
            self.backtrack = b
            x = self.enteredCue
            self.gotoCue(self.cue.name)
            self.enteredCue = x
            self.rerender = True
        self.hasNewInfo = {}

    def setBPM(self, b):
        b = float(b)
        if self.bpm == b:
            return
        else:
            self.bpm = b
            self.rerender = True
        self.hasNewInfo = {}

    def tap(self, t=None):
        "Do a tap tempo tap. If the tap happened earlier, use t to enter that time"
        t = t or time.time()

        x = t - self.lastTap

        self.lastTap = t

        l = 60 / self.bpm

        # More than 8s, we're starting a new tap tapSequence
        if x > 8:
            self.tapSequence = 0

        # If we are more than 5 percent off from where the beat is expected,
        # Start agaon
        if self.tapSequence > 1:
            if abs(x - l) > l * 0.05:
                self.tapSequence = 0

        if self.tapSequence:
            f = max((1 / self.tapSequence)**2, 0.0025)
            self.bpm = self.bpm * (1 - f) + (60 / (x)) * f
        self.tapSequence += 1

        l = 60 / self.bpm
        ts = t - self.enteredCue
        beats = ts / l

        fbeat = beats % 1
        # We are almost right on where a beat would be, make a small phase adjustment

        # Back project N beats into the past finding the closest beat to when we entered the cue
        new_ts = round(beats) * l
        x = t - new_ts

        if (fbeat < 0.1 or fbeat > 0.90) and self.tapSequence:
            # Filter between that backprojected time and the real time
            # Yes I know we already incremented tapSequence
            f = 1 / self.tapSequence**1.2
            self.enteredCue = self.enteredCue * (1 - f) + x * f
        elif self.tapSequence:
            # Just change enteredCue to match the phase.
            self.enteredCue = x
        self.pushMeta(keys={'bpm'})

    def stop(self):
        with core.lock:
            # No need to set rerender
            if self.scriptContext:
                self.scriptContext.clearBindings()
                self.scriptContext.clearState()

            # Use the cue as the marker of if we actually
            # Completed the stop, not just if we logically should be stopped
            # Because we want to be able to manually retry that if we failed.
            if not self.cue:
                return

            self._blend = None
            self.hasNewInfo = {}
            self.canvas = None

            try:
                for i in self.affect:
                    rerenderUniverse(i)
            except Exception:
                print(traceback.format_exc())

            self.affect = []
            if self in core._activeScenes:
                core._activeScenes.remove(self)
                core.activeScenes = core._activeScenes[:]

            self.active = False
            self.cue_cached_vals_as_arrays = {}
            self.cue_cached_alphas_as_arrays = {}
            kaithem.sound.stop(str(self.id))

            self.runningTimers.clear()

            try:
                for i in core.boards:
                    i().link.send(['scenetimers', self.id, self.runningTimers])
            except Exception:
                rl_log_exc("Error handling timer set notification")
                print(traceback.format_exc())

            self.cue = None
            self.cueTagClaim.set("__stopped__", annotation="SceneObject")
            self.doMqttSubscriptions(keepUnused=0)

    def noteOn(self, ch, note, vel):
        self.event("midi.note:" + str(ch) + "." + number_to_note(note), vel)

    def noteOff(self, ch, note):
        self.event("midi.noteoff:" + str(ch) + "." + number_to_note(note), 0)

    def cc(self, ch, n, v):
        self.event("midi.cc:" + str(ch) + "." + str(n), v)

    def setMidiSource(self, s):

        if s == self.midiSource:
            return

        if not s:
            kaithem.message.unsubscribe("/midi/" + s.replace(":", '_').replace(
                "[", '').replace("]", '').replace(" ", ''), self.onMidiMessage)
        else:
            kaithem.message.subscribe("/midi/" + s.replace(":", '_').replace(
                "[", '').replace("]", '').replace(" ", ''), self.onMidiMessage)

        self.midiSource = s

    def onMidiMessage(self, t, v):
        if v[0] == 'noteon':
            self.noteOn(v[1], v[2], v[3])
        if v[0] == 'noteoff':
            self.noteOff(v[1], v[2])
        if v[0] == 'cc':
            self.cc(v[1], v[2], v[3])

    def setAlpha(self, val, sd=False):
        val = min(1, max(0, val))
        try:
            self.cueVolume = min(
                5, max(0, float(self.evalExpr(self.cue.soundVolume))))
        except Exception:
            self.event("script.error", self.name +
                       " in cueVolume eval:\n" + traceback.format_exc())
            self.cueVolume = 1

        kaithem.sound.setvol(val * self.cueVolume, str(self.id))
        self.rerender = True

        if not self.isActive() and val > 0:
            self.go()
        self.manualAlpha = True
        self.alpha = val
        self.alphaTagClaim.set(val, annotation="SceneObject")
        if sd:
            self.defaultalpha = val
            self.pushMeta(keys={'alpha', 'dalpha'})
        else:
            self.pushMeta(keys={'alpha', 'dalpha'})

        self.mediaLink.send(['volume', val])

    def addCue(self, name, **kw):
        return Cue(self, name, **kw)

    def setBlend(self, blend):
        disallow_special(blend)
        blend = str(blend)[:256]
        self.blend = blend
        if blend in core.blendmodes:
            if self.isActive():
                self._blend = core.blendmodes[blend](self)
            self.blendClass = core.blendmodes[blend]
            self.setupBlendArgs()
        else:
            self.blendArgs = self.blendArgs or {}
            self._blend = None
            self.blendClass = None
        self.rerender = True
        self.hasNewInfo = {}

    def setBlendArg(self, key, val):
        disallow_special(key, "_")
        # serializableness check
        json.dumps(val)
        if not hasattr(self.blendClass, "parameters") or not key in self.blendClass.parameters:
            raise KeyError("No such param")

        if val is None:
            del self.blendArgs[key]
        else:
            if self.blendClass.parameters[key][1] == "number":
                val = float(val)
            self.blendArgs[key] = val
        self.rerender = True
        self.hasNewInfo = {}

    def clearValue(self, universe, channel):
        self.rerender = True
        try:
            del self.values[universe][channel]
            if not self.values[universe]:
                x = self.values[universe]
                del self.values[universe]
                # Put it back if there was a write from another thread. Prob
                # still not totally threadsafe
                if x:
                    self.values[universe] = x
        except Exception:
            print(traceback.format_exc())
        self.valueschanged = {}

    def render(self, force_repaint=False):
        "Calculate the current alpha value, handle stopping the scene and spawning the next one"
        if self.cue.fadein:
            fadePosition = min((time.time() - self.enteredCue) /
                               (self.cue.fadein * (60 / self.bpm)), 1)
        else:
            fadePosition = 1

        if fadePosition < 1:
            self.rerender = True

        # TODO: We absolutely should not have to do this every time we rerender.
        # Bugfix is in order!
        #self.canvas.paint(fadePosition,vals=self.cue_cached_vals_as_arrays, alphas=self.cue_cached_alphas_as_arrays)

        # Remember, we can and do the next cue thing and still need to repaint, because sometimes the next cue thing does nothing
        if force_repaint or (not self.fadeInCompleted):
            self.canvas.paint(fadePosition, vals=self.cue_cached_vals_as_arrays,
                              alphas=self.cue_cached_alphas_as_arrays)
            if fadePosition >= 1:
                # We no longer affect universes from the previous cue we are fading from

                # But we *do* still keep tracked and backtracked values.
                self.affect = []
                for i in self.cue_cached_vals_as_arrays:
                    u = mapUniverse(i)
                    if u and u in universes.universes:
                        if not u in self.affect:
                            self.affect.append(u)

                # Remove unused universes from the cue
                self.canvas.clean(self.cue_cached_vals_as_arrays)
                self.fadeInCompleted = True
                self.rerender = True

        if self.cuelen and (time.time() - self.enteredCue) > self.cuelen * (60 / self.bpm):
            # rel_length cues end after the sound in a totally different part of code
            # Calculate the "real" time we entered, which is exactly the previous entry time plus the len.
            # Then round to the nearest millisecond to prevent long term drift due to floating point issues.
            self.nextCue(round(self.enteredCue + self.cuelen *
                         (60 / self.bpm), 3), cause='time')

    def updateMonitorValues(self):
        if self.blend == "monitor":
            data = self.cue.values
            for i in data:
                for j in data[i]:
                    x = mapChannel(i, j)
                    if x:
                        u = getUniverse(x[0])
                        if u:
                            v = u.values[x[1]]
                            self.cue.values[i][j] = float(v)
            self.valueschanged = {}


def event(s, value=None, info=''):
    "THIS IS THE ONLY TIME THE INFO THING DOES ANYTHING"
    #disallow_special(s, allow=".")
    with core.lock:
        for i in core.activeScenes:
            i._event(s, value=value, info=info)


lastrendered = 0

core.Board = ChandlerConsole

core.board = ChandlerConsole()
core.boards.append(weakref.ref(core.board))
core.Scene = Scene

kaithem.chandler.board = core.board
kaithem.chandler.Scene = core.Scene
kaithem.chandler.scenesByUUID = core.scenes
kaithem.chandler.scenes = core.scenes_by_name
kaithem.chandler.Universe = universes.Universe
kaithem.chandler.blendmodes = core.blendmodes
kaithem.chandler.fixture = Fixture
kaithem.chandler.shortcut = shortcutCode

kaithem.chandler.commands = rootContext.commands
kaithem.chandler.event = event


controluniverse = universes.Universe("control")
core.controluniverse = weakref.proxy(controluniverse)
varsuniverse = universes.Universe("__variables__")


def loop():
    while 1:
        try:
            with core.lock:
                render()

            global lastrendered
            if time.time() - lastrendered > 1 / 14.0:
                with core.lock:
                    pollsounds()
                with boardsListLock:
                    for i in core.boards:
                        b = i()
                        if b:
                            b.guiPush()
                        del b
                lastrendered = time.time()
            time.sleep(1 / 60)
        except Exception:
            logger.exception("Wat")

thread = threading.Thread(target=loop, name="ChandlerThread")
thread.start()
