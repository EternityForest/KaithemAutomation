from .scenes import Scene
from . import core
from . import universes
from . import scenes
from . import fixtureslib
from . import blendmodes
from . import console_abc
from .core import logger
from .universes import getUniverse, getUniverses
from ..kaithemobj import kaithem
from ..import schemas
from ..import scheduling

from .scenes import cues, event

import yaml


from typing import Optional, Set, Any, Dict, List
import copy
import os
import threading
import time
import traceback
import uuid
import weakref

# The frontend's ephemeral state is using CamelCase conventions for now
from .. import snake_compat


def from_legacy(d: Dict[str, Any]) -> Dict[str, Any]:
    if 'mediaWindup' in d:
        d['media_wind_up'] = d.pop('mediaWindup')
    if 'mediaWinduown' in d:
        d['media_wind_down'] = d.pop('mediaWinduown')
    if 'fadein' in d:
        d['fade_in'] = d.pop('fadein')
    return d


class ChandlerConsole(console_abc.Console_ABC):
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

        self.linkSend(["refreshPage", self.fixtureAssignments])

    def __init__(self):
        super().__init__()

        self.id = uuid.uuid4().hex

        # mutable and immutable versions of the active scenes list.
        self._active_scenes = []
        self.active_scenes = []

        self.presets = {}

        # This light board's scene memory, or the set of scenes 'owned' by this board.
        self.scenememory: Dict[str, Scene] = {}

        # For change etection in scenes
        self.last_saved_versions : Dict[str, Dict[str,Any]] = {}

        self.ext_scenes = {}

        self.lock = threading.RLock()

        self.configuredUniverses: Dict[str, Any] = {}
        self.fixtureAssignments: Dict[str, Any] = {}
        self.fixtures = {}

        self.universeObjs: Dict[str, universes.Universe] = {}
        self.fixtureClasses: Dict[str, Any] = copy.deepcopy(fixtureslib.genericFixtureClasses)

        self.loadProject()

        self.refreshFixtures()

        def f(self: ChandlerConsole, *dummy: tuple[Any]):
            self.linkSend(
                ["soundoutputs", [i for i in kaithem.sound.outputs()]])

        self.callback_jackports = f
        kaithem.message.subscribe("/system/jack/newport/", f)
        kaithem.message.subscribe("/system/jack/delport/", f)

        # Use only for stuff in background threads, to avoid pileups that clog the
        # Whole worker pool
        self.guiSendLock = threading.Lock()

        # For logging ratelimiting
        self.lastLoggedGuiSendError = 0

        self.autosave_checker = scheduling.scheduler.every(self.check_autosave, 10*60)

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

    def save_setup(self, force=True):

        # These pre-checks are just for performance reasons, saveasfiles already knows how not
        # to unnecessarily do disk writes
        # as does persist.save
        if force or not self.fixtureClasses == self.last_saved_versions.get("__INTERNAL__:__FIXTURECLASSES__", None):
            self.last_saved_versions["__INTERNAL__:__FIXTURECLASSES__"] = copy.deepcopy(self.fixtureClasses)
            self.saveAsFiles(
                    "fixturetypes", self.fixtureClasses, "lighting/fixtureclasses"
                )

        if force or not self.configuredUniverses == self.last_saved_versions.get("__INTERNAL__:__UNIVERSES__", None):
            self.last_saved_versions["__INTERNAL__:__UNIVERSES__"] = copy.deepcopy(self.configuredUniverses)
            self.saveAsFiles(
                "universes", self.fixtureAssignments, "lighting/universes"
            )

        if force or not self.fixtureAssignments == self.last_saved_versions.get("__INTERNAL__:__ASSG__", None):
            self.last_saved_versions["__INTERNAL__:__ASSG__"] = copy.deepcopy(self.fixtureAssignments)
                
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
        
    def createUniverses(self, data):
        assert isinstance(data, Dict)
        for i in self.universeObjs:
            self.universeObjs[i].close()

        self.universeObjs = {}
        import gc

        gc.collect()
        universeObjects = {}
        u: Dict[str, Dict[Any, Any]] = data
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
        if not kaithem.users.check_permission(kaithem.web.user(), "/admin/modules.edit"):
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
            self.linkSend(["presets", data["presets"]])

    def getSetupFile(self):
        with core.lock:
            return {
                "fixtureTypes": self.fixtureClasses,
                "universes": self.configuredUniverses,
                "fixtures": self.fixtureAssignments,
                "presets": self.presets,
            }

    def loadLibraryFile(self, data_file_str: str, _asuser: bool = False, filename: str = None, errs: bool = False):
        data = yaml.load(data_file_str, Loader=yaml.SafeLoader)

        if "fixtureTypes" in data:
            assert isinstance(data["fixtureTypes"], Dict)

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

    def loadSceneFile(self, data, filename: str, errs=False, clear_old=True):
        data = yaml.load(data, Loader=yaml.SafeLoader)

        # Detect if the user is trying to upload a single scenefile, if so, wrap it in a multi-dict of scenes to keep the reading code
        # The same for both
        if "uuid" in data and isinstance(data["uuid"], str):
            # Remove the .yaml
            data = {filename[:-5]: data}


        with core.lock:
            for i in self.scenememory:
                scenes.checkPermissionsForSceneData(
                    self.scenememory[i].toDict(), kaithem.web.user()
                )
            for i in self.scenememory:
                if clear_old or (i in data):
                    self.scenememory[i].stop()
                    self.scenememory[i].close()

            self.scenememory = {}
            self.loadDict(data, errs)

    def loadDict(self, data, errs=False):

        data = from_legacy(data)
        data = snake_compat.snakify_dict(data)

        # Note that validation could include integer keys, but we handle that
        for i in data:
            try:
                schemas.validate("chandler/scene", data[i])
            except Exception:
                logger.exception(f"Error Validating scene {i}, loading anyway")

            cues = data[i].get('cues', {})
            for j in cues:
                try:
                    schemas.validate("chandler/cue", cues[j])
                except Exception:
                    logger.exception(
                        f"Error Validating cue {j}, loading anyway")

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
                    x = False

                    # I think this was a legacy save format thing TODO
                    if "default_active" in data[i]:
                        x = data[i]["default_active"]
                        del data[i]["default_active"]
                    if "active" in data[i]:
                        x = data[i]["active"]
                        del data[i]["active"]

                    # Older versions indexed by UUID
                    if "uuid" in data[i]:
                        uuid = data[i]["uuid"]
                        del data[i]["uuid"]
                    else:
                        uuid = i

                    s = Scene(id=uuid, default_active=x, **data[i])

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
                    self.linkSend(
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
        self.linkSend(["ferrs", self.ferrs])
        try:
            self.linkSend(
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

        self.linkSend(
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
        

    def check_autosave(self):
        changed = False
        s = self.getScenes()
        for i in s:
            if not s[i] == self.last_saved_versions.get(i,None):
                changed = True
                logger.info("Chandler scenes changed. Autosaving.")

        if changed:
            self.saveAsFiles("scenes", self.getScenes(), "lighting/scenes")

        self.save_setup(force=False)

    def saveAsFiles(self, dirname: str, data: Any, legacyKey: Optional[str] = None):
        sd = data
        saveLocation = os.path.join(kaithem.misc.vardir, "chandler", dirname)
        if not os.path.exists(saveLocation):
            os.makedirs(saveLocation, mode=0o755)

        saved = {}
        # Lock used to prevent conflict, saving over each other with nonsense data.
        with core.lock:
            for i in sd:
                saved[i + ".yaml"] = True
                self.last_saved_versions[i] = copy.deepcopy(sd[i])
                kaithem.persist.save(
                    sd[i], os.path.join(saveLocation, i + ".yaml"))

        # Delete everything not in folder
        for i in os.listdir(saveLocation):
            fn = os.path.join(saveLocation, i)
            if os.path.isfile(fn) and i.endswith(".yaml"):
                if i not in saved:
                    try:
                        self.last_saved_versions.pop(i, None)
                    except Exception:
                        pass
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
            self.linkSend(["cnames", u, d])
        else:
            d = {}
            if u[1:] in universes.fixtures:
                f = universes.fixtures[u[1:]]()
                if f:
                    for i in range(0, len(f.channels)):
                        d[f.channels[i][0]] = [u[1:]] + f.channels[i]
            self.linkSend(["cnames", u, d])

    def pushMeta(self, sceneid: str, statusOnly: bool = False, keys: Optional[List[Any] | Set[Any] | Dict[Any, Any]] = None):
        "Statusonly=only the stuff relevant to a cue change. Keys is iterabe of what to send, or None for all"
        scene = scenes.scenes.get(sceneid, None)
        # Race condition of deleted scenes
        if not scene:
            return

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
            data: Dict[str, Any] = {
                "ext": sceneid not in self.scenememory,
                "dalpha": scene.defaultalpha,
                "alpha": scene.alpha,
                "active": scene.isActive(),
                "default_active": scene.default_active,
                "name": scene.name,
                "bpm": round(scene.bpm, 6),
                "blend": scene.blend,
                "blend_args": scene.blend_args,
                "blendDesc": blendmodes.getblenddesc(scene.blend),
                "blendParams": scene.blendClass.parameters
                if hasattr(scene.blendClass, "parameters")
                else {},
                "priority": scene.priority,
                "started": scene.started,
                "enteredCue": scene.enteredCue,
                "backtrack": scene.backtrack,
                "mqtt_sync_features": scene.mqtt_sync_features,
                "cue": scene.cue.id if scene.cue else scene.cues["default"].id,
                "cuelen": scene.cuelen,
                "midi_source": scene.midi_source,
                "music_visualizations": scene.music_visualizations,
                "default_next": scene.default_next,
                "command_tag": scene.command_tag,
                "sound_output": scene.sound_output,
                "slide_overlay_url": scene.slide_overlay_url,
                "event_buttons": scene.event_buttons,
                "info_display": scene.info_display,
                "utility": scene.utility,
                "hide": scene.hide,
                "display_tags": scene.display_tags,
                "displayTagValues": scene.displayTagValues,
                "displayTagMeta": scene.displayTagMeta,
                "vars": v,
                "timers": scene.runningTimers,
                "notes": scene.notes,
                "mqtt_server": scene.mqtt_server,
                "crossfade": scene.crossfade,
                "status": scene.getStatusString(),
            }
        else:
            data = {
                "alpha": scene.alpha,
                "active": scene.isActive(),
                "default_active": scene.default_active,
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

        d = {i: data[i] for i in data if (not keys or (i in keys))}
        d = snake_compat.camel_dict(d)

        self.linkSend(
            [
                "scenemeta",
                sceneid,
                d
            ]
        )

    def pushCueMeta(self, cueid: str):
        try:
            cue = cues[cueid]

            scene = cue.scene()
            if not scene:
                raise RuntimeError("Cue belongs to nonexistant scene")

            # Stuff that never gets saved, it's runtime UI stuff
            d2 = {
                "id": cueid,
                "name": cue.name,
                "next": cue.next_cue if cue.next_cue else "",
                "scene": scene.id,
                "number": cue.number / 1000.0,
                "prev": scene.getParent(cue.name),
                "hasLightingData": len(cue.values),
                "default_next": scene.getAfter(cue.name),
            }

            d = {}
            # All the stuff that's just a straight 1 to 1 copy of the attributes
            # are the same as whats in the save file
            for i in schemas.get_schema("chandler/cue")['properties']:
                d[i] = getattr(cue, i)

            # Important that d2 takes priority
            d.update(d2)

            # not metadata, sent separately
            d.pop('values')

            # Web frontend still uses ye olde camel case
            d = snake_compat.camel_dict(d)

            self.linkSend(
                [
                    "cuemeta",
                    cueid,
                    d,
                ]
            )
        except Exception:
            core.rl_log_exc("Error pushing cue data")
            print("cue data push error", cueid, traceback.format_exc())

    def pushCueMetaAttr(self, cueid: str, attr: str):
        "Be careful with this, some attributes can't be sent directly and need preprocessing"
        try:
            cue = cues[cueid]
            self.linkSend(["cuemetaattr", cueid, {attr: getattr(cue, attr)}])
        except Exception:
            core.rl_log_exc("Error pushing cue data")
            print("cue data push error", cueid, traceback.format_exc())

    def pushCueData(self, cueid: str):
        self.linkSend(["cuedata", cues[cueid].id, cues[cueid].values])

    def pushConfiguredUniverses(self):
        self.linkSend(["confuniverses", self.configuredUniverses])

    def pushCueList(self, scene: str):
        s = scenes.scenes[scene]
        x = list(s.cues.keys())
        # split list into messages of 100 because we don't want to exceed the widget send limit
        while x:
            self.linkSend(
                [
                    "scenecues",
                    scene,
                    {i: (s.cues[i].id, s.cues[i].number / 1000.0)
                     for i in x[:100]},
                ]
            )
            x = x[100:]

    def delscene(self, sc):
        i = None
        with core.lock:
            if sc in self.scenememory:
                i = self.scenememory.pop(sc)
        if i:
            i.stop()
            scenes.scenes_by_name.pop(i.name)
            self.linkSend(["del", i.id])

    def guiPush(self):
        with core.lock:
            for i in self.newDataFunctions:
                i(self)
            self.newDataFunctions = []
            snapshot = getUniverses()
            for i in snapshot:
                if self.id not in snapshot[i].statusChanged:
                    self.linkSend(
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
                    self.linkSend(
                        [
                            "cuedata",
                            self.scenememory[i].cue.id,
                            self.scenememory[i].cue.values,
                        ]
                    )

            for i in scenes.active_scenes:
                # Tell clients about any changed alpha values and stuff.
                if self.id not in i.hasNewInfo:
                    self.pushMeta(i.id)
                    i.hasNewInfo[self.id] = False
