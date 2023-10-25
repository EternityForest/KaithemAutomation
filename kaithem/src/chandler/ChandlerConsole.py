from .scenes import Scene
from . import core
from . import universes
from . import scenes
from . import fixtureslib
from . import blendmodes
from .core import disallow_special, logger
from .universes import getUniverse, getUniverses
from ..kaithemobj import kaithem
from .scenes import cues, event

import yaml
from tinytag import TinyTag


import copy
import gc
import os
import threading
import time
import traceback
import uuid
import weakref


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
        if i not in scenes.allowedCueNameSpecials:
            fn = fn.replace(i, "")
    return fn


def listsoundfolder(path):
    "return format [ [subfolderfolder,displayname],[subfolder2,displayname]  ], [file,file2,etc]"
    soundfolders = core.getSoundFolders()

    if not path:
        return [
            [
                [i + ("/" if not i.endswith("/") else ""), soundfolders[i]]
                for i in soundfolders
            ],
            [],
        ]

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
        return [
            [
                [i + ("/" if not i.endswith("/") else ""), soundfolders[i]]
                for i in soundfolders
            ],
            [],
        ]

    # if not os.path.exists(path):
    #    return [[],[]]

    # x = os.listdir(path)
    x = kaithem.assetpacks.ls(path)

    return (
        sorted(
            [
                [os.path.join(path, i), os.path.join(path, i)]
                for i in x
                if i.endswith("/")
            ]
        ),
        sorted([i for i in x if not i.endswith("/")]),
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
            path = path + "/"

        for dir, dirs, files in os.walk(path):
            relpath = dir[len(path):]
            for i in files:
                match = True
                for j in words:
                    if j not in i.lower():
                        if j not in relpath.lower():
                            match = False
                if not match:
                    continue
                results.append((path, os.path.join(relpath, i)))
    return results

def getSerPorts():
    try:
        import serial.tools.list_ports

        if os.path.exists("/dev/serial/by-path"):
            return [
                os.path.join("/dev/serial/by-path", i)
                for i in os.listdir("/dev/serial/by-path")
            ]
        else:
            return [i.device for i in serial.tools.list_ports.comports()]
    except Exception:
        return [str(traceback.format_exc())]


class ChandlerConsole:
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
                    self.configuredUniverses[i[: -len(".yaml")]] = kaithem.persist.load(
                        fn
                    )

        saveLocation = os.path.join(
            kaithem.misc.vardir, "chandler", "fixturetypes")
        if os.path.isdir(saveLocation):
            for i in os.listdir(saveLocation):
                fn = os.path.join(saveLocation, i)
                if os.path.isfile(fn) and fn.endswith(".yaml"):
                    self.fixtureClasses[i[: -
                                          len(".yaml")]] = kaithem.persist.load(fn)

        saveLocation = os.path.join(
            kaithem.misc.vardir, "chandler", "fixtures")
        if os.path.isdir(saveLocation):
            for i in os.listdir(saveLocation):
                fn = os.path.join(saveLocation, i)
                if os.path.isfile(fn) and fn.endswith(".yaml"):
                    self.fixtureAssignments[i[: -len(".yaml")]] = kaithem.persist.load(
                        fn
                    )
        saveLocation = os.path.join(kaithem.misc.vardir, "chandler")
        if os.path.exists(os.path.join(saveLocation, "presets.yaml")):
            self.presets = kaithem.persist.load(
                os.path.join(saveLocation, "presets.yaml"))

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
                    d[i[: -len(".yaml")]] = kaithem.persist.load(fn)

        self.loadDict(d)

        if self.link:
            self.link.send(["refreshPage", self.fixtureAssignments])

    def __init__(self, count=65536):
        self.newDataFunctions = []

        self.id = uuid.uuid4().hex
        self.link = kaithem.widget.APIWidget("api_link")
        self.link.require("users.chandler.admin")
        self.link.echo = False
        # mutable and immutable versions of the active scenes list.
        self._activeScenes = []
        self.activeScenes = []

        self.presets = {}

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
                ["soundoutputs", [i for i in kaithem.sound.outputs()]])

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
            self.ferrs = ""
            try:
                for i in self.fixtures:
                    self.fixtures[i].assign(None, None)
                    self.fixtures[i].rm()
            except Exception:
                self.ferrs += (
                    "Error deleting old assignments:\n" + traceback.format_exc()
                )
                print(traceback.format_exc())

            try:
                del i
            except Exception:
                pass

            self.fixtures = {}

            for i in self.fixtureAssignments.values():
                try:
                    x = universes.Fixture(
                        i["name"], self.fixtureClasses[i["type"]])
                    self.fixtures[i["name"]] = x
                    self.fixtures[i["name"]].assign(
                        i["universe"], int(i["addr"]))
                    universes.fixtures[i["name"]] = weakref.ref(x)
                except Exception:
                    logger.exception("Error setting up fixture")
                    print(traceback.format_exc())
                    self.ferrs += str(i) + "\n" + traceback.format_exc()

            for u in universes.universes:
                self.pushChannelNames(u)

            with core.lock:
                for f in universes.fixtures:
                    if f:
                        self.pushChannelNames("@" + f)

            self.ferrs = self.ferrs or "No Errors!"
            self.pushfixtures()

    def createUniverses(self, data):
        for i in self.universeObjs:
            self.universeObjs[i].close()

        self.universeObjs = {}
        import gc

        gc.collect()
        universeObjects = {}
        u = data
        for i in u:
            if u[i]["type"] == "enttecopen" or u[i]["type"] == "rawdmx":
                universeObjects[i] = universes.EnttecOpenUniverse(
                    i,
                    channels=int(u[i].get("channels", 128)),
                    portname=u[i].get("interface", None),
                    framerate=float(u[i].get("framerate", 44)),
                )
            elif u[i]["type"] == "enttec":
                universeObjects[i] = universes.EnttecUniverse(
                    i,
                    channels=int(u[i].get("channels", 128)),
                    portname=u[i].get("interface", None),
                    framerate=float(u[i].get("framerate", 44)),
                )
            elif u[i]["type"] == "artnet":
                universeObjects[i] = universes.ArtNetUniverse(
                    i,
                    channels=int(u[i].get("channels", 128)),
                    address=u[i].get("interface", "255.255.255.255:6454"),
                    framerate=float(u[i].get("framerate", 44)),
                    number=int(u[i].get("number", 0)),
                )
            elif u[i]["type"] == "tagpoints":
                universeObjects[i] = universes.TagpointUniverse(
                    i,
                    channels=int(u[i].get("channels", 128)),
                    tagpoints=u[i].get("channelConfig", {}),
                    framerate=float(u[i].get("framerate", 44)),
                    number=int(u[i].get("number", 0)),
                )
            else:
                event("system.error", "No universe type: " + u[i]["type"])
        self.universeObjs = universeObjects

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
                    d[i[: -len(".yaml")]] = kaithem.persist.load(fn)

        self.loadDict(d)
        self.refreshFixtures()

    def loadSetup(self, setupName):
        saveLocation = os.path.join(
            kaithem.misc.vardir, "chandler", "setups", setupName, "universes"
        )
        if os.path.isdir(saveLocation):
            for i in os.listdir(saveLocation):
                fn = os.path.join(saveLocation, i)
                if os.path.isfile(fn) and fn.endswith(".yaml"):
                    self.configuredUniverses[i[: -len(".yaml")]] = kaithem.persist.load(
                        fn
                    )

        self.universeObjs = {}
        self.fixtureAssignments = {}
        self.fixtures = {}

        self.fixtureAssignments = {}

        saveLocation = os.path.join(
            kaithem.misc.vardir, "chandler", "setups", setupName, "fixtures"
        )
        if os.path.isdir(saveLocation):
            for i in os.listdir(saveLocation):
                fn = os.path.join(saveLocation, i)
                if os.path.isfile(fn) and fn.endswith(".yaml"):
                    self.fixtureAssignments[i[: -len(".yaml")]] = kaithem.persist.load(
                        fn
                    )

        self.refreshFixtures()
        self.createUniverses(self.configuredUniverses)

        if os.path.exists(os.path.join(saveLocation, "presets.yaml")):
            self.presets = kaithem.persist.load(
                os.path.join(saveLocation, "presets.yaml"))

    def loadSetupFile(self, data, _asuser=False, filename=None, errs=False):
        if not kaithem.users.checkPermission(kaithem.web.user(), "/admin/modules.edit"):
            raise ValueError(
                "You cannot change the setup without /admin/modules.edit")
        data = yaml.load(data, Loader=yaml.SafeLoader)

        if "fixtureTypes" in data:
            self.fixtureClasses.update(data["fixtureTypes"])

        if "universes" in data:
            self.configuredUniverses = data["universes"]
            self.createUniverses(self.configuredUniverses)

        # Compatibility with a legacy typo
        if "fixures" in data:
            data["fixtures"] = data["fixures"]

        if "fixtures" in data:
            self.fixtureAssignments = data["fixtures"]
            self.refreshFixtures()

        if "presets" in data:
            self.presets = data["presets"]
            self.link.send(["presets", data["presets"]])

    def getSetupFile(self):
        with core.lock:
            return {
                "fixtureTypes": self.fixtureClasses,
                "universes": self.configuredUniverses,
                "fixtures": self.fixtureAssignments,
                "presets": self.presets,
            }

    def loadLibraryFile(self, data, _asuser=False, filename=None, errs=False):
        data = yaml.load(data, Loader=yaml.SafeLoader)

        if "fixtureTypes" in data:
            self.fixtureClasses.update(data["fixtureTypes"])
        else:
            raise ValueError("No fixture types in that file")

    def getLibraryFile(self):
        with core.lock:
            return {
                "fixtureTypes": self.fixtureClasses,
                "universes": self.configuredUniverses,
                "fixures": self.fixtureAssignments,
                "presets": self.presets,
            }

    def loadSceneFile(self, data, _asuser=False, filename=None, errs=False):
        data = yaml.load(data, Loader=yaml.SafeLoader)

        # Detect if the user is trying to upload a single scenefile, if so, wrap it in a multi-dict of scenes to keep the reading code
        # The same for both
        if "uuid" in data and isinstance(data["uuid"], str):
            # Remove the .yaml
            data = {filename[:-5]: data}

        for i in data:
            scenes.checkPermissionsForSceneData(data, kaithem.web.user())

        with core.lock:
            for i in self.scenememory:
                scenes.checkPermissionsForSceneData(
                    self.scenememory[i].toDict(), kaithem.web.user()
                )
            for i in self.scenememory:
                self.scenememory[i].stop()
                self.scenememory[i].close()
            self.scenememory = {}
            self.loadDict(data, errs)

    def loadDict(self, data, errs=False):
        with core.lock:
            for i in data:
                # New versions don't have a name key at all, the name is the key
                if "name" in data[i]:
                    pass
                else:
                    data[i]["name"] = i
                n = data[i]["name"]

                # Delete existing scenes we own
                if n in scenes.scenes_by_name:
                    if scenes.scenes_by_name[n].id in self.scenememory:
                        self.scenememory[scenes.scenes_by_name[n].id].stop()
                        self.scenememory[scenes.scenes_by_name[n].id].close()

                        del self.scenememory[scenes.scenes_by_name[n].id]
                    else:
                        raise ValueError(
                            "Scene "
                            + i
                            + " already exists. We cannot overwrite, because it was not created through this board"
                        )
                try:
                    if "defaultActive" in data[i]:
                        x = data[i]["defaultActive"]
                        del data[i]["defaultActive"]
                    if "active" in data[i]:
                        x = data[i]["active"]
                        del data[i]["active"]

                    # Older versions indexed by UUID
                    if "uuid" in data[i]:
                        uuid = data[i]["uuid"]
                        del data[i]["uuid"]
                    else:
                        uuid = i

                    s = Scene(id=uuid, defaultActive=x, **data[i])


                    self.scenememory[uuid] = s
                    if x:
                        s.go()
                        s.rerender = True
                except Exception:
                    if not errs:
                        logger.exception(
                            "Failed to load scene "
                            + str(i)
                            + " "
                            + str(data[i].get("name", ""))
                        )
                        print(
                            "Failed to load scene "
                            + str(i)
                            + " "
                            + str(data[i].get("name", ""))
                            + ": "
                            + traceback.format_exc(3)
                        )
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
                        [
                            "event",
                            [
                                event,
                                target,
                                kaithem.time.strftime(t or time.time()),
                                value,
                                info,
                            ],
                        ]
                    )
                except Exception:
                    if time.monotonic() - self.lastLoggedGuiSendError < 60:
                        logger.exception(
                            "Error when reporting event. (Log ratelimit: 30)"
                        )
                        self.lastLoggedGuiSendError = time.monotonic()
                finally:
                    self.guiSendLock.release()
            else:
                if time.monotonic() - self.lastLoggedGuiSendError < 60:
                    logger.error(
                        "Timeout getting lock to push event. (Log ratelimit: 60)"
                    )
                    self.lastLoggedGuiSendError = time.monotonic()

        kaithem.misc.do(f)

    def pushfixtures(self):
        "Errors in fixture list"
        self.link.send(["ferrs", self.ferrs])
        try:
            self.link.send(
                [
                    "fixtures",
                    {
                        i: [
                            universes.fixtures[i]().universe,
                            universes.fixtures[i]().startAddress,
                            universes.fixtures[i]().channels,
                        ]
                        for i in universes.fixtures
                    },
                ]
            )
        except Exception:
            print(traceback.format_exc())

    def pushUniverses(self):
        snapshot = getUniverses()

        self.link.send(
            [
                "universes",
                {
                    i: {
                        "count": len(snapshot[i].values),
                        "status": snapshot[i].status,
                        "ok": snapshot[i].ok,
                        "telemetry": snapshot[i].telemetry,
                    }
                    for i in snapshot
                },
            ]
        )

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

    def pushChannelNames(self, u):
        "This has expanded to push more data than names"
        if not u[0] == "@":
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
            self.link.send(["cnames", u, d])
        else:
            d = {}
            if u[1:] in universes.fixtures:
                f = universes.fixtures[u[1:]]()
                for i in range(0, len(f.channels)):
                    d[f.channels[i][0]] = [u[1:]] + f.channels[i]
            self.link.send(["cnames", u, d])

    def pushMeta(self, sceneid, statusOnly=False, keys=None):
        "Statusonly=only the stuff relevant to a cue change. Keys is iterabe of what to send, or None for all"
        scene = scenes.scenes[sceneid]

        v = {}
        if scene.scriptContext:
            try:
                for j in scene.scriptContext.variables:
                    if not j == "_":
                        if isinstance(
                            scene.scriptContext.variables[j], (
                                int, float, str, bool)
                        ):
                            v[j] = scene.scriptContext.variables[j]
                        else:
                            v[j] = "__PYTHONDATA__"
            except Exception:
                print(traceback.format_exc())

        if not statusOnly:
            data = {
                "ext": sceneid not in self.scenememory,
                "dalpha": scene.defaultalpha,
                "alpha": scene.alpha,
                "active": scene.isActive(),
                "defaultActive": scene.defaultActive,
                "name": scene.name,
                "bpm": round(scene.bpm, 6),
                "blend": scene.blend,
                "blendArgs": scene.blendArgs,
                "blendDesc": blendmodes.getblenddesc(scene.blend),
                "blendParams": scene.blendClass.parameters
                if hasattr(scene.blendClass, "parameters")
                else {},
                "priority": scene.priority,
                "started": scene.started,
                "enteredCue": scene.enteredCue,
                "backtrack": scene.backtrack,
                "mqttSyncFeatures": scene.mqttSyncFeatures,
                "cue": scene.cue.id if scene.cue else scene.cues["default"].id,
                "cuelen": scene.cuelen,
                "midiSource": scene.midiSource,
                "musicVisualizations": scene.musicVisualizations,
                "defaultNext": scene.defaultNext,
                "commandTag": scene.commandTag,
                "soundOutput": scene.soundOutput,
                "slideOverlayURL": scene.slideOverlayURL,
                "eventButtons": scene.eventButtons,
                "infoDisplay": scene.infoDisplay,
                "utility": scene.utility,
                "displayTags": scene.displayTags,
                "displayTagValues": scene.displayTagValues,
                "displayTagMeta": scene.displayTagMeta,
                "vars": v,
                "timers": scene.runningTimers,
                "notes": scene.notes,
                "mqttServer": scene.mqttServer,
                "crossfade": scene.crossfade,
                "status": scene.getStatusString(),
            }
        else:
            data = {
                "alpha": scene.alpha,
                "active": scene.isActive(),
                "defaultActive": scene.defaultActive,
                "displayTagValues": scene.displayTagValues,
                "enteredCue": scene.enteredCue,
                "cue": scene.cue.id if scene.cue else scene.cues["default"].id,
                "cuelen": scene.cuelen,
                "status": scene.getStatusString(),
            }
        if keys:
            for i in keys:
                if i not in data:
                    raise KeyError(i)
        self.link.send(
            [
                "scenemeta",
                sceneid,
                {i: data[i] for i in data if (not keys or (i in keys))},
            ]
        )

    def pushCueMeta(self, cueid):
        try:
            cue = cues[cueid]
            self.link.send(
                [
                    "cuemeta",
                    cueid,
                    {
                        "fadein": cue.fadein,
                        "alpha": cue.alpha,
                        "length": cue.length,
                        "lengthRandomize": cue.lengthRandomize,
                        "next": cue.nextCue if cue.nextCue else "",
                        "name": cue.name,
                        "id": cueid,
                        "sound": cue.sound,
                        "slide": cue.slide,
                        "soundOutput": cue.soundOutput,
                        "soundStartPosition": cue.soundStartPosition,
                        "mediaSpeed": cue.mediaSpeed,
                        "mediaWindup": cue.mediaWindup,
                        "mediaWinddown": cue.mediaWinddown,
                        "rel_len": cue.rel_length,
                        "track": cue.track,
                        "notes": cue.notes,
                        "scene": cue.scene().id,
                        "shortcut": cue.shortcut,
                        "number": cue.number / 1000.0,
                        "defaultNext": cue.scene().getAfter(cue.name),
                        "prev": cue.scene().getParent(cue.name),
                        "probability": cue.probability,
                        "rules": cue.rules,
                        "reentrant": cue.reentrant,
                        "inheritRules": cue.inheritRules,
                        "soundFadeOut": cue.soundFadeOut,
                        "soundFadeIn": cue.soundFadeIn,
                        "soundVolume": cue.soundVolume,
                        "soundLoops": cue.soundLoops,
                        "triggerShortcut": cue.triggerShortcut,
                        "hasLightingData": len(cue.values),
                    },
                ]
            )
        except Exception:
            core.rl_log_exc("Error pushing cue data")
            print("cue data push error", cueid, traceback.format_exc())

    def pushCueMetaAttr(self, cueid, attr):
        "Be careful with this, some attributes can't be sent directly and need preprocessing"
        try:
            cue = cues[cueid]
            self.link.send(["cuemetaattr", cueid, {attr: getattr(cue, attr)}])
        except Exception:
            core.rl_log_exc("Error pushing cue data")
            print("cue data push error", cueid, traceback.format_exc())

    def pushCueData(self, cueid):
        self.link.send(["cuedata", cues[cueid].id, cues[cueid].values])

    def pushConfiguredUniverses(self):
        self.link.send(["confuniverses", self.configuredUniverses])

    def pushCueList(self, scene):
        s = scenes.scenes[scene]
        x = list(s.cues.keys())
        # split list into messages of 100 because we don't want to exceed the widget send limit
        while x:
            self.link.send(
                [
                    "scenecues",
                    scene,
                    {i: (s.cues[i].id, s.cues[i].number / 1000.0)
                     for i in x[:100]},
                ]
            )
            x = x[100:]

    def _onmsg(self, user, msg):
        try:
            # Getters

            if msg[0] == "gsd":
                # Could be long-running, so we offload to a workerthread
                # Used to be get scene data, Now its a general get everything to show pags thing
                def f():
                    s = scenes.scenes[msg[1]]
                    self.pushCueList(s.id)
                    self.pushMeta(msg[1])
                    self.pushfixtures()

                kaithem.misc.do(f)

            elif msg[0] == "getallcuemeta":

                def f():
                    for i in scenes.scenes[msg[1]].cues:
                        self.pushCueMeta(scenes.scenes[msg[1]].cues[i].id)

                kaithem.misc.do(f)

            elif msg[0] == "getcuedata":
                s = cues[msg[1]]
                self.link.send(["cuedata", msg[1], s.values])
                self.pushCueMeta(msg[1])

            elif msg[0] == "getfixtureclass":
                self.link.send(
                    ["fixtureclass", msg[1], self.fixtureClasses[msg[1]]])

            elif msg[0] == "getfixtureclasses":
                # Send placeholder lists
                self.link.send(
                    ["fixtureclasses", {i: []
                                        for i in self.fixtureClasses.keys()}]
                )
            elif msg[0] == "getcuemeta":
                s = cues[msg[1]]
                self.pushCueMeta(msg[1])

            elif msg[0] == "gasd":
                with core.lock:
                    self.link.send(["presets", self.presets])
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
                                self.scenememory[i].cues["default"].id)
                        except Exception:
                            print(traceback.format_exc())

                        try:
                            for j in self.scenememory[i].cues:
                                self.pushCueMeta(
                                    self.scenememory[i].cues[j].id)
                        except Exception:
                            print(traceback.format_exc())

                    for i in scenes.activeScenes:
                        # Tell clients about any changed alpha values and stuff.
                        if i.id not in self.scenememory:
                            self.pushMeta(i.id)
                    self.pushConfiguredUniverses()
                self.link.send(["serports", getSerPorts()])

                shows = os.path.join(kaithem.misc.vardir, "chandler", "shows")
                if os.path.isdir(shows):
                    self.link.send(
                        [
                            "shows",
                            [
                                i
                                for i in os.listdir(shows)
                                if os.path.isdir(os.path.join(shows, i))
                            ],
                        ]
                    )

                setups = os.path.join(
                    kaithem.misc.vardir, "chandler", "setups")
                if os.path.isdir(setups):
                    self.link.send(
                        [
                            "setups",
                            [
                                i
                                for i in os.listdir(setups)
                                if os.path.isdir(os.path.join(setups, i))
                            ],
                        ]
                    )

            # There's such a possibility for an iteration error if universes changes.
            # I'm not going to worry about it, this is only for the GUI list of universes.
            elif msg[0] == "getuniverses":
                self.pushUniverses()

            elif msg[0] == "getserports":
                self.link.send(["serports", getSerPorts()])

            elif msg[0] == "getCommands":
                c = scenes.rootContext.commands.scriptcommands
                commandInfo = {}
                for i in c:
                    f = c[i]
                    commandInfo[i] = kaithem.chandlerscript.getFunctionInfo(f)
                self.link.send(["commands", commandInfo])

            elif msg[0] == "getconfuniverses":
                self.pushConfiguredUniverses()

            # User level runtime stuff that can't change config

            elif msg[0] == "jumptocue":
                if not cues[msg[1]].scene().active:
                    cues[msg[1]].scene().go()

                cues[msg[1]].scene().gotoCue(cues[msg[1]].name, cause="manual")

            elif msg[0] == "jumpbyname":
                scenes.scenes_by_name[msg[1]].gotoCue(msg[2], cause="manual")

            elif msg[0] == "nextcue":
                scenes.scenes[msg[1]].nextCue(cause="manual")

            elif msg[0] == "prevcue":
                scenes.scenes[msg[1]].nextCue(cause="manual")

            elif msg[0] == "nextcuebyname":
                scenes.scenes_by_name[msg[1]].nextCue(cause="manual")

            elif msg[0] == "shortcut":
                scenes.shortcutCode(msg[1])

            elif msg[0] == "gotonext":
                if cues[msg[1]].nextCue:
                    try:
                        cues[msg[1]].scene().nextCue(cause="manual")
                    except Exception:
                        print(traceback.format_exc())
            elif msg[0] == "go":
                scenes.scenes[msg[1]].go()
                self.pushMeta(msg[1])

            elif msg[0] == "gobyname":
                scenes.scenes_by_name[msg[1]].go()
                self.pushMeta(scenes.scenes_by_name[msg[1]].id)

            elif msg[0] == "stopbyname":
                scenes.scenes_by_name[msg[1]].stop()
                self.pushMeta(msg[1], statusOnly=True)

            elif msg[0] == "togglebyname":
                if scenes.scenes_by_name[msg[1]].isActive():
                    scenes.scenes_by_name[msg[1]].stop()
                else:
                    scenes.scenes_by_name[msg[1]].go()
                self.pushMeta(
                    msg[1],
                )

            elif msg[0] == "stop":
                x = scenes.scenes[msg[1]]
                x.stop()
                self.pushMeta(msg[1], statusOnly=True)

            elif msg[0] == "testSoundCard":
                kaithem.sound.oggTest(output=msg[1])

            ###

            elif msg[0] == "preset":
                if msg[2] is None:
                    self.presets.pop(msg[2], None)
                else:
                    self.presets[msg[1]] = msg[2]

            elif msg[0] == "saveScenes":
                self.saveAsFiles("scenes", self.getScenes(), "lighting/scenes")

            elif msg[0] == "saveShow":
                self.saveAsFiles(
                    os.path.join("shows", msg[1], "scenes"),
                    self.getScenes()
                )

            elif msg[0] == "loadShow":
                self.loadShow(msg[1])

            elif msg[0] == "saveSetup":
                self.saveAsFiles(
                    "fixturetypes", self.fixtureClasses, "lighting/fixtureclasses"
                )
                self.saveAsFiles(
                    "universes", self.configuredUniverses, "lighting/universes"
                )
                self.saveAsFiles(
                    "fixtures", self.fixtureAssignments, "lighting/fixtures"
                )

                saveLocation = os.path.join(kaithem.misc.vardir, "chandler")
                if not os.path.exists(saveLocation):
                    os.makedirs(saveLocation, mode=0o755)

                kaithem.persist.save(
                    core.config, os.path.join(saveLocation, "config.yaml")
                )

                kaithem.persist.save(
                    self.presets, os.path.join(saveLocation, "presets.yaml")
                )

            elif msg[0] == "saveSetupPreset":
                self.saveAsFiles(
                    "fixturetypes",
                    self.fixtureClasses,
                    "lighting/fixtureclasses",
                    noRm=True,
                )
                self.saveAsFiles(
                    os.path.join("setups", msg[1], "universes"),
                    self.configuredUniverses,
                )
                self.saveAsFiles(
                    os.path.join(
                        "setups", msg[1], "fixtures"), self.fixtureAssignments
                )

            elif msg[0] == "saveLibrary":
                self.saveAsFiles(
                    "fixturetypes", self.fixtureClasses, "lighting/fixtureclasses"
                )

            elif msg[0] == "addscene":
                s = Scene(msg[1].strip())
                self.scenememory[s.id] = s
                self.link.send(["newscene", msg[1].strip(), s.id])
                self.pushMeta(s.id)

            elif msg[0] == "addmonitor":
                s = Scene(msg[1].strip(), blend="monitor",
                          priority=100, active=True)
                self.scenememory[s.id] = s
                self.link.send(["newscene", msg[1].strip(), s.id])

            elif msg[0] == "setconfuniverses":
                if kaithem.users.checkPermission(user, "/admin/settings.edit"):
                    self.configuredUniverses = msg[1]
                    self.createUniverses(self.configuredUniverses)
                else:
                    raise RuntimeError("User does not have permission")

            elif msg[0] == "setfixtureclass":
                commandInfo = []
                for i in msg[2]:
                    if i[1] not in ["custom", "fine", "fixed"]:
                        commandInfo.append(i[:2])
                    else:
                        commandInfo.append(i)
                self.fixtureClasses[msg[1]] = commandInfo
                self.refreshFixtures()

            elif msg[0] == "setfixtureclassopz":
                x = []

                for i in msg[2]["channels"]:
                    if i in ("red", "green", "blue", "intensity", "white", "fog"):
                        x.append([i, i])

                    elif i.isnumeric:
                        x.append(["fixed", "fixed", i])

                    elif i == "color":
                        x.append(["hue", "hue"])

                commandInfo = []
                for i in x:
                    if i[1] not in ["custom", "fine", "fixed"]:
                        commandInfo.append(i[:2])
                    else:
                        commandInfo.append(i)
                self.fixtureClasses[msg[1].replace(
                    "-", " ").replace("/", " ")] = commandInfo
                self.refreshFixtures()

            elif msg[0] == "rmfixtureclass":
                del self.fixtureClasses[msg[1]]
                self.refreshFixtures()

            elif msg[0] == "setFixtureAssignment":
                self.fixtureAssignments[msg[1]] = msg[2]
                self.link.send(["fixtureAssignments", self.fixtureAssignments])
                self.refreshFixtures()

            elif msg[0] == "getcuehistory":
                self.link.send(
                    ["cuehistory", msg[1], scenes.scenes[msg[1]].cueHistory])

            elif msg[0] == "rmFixtureAssignment":
                del self.fixtureAssignments[msg[1]]

                self.link.send(["fixtureAssignments", self.fixtureAssignments])
                self.link.send(["fixtureAssignments", self.fixtureAssignments])

                self.refreshFixtures()

            elif msg[0] == "getfixtureassg":
                self.link.send(["fixtureAssignments", self.fixtureAssignments])
                self.pushfixtures()

            elif msg[0] == "clonecue":
                cues[msg[1]].clone(msg[2])

            elif msg[0] == "event":
                event(msg[1], msg[2])

            elif msg[0] == "setshortcut":
                cues[msg[1]].setShortcut(msg[2][:128])
            elif msg[0] == "setnumber":
                cues[msg[1]].setNumber(msg[2])

            elif msg[0] == "setrellen":
                cues[msg[1]].rel_length = msg[2]
                self.pushCueMeta(msg[1])

            elif msg[0] == "setsoundout":
                cues[msg[1]].soundOutput = msg[2]
                self.pushCueMeta(msg[1])

            elif msg[0] == "setNotes":
                scenes.scenes[msg[1]].notes = msg[2]
                self.pushMeta(msg[1], keys={"notes"})

            elif msg[0] == "seteventbuttons":
                scenes.scenes[msg[1]].eventButtons = msg[2]
                self.pushMeta(msg[1], keys={"eventButtons"})

            elif msg[0] == "setinfodisplay":
                scenes.scenes[msg[1]].infoDisplay = msg[2]
                self.pushMeta(msg[1], keys={"infoDisplay"})

            elif msg[0] == "setutility":
                scenes.scenes[msg[1]].utility = msg[2]
                self.pushMeta(msg[1], keys={"utility"})

            elif msg[0] == "setdisplaytags":
                scenes.scenes[msg[1]].setDisplayTags(msg[2])
                self.pushMeta(msg[1], keys={"displayTags"})

            elif msg[0] == "setMqttServer":
                if kaithem.users.checkPermission(user, "/admin/modules.edit"):
                    scenes.scenes[msg[1]].setMqttServer(msg[2])
                    self.pushMeta(msg[1], keys={"mqttServer"})

            elif msg[0] == "clonescene":
                s = Scene(msg[2])
                self.scenememory[s.id] = s
                s0 = scenes.scenes[msg[1]]
                s.fadein = s0.fadein
                s.length = s0.length
                s.defaultalpha = s0.defaultalpha
                s.alpha = s0.alpha
                s.track = s0.track
                s.setBlend(s0.blend)
                s.blendArgs = s0.blendArgs.copy()

                self.link.send(["newscene", msg[1], s.id])

            elif msg[0] == "getcnames":
                self.pushChannelNames(msg[1])

            elif msg[0] == "namechannel":
                if msg[3]:
                    universes.universes[msg[1]]().channels[msg[2]] = msg[3]
                else:
                    del universes.universes[msg[1]]().channels[msg[2]]

            elif msg[0] == "addcueval":
                if hasattr(cues[msg[1]].scene().blendClass, "default_channel_value"):
                    val = cues[msg[1]].scene().blendClass.default_channel_value
                else:
                    val = 0

                hadVals = len(cues[msg[1]].values)

                # Allow number:name format, but we only want the name
                cues[msg[1]].setValue(msg[2], str(msg[3]).split(":")[-1], val)
                # Tell clients that now there is values in that cue
                if not hadVals:
                    self.pushCueMeta(msg[1])

            elif msg[0] == "setcuevaldata":
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

            elif msg[0] == "addcuef":
                cue = cues[msg[1]]

                # Can add a length and start point to the cue.
                # index = int(msg[3])
                length = int(msg[4])
                spacing = int(msg[5])

                # Get rid of any index part, treat it like it's part of the same fixture.
                x = universes.fixtures[msg[2].split("[")[0]]()
                # Add every non-unused channel.  Fixtures
                # Are stored as if they are their own universe, starting with an @ sign.
                # Channels are stored by name and not by number.
                for i in x.channels:
                    if not i[1] in ("unused", "fixed"):
                        if hasattr(cue.scene().blendClass, "default_channel_value"):
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
                            if hasattr(cue.scene().blendClass, "default_channel_value"):
                                val = cue.scene().blendClass.default_channel_value
                            else:
                                val = 0
                            # i[0] is the name of the channel
                            cue.setValue(
                                "@" + msg[2], "__dest__." + str(i[0]), val)

                self.link.send(["cuedata", msg[1], cue.values])
                self.pushCueMeta(msg[1])

            elif msg[0] == "rmcuef":
                s = cues[msg[1]]

                x = list(s.values[msg[2]].keys())

                for i in x:
                    s.setValue(msg[2], i, None)
                self.link.send(["cuedata", msg[1], s.values])
                self.pushCueMeta(msg[1])

            elif msg[0] == "setscenelight":
                universes.universes[msg[1]]()[msg[2]] = float(msg[3])

            elif msg[0] == "listsoundfolder":
                self.link.send(
                    ["soundfolderlisting", msg[1], listsoundfolder(msg[1])])

            elif msg[0] == "scv":
                ch = msg[3]
                # If it looks like an int, it should be an int.
                if isinstance(ch, str):
                    try:
                        ch = int(ch)
                    except ValueError:
                        pass

                v = msg[4]

                if isinstance(v, str):
                    try:
                        v = float(v)
                    except ValueError:
                        pass

                cues[msg[1]].setValue(msg[2], ch, v)
                self.link.send(["scv", msg[1], msg[2], ch, v])

                if v is None:
                    # Count of values in the metadata changed
                    self.pushCueMeta(msg[1])

            elif msg[0] == "setMidiSource":
                scenes.scenes[msg[1]].setMidiSource(msg[2])

            elif msg[0] == "setMusicVisualizations":
                scenes.scenes[msg[1]].setMusicVisualizations(msg[2])

            elif msg[0] == "setDefaultNext":
                scenes.scenes[msg[1]].defaultNext = str(msg[2])[:256]
            elif msg[0] == "tap":
                scenes.scenes[msg[1]].tap(msg[2])
            elif msg[0] == "setbpm":
                scenes.scenes[msg[1]].setBPM(msg[2])

            elif msg[0] == "setalpha":
                scenes.scenes[msg[1]].setAlpha(msg[2])

            elif msg[0] == "setcrossfade":
                scenes.scenes[msg[1]].crossfade = float(msg[2])

            elif msg[0] == "setdalpha":
                scenes.scenes[msg[1]].setAlpha(msg[2], sd=True)

            elif msg[0] == "addcue":
                n = msg[2].strip()
                if not msg[2] in scenes.scenes[msg[1]].cues:
                    scenes.scenes[msg[1]].addCue(n)

            elif msg[0] == "searchsounds":
                self.link.send(
                    [
                        "soundsearchresults",
                        msg[1],
                        searchPaths(msg[1], core.getSoundFolders()),
                    ]
                )

            elif msg[0] == "newFromSound":
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
                bn = bn.replace("(", "")
                bn = bn.replace(")", "")
                bn = bn.replace("[", "")
                bn = bn.replace("]", "")

                # Sometimes used as a stylized S
                bn = bn.replace("$", "S")
                bn = bn.replace("@", " at ")

                # Usually going to be the number sign, we can ditch
                bn = bn.replace("#", "")

                # Handle spaces already there or not
                bn = bn.replace(" & ", " and ")
                bn = bn.replace("&", " and ")

                bn = disallow_special(bn, "_~", replaceMode=" ")
                if bn not in scenes.scenes[msg[1]].cues:
                    scenes.scenes[msg[1]].addCue(bn)
                    scenes.scenes[msg[1]].cues[bn].rel_length = True
                    scenes.scenes[msg[1]].cues[bn].length = 0.01

                    soundfolders = core.getSoundFolders()

                    for i in soundfolders:
                        s = msg[2]
                        # Make paths relative.
                        if not i.endswith("/"):
                            i = i + "/"
                        if s.startswith(i):
                            s = s[len(i):]
                            break
                    scenes.scenes[msg[1]].cues[bn].sound = s
                    scenes.scenes[msg[1]].cues[bn].namedForSound = True

                    self.pushCueMeta(scenes.scenes[msg[1]].cues[bn].id)

            elif msg[0] == "newFromSlide":
                bn = os.path.basename(msg[2])
                bn = fnToCueName(bn)

                # Empty string is probably going to look best for that char
                bn = bn.replace("'", "")
                # Also the double quotesif they show up
                bn = bn.replace('"', "")
                bn = bn.replace("(", "")
                bn = bn.replace(")", "")
                bn = bn.replace("[", "")
                bn = bn.replace("]", "")

                # Sometimes used as a stylized S
                bn = bn.replace("$", "S")
                bn = bn.replace("@", " at ")

                # Usually going to be the number sign, we can ditch
                bn = bn.replace("#", "")

                # Handle spaces already there or not
                bn = bn.replace(" & ", " and ")
                bn = bn.replace("&", " and ")

                bn = disallow_special(bn, "_~", replaceMode=" ")
                if bn not in scenes.scenes[msg[1]].cues:
                    scenes.scenes[msg[1]].addCue(bn)
                    soundfolders = core.getSoundFolders()

                    for i in soundfolders:
                        s = msg[2]
                        # Make paths relative.
                        if not i.endswith("/"):
                            i = i + "/"
                        if s.startswith(i):
                            s = s[len(i):]
                            break
                    scenes.scenes[msg[1]].cues[bn].slide = s

                    self.pushCueMeta(scenes.scenes[msg[1]].cues[bn].id)

            elif msg[0] == "rmcue":
                c = cues[msg[1]]
                c.scene().rmCue(c.id)

            elif msg[0] == "setCueTriggerShortcut":
                v = msg[2]
                cues[msg[1]].triggerShortcut = v
                self.pushCueMeta(msg[1])

            elif msg[0] == "setfadein":
                try:
                    v = float(msg[2])
                except Exception:
                    v = msg[2]
                cues[msg[1]].fadein = v
                self.pushCueMeta(msg[1])

            elif msg[0] == "setSoundFadeOut":
                try:
                    v = float(msg[2])
                except Exception:
                    v = msg[2]
                cues[msg[1]].soundFadeOut = v
                self.pushCueMeta(msg[1])

            elif msg[0] == "setCueVolume":
                try:
                    v = float(msg[2])
                except Exception:
                    v = msg[2]
                cues[msg[1]].soundVolume = v
                self.pushCueMeta(msg[1])
                cues[msg[1]].scene().setAlpha(cues[msg[1]].scene().alpha)

            elif msg[0] == "setCueLoops":
                try:
                    v = float(msg[2])
                except Exception:
                    v = msg[2]
                cues[msg[1]].soundLoops = v if (
                    not v == -1) else 99999999999999999

                self.pushCueMeta(msg[1])
                cues[msg[1]].scene().setAlpha(cues[msg[1]].scene().alpha)

            elif msg[0] == "setSoundFadeIn":
                try:
                    v = float(msg[2])
                except Exception:
                    v = msg[2]
                cues[msg[1]].soundFadeIn = v
                self.pushCueMeta(msg[1])

            elif msg[0] == "setreentrant":
                v = bool(msg[2])

                cues[msg[1]].reentrant = v
                self.pushCueMeta(msg[1])

            elif msg[0] == "setCueRules":
                cues[msg[1]].setRules(msg[2])
                self.pushCueMeta(msg[1])

            elif msg[0] == "setCueInheritRules":
                cues[msg[1]].setInheritRules(msg[2])
                self.pushCueMeta(msg[1])

            elif msg[0] == "setcuesound":
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
                        "This cue was named for a specific sound file, forbidding change to avoid confusion.  To override, set to no sound first"
                    )
                cues[msg[1]].sound = s
                self.pushCueMeta(msg[1])

            elif msg[0] == "setcueslide":
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

            elif msg[0] == "setcuesoundoutput":
                cues[msg[1]].soundOutput = msg[2].strip()
                self.pushCueMeta(msg[1])

            elif msg[0] == "setcuesoundstartposition":
                cues[msg[1]].soundStartPosition = float(msg[2].strip())
                self.pushCueMeta(msg[1])

            elif msg[0] == "setcuemediaspeed":
                cues[msg[1]].mediaSpeed = float(msg[2].strip())
                self.pushCueMeta(msg[1])

            elif msg[0] == "setcuemediawindup":
                cues[msg[1]].mediaWindup = float(msg[2].strip())
                self.pushCueMeta(msg[1])

            elif msg[0] == "setcuemediawinddown":
                cues[msg[1]].mediaWinddown = float(msg[2].strip())
                self.pushCueMeta(msg[1])

            elif msg[0] == "settrack":
                cues[msg[1]].setTrack(msg[2])
                self.pushCueMeta(msg[1])

            elif msg[0] == "setcuenotes":
                cues[msg[1]].notes = msg[2].strip()
                self.pushCueMeta(msg[1])

            elif msg[0] == "setdefaultactive":
                scenes.scenes[msg[1]].defaultActive = bool(msg[2])
                self.pushMeta(msg[1], keys={"active"})

            elif msg[0] == "setbacktrack":
                scenes.scenes[msg[1]].setBacktrack(bool(msg[2]))
                self.pushMeta(msg[1], keys={"backtrack"})

            elif msg[0] == "setmqttfeature":
                scenes.scenes[msg[1]].setMQTTFeature(msg[2], msg[3])
                self.pushMeta(msg[1], keys={"mqttSyncFeatures"})

            elif msg[0] == "setscenesoundout":
                scenes.scenes[msg[1]].soundOutput = msg[2]
                self.pushMeta(msg[1], keys={"soundOutput"})

            elif msg[0] == "setsceneslideoverlay":
                scenes.scenes[msg[1]].slideOverlayURL = msg[2]
                self.pushMeta(msg[1], keys={"slideOverlayURL"})

            elif msg[0] == "setscenecommandtag":
                scenes.scenes[msg[1]].setCommandTag(msg[2])

                self.pushMeta(msg[1], keys={"commandTag"})

            elif msg[0] == "setlength":
                try:
                    v = float(msg[2])
                except Exception:
                    v = msg[2][:256]
                cues[msg[1]].length = v
                cues[msg[1]].scene().recalcCueLen()
                self.pushCueMeta(msg[1])

            elif msg[0] == "setrandomize":
                try:
                    v = float(msg[2])
                except Exception:
                    v = msg[2][:256]
                cues[msg[1]].lengthRandomize = v
                cues[msg[1]].scene().recalcRandomizeModifier()
                self.pushCueMeta(msg[1])

            elif msg[0] == "setnext":
                if msg[2][:1024]:
                    c = msg[2][:1024].strip()
                else:
                    c = None
                cues[msg[1]].nextCue = c
                self.pushCueMeta(msg[1])

            elif msg[0] == "setprobability":
                cues[msg[1]].probability = msg[2][:2048]
                self.pushCueMeta(msg[1])

            elif msg[0] == "setblend":
                scenes.scenes[msg[1]].setBlend(msg[2])
            elif msg[0] == "setblendarg":
                scenes.scenes[msg[1]].setBlendArg(msg[2], msg[3])

            elif msg[0] == "setpriority":
                scenes.scenes[msg[1]].setPriority(msg[2])

            elif msg[0] == "setscenename":
                scenes.scenes[msg[1]].setName(msg[2])

            elif msg[0] == "del":
                # X is there in case the activeScenes listing was the last string reference, we want to be able to push the data still
                x = scenes.scenes[msg[1]]
                scenes.checkPermissionsForSceneData(x.toDict(), user)

                x.stop()
                self.delscene(msg[1])

        except Exception:
            core.rl_log_exc("Error handling command")
            self.pushEv(
                "board.error",
                "__this_lightboard__",
                time.time(),
                traceback.format_exc(8),
            )
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
            scenes.scenes_by_name.pop(i.name)
            self.link.send(["del", i.id])

    def guiPush(self):
        with core.lock:
            for i in self.newDataFunctions:
                i(self)
            self.newDataFunctions = []
            snapshot = getUniverses()
            for i in snapshot:
                if self.id not in snapshot[i].statusChanged:
                    self.link.send(
                        [
                            "universe_status",
                            i,
                            snapshot[i].status,
                            snapshot[i].ok,
                            snapshot[i].telemetry,
                        ]
                    )
                    snapshot[i].statusChanged[self.id] = True

            for i in self.scenememory:
                # Tell clients about any changed alpha values and stuff.
                if self.id not in self.scenememory[i].hasNewInfo:
                    self.pushMeta(i, statusOnly=True)
                    self.scenememory[i].hasNewInfo[self.id] = False

                # special case the monitor scenes.
                if (
                    self.scenememory[i].blend == "monitor"
                    and self.scenememory[i].isActive()
                    and self.id not in self.scenememory[i].valueschanged
                ):
                    self.scenememory[i].valueschanged[self.id] = True
                    # Numpy scalars aren't serializable, so we have to un-numpy them in case
                    self.link.send(
                        [
                            "cuedata",
                            self.scenememory[i].cue.id,
                            self.scenememory[i].cue.values,
                        ]
                    )

            for i in scenes.activeScenes:
                # Tell clients about any changed alpha values and stuff.
                if self.id not in i.hasNewInfo:
                    self.pushMeta(i.id)
                    i.hasNewInfo[self.id] = False