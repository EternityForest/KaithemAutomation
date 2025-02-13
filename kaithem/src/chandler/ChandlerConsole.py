import copy
import gc
import os
import threading
import time
import traceback
import uuid
import weakref
from typing import Any, Dict, Iterable, List, Optional, Set

import beartype
import yaml
from scullery import messagebus, scheduling, snake_compat, workers

from kaithem.api.modules import modules_lock

# The frontend's ephemeral state is using CamelCase conventions for now
from .. import schemas, unitsofmeasure
from . import (
    blendmodes,
    console_abc,
    core,
    fixtureslib,
    group_lighting,
    groups,
    persistance,
    soundmanager,
    universes,
)
from .core import logger
from .global_actions import async_event
from .groups import Group, cues
from .universes import getUniverse, getUniverses


class ChandlerConsole(console_abc.Console_ABC):
    "Represents a web GUI board. Pretty much the whole GUI app is part of this class"

    def __init__(self, name: str = "ChandlerConsole") -> None:
        super().__init__()

        self.id = uuid.uuid4().hex

        for i in "./\\*?\"<>|'":
            if i in name:
                raise ValueError(f"Name cannot contain {i}")

        self.name = name

        # mutable and immutable versions of the active groups list.
        self.groups_by_name: weakref.WeakValueDictionary[str, Group] = (
            weakref.WeakValueDictionary()
        )

        self._active_groups: list[Group] = []
        self.active_groups: list[Group] = []

        # This light board's group memory, or the set of groups 'owned' by this board.
        self.groups: Dict[str, Group] = {}

        self.media_folders: list[str] = []

        # For change detection in groups. Tuple is folder, file indicating where it should go,
        # as would be passed to saveasfiles
        self.last_saved_version: dict[str, Any] = {}

        self.configured_universes: Dict[str, dict[str, Any]] = {}
        self.fixture_assignments: Dict[str, Any] = {}
        self.fixture_presets: Dict[str, dict[str, Any]] = {}

        with open(
            os.path.join(os.path.dirname(__file__), "fixture_presets.yaml")
        ) as fp:
            self.fixture_presets = yaml.safe_load(fp)

        self.fixtures: Dict[str, universes.Fixture] = {}

        self.universe_objects: Dict[str, universes.Universe] = {}
        self.fixture_classes: Dict[str, Any] = {}
        c = copy.deepcopy(fixtureslib.genericFixtureClasses)

        for i in c:
            self.fixture_classes[i] = c[i]

        self.initialized = False

        def f(t, m):
            if not m.clientName.startswith("kplayer"):
                time.sleep(0.1)
                self.on_soundcards_changed()

        self.callback_jackports = f
        messagebus.subscribe("/system/jack/newport", f)
        messagebus.subscribe("/system/jack/delport", f)

        # Use only for stuff in background threads, to avoid pileups that clog the
        # Whole worker pool
        self.gui_send_lock = threading.Lock()

        # For logging ratelimiting
        self.last_logged_gui_send_error = 0
        self.fixture_errors = ""

        self.autosave_checker = scheduling.scheduler.every(
            self.ml_cl_check_autosave, 10 * 60
        )

        def dummy(data: dict[str, Any]):
            logger.error("No save backend present")

        self.ml_save_callback = dummy
        self.should_run = True

    def on_soundcards_changed(self):
        self.linkSend(
            ["soundoutputs", [i for i in soundmanager.list_outputs()]]
        )

    @core.cl_context.required
    def cl_close(self):
        for i in self.groups:
            self.groups[i].stop()
            self.groups[i].close()
        self.groups = {}

        for i in self.configured_universes:
            if not self.configured_universes[i]["type"] == "null":
                try:
                    u = universes.universes[i]()
                    if u is not None:
                        u.close()
                except Exception:
                    logger.exception("Could not close universe")

        try:
            self.autosave_checker.unregister()
        except Exception:
            logger.exception("Could not close correctly")

        self.cl_delete_assigned_fixtures()

    @core.cl_context.entry_point
    def cl_load_project(self, data: dict[str, Any]):
        for i in self.groups:
            self.groups[i].stop()
            self.groups[i].close()
        self.groups = {}

        for i in self.configured_universes:
            try:
                u = universes.universes[i]()
                if u is not None:
                    u.close()
            except Exception:
                logger.exception("Could not close universe")

        if "setup" in data:
            data2 = data["setup"]

            self.configured_universes = data2["configured_universes"]
            self.fixture_classes = {}
            ft = data2["fixture_types"]
            for i in ft:
                assert isinstance(ft[i], dict)
                self.fixture_classes[i] = ft[i]

            self.fixture_assignments = data2["fixture_assignments"]

            x = data2.get("fixture_presets", {})
            self.fixture_presets = {i: x[i] for i in x}

            default_media_folders: list[str] = []

            if os.path.exists(os.path.expanduser("~/Music")):
                default_media_folders.append(os.path.expanduser("~/Music"))
            if os.path.exists(os.path.expanduser("~/Videos")):
                default_media_folders.append(os.path.expanduser("~/Videos"))
            if os.path.exists(os.path.expanduser("~/Pictures")):
                default_media_folders.append(os.path.expanduser("~/Pictures"))

            self.media_folders = (
                data2.get("media_folders", default_media_folders) or []
            )

            try:
                self.cl_create_universes(self.configured_universes)
            except Exception:
                logger.exception("Error creating universes")
                print(traceback.format_exc(6))

            self.cl_reload_fixture_assignment_data()

        if "scenes" in data:
            data["groups"] = data.pop("scenes")

        if "groups" in data:
            d = data["groups"]

            self.cl_load_groups_from_dict(d)
            self.linkSend(["refreshPage", self.fixture_assignments])

    @core.cl_context.entry_point
    def cl_setup(self, project: dict[str, Any]):
        console_abc.Console_ABC.cl_setup(self, project)
        self.cl_load_project(project)
        self.initialized = True

    @core.cl_context.entry_point
    def cl_delete_assigned_fixtures(self):
        """Clear the fixture objects without actually touching the config
        that generates them"""
        try:
            for i in self.fixtures:
                self.fixtures[i].cl_assign(None, None)
                self.fixtures[i].rm()
        except Exception:
            self.fixture_errors += (
                "Error deleting old assignments:\n" + traceback.format_exc()
            )
            print(traceback.format_exc())

        try:
            del i  # type: ignore
        except Exception:
            pass

    @core.cl_context.entry_point
    def cl_reload_fixture_assignment_data(self):
        self.fixture_errors = ""
        self.cl_delete_assigned_fixtures()
        self.fixtures = {}
        for key, i in self.fixture_assignments.items():
            try:
                if not i["name"] == key:
                    raise RuntimeError("Name does not match key?")
                x = universes.Fixture(
                    i["name"], self.fixture_classes[i["type"]]
                )
                self.fixtures[i["name"]] = x
                self.fixtures[i["name"]].cl_assign(
                    i["universe"], int(i["addr"])
                )
            except Exception:
                logger.exception("Error setting up fixture")
                print(traceback.format_exc())
                self.fixture_errors += str(i) + "\n" + traceback.format_exc()

        for u in universes.universes:
            self.pushchannelInfoByUniverseAndNumber(u)

        for f in universes.fixtures:
            if f:
                self.pushchannelInfoByUniverseAndNumber("@" + f)

        self.fixture_errors = self.fixture_errors or "No Errors!"
        self.push_setup()
        group_lighting.refresh_all_group_lighting()

    @core.cl_context.entry_point
    def cl_create_universes(self, data: dict[str, Any]):
        """Cl because of the universes object init"""
        assert isinstance(data, Dict)
        for i in self.universe_objects:
            self.universe_objects[i].close()

        self.universe_objects = {}
        import gc

        gc.collect()
        universeObjects: dict[str, universes.Universe] = {}
        u: Dict[str, Dict[Any, Any]] = data
        for i in u:
            if u[i]["type"] == "null":
                continue

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
            else:
                async_event("system.error", "No universe type: " + u[i]["type"])
        self.universe_objects = universeObjects

        try:
            universes.cl_discover_color_tag_devices()
        except Exception:
            async_event("system.error", traceback.format_exc())
            print(traceback.format_exc())

        self.push_setup()

    @core.cl_context.entry_point
    def cl_import_from_resource_file(
        self,
        data_str: str,
        fixture_types: bool = True,
        universes: bool = True,
        fixture_assignments: bool = True,
        fixture_presets: bool = True,
    ):
        data = yaml.load(data_str, Loader=yaml.SafeLoader)
        data = snake_compat.snakify_dict_keys(data)

        if "project" in data:
            data = data["project"]
            if "setup" in data:
                data = data["setup"]

        if fixture_types:
            if "fixture_types" in data:
                for i in data["fixture_types"]:
                    self.cl_set_fixture_type(i, data["fixture_types"][i])

        if universes:
            if "universes" in data:
                for i in data["universes"]:
                    self.configured_universes[i] = data["universes"][i]
                self.cl_create_universes(self.configured_universes)

            if "configured_universes" in data:
                for i in data["configured_universes"]:
                    self.configured_universes[i] = data["configured_universes"][
                        i
                    ]
                self.cl_create_universes(self.configured_universes)

        if fixture_assignments:
            # Compatibility with a legacy typo
            if "fixures" in data:
                data["fixture_assignments"] = data["fixures"]

            if "fixtures" in data:
                data["fixture_assignments"] = data["fixtures"]

            if "fixture_assignments" in data:
                for i in data["fixture_assignments"]:
                    self.fixture_assignments[i] = data["fixture_assignments"][i]

                self.cl_reload_fixture_assignment_data()

        if fixture_presets:
            if "fixture_presets" in data:
                x = data["fixture_presets"]
                fp = {i: x[i] for i in x}

                for i in fp:
                    self.fixture_presets[i] = fp[i]

        self.push_setup()

    def get_file_timestamp_if_exists(self, filename: str) -> str:
        try:
            if not filename:
                return ""
            filename = core.resolve_sound(
                filename, extra_folders=self.media_folders
            )
            if not filename:
                return ""
            if os.path.isfile(filename):
                return str(os.stat(filename).st_mtime * 10)
            else:
                return ""
        except (FileNotFoundError, ValueError):
            return ""
        except Exception:
            logger.exception("Failed to get file timestamp")
            return ""

    @core.cl_context.entry_point
    def cl_get_setup_file(self):
        return {
            "fixture_types": self.fixture_classes,
            "configured_universes": self.configured_universes,
            "fixture_assignments": self.fixture_assignments,
            "fixture_presets": self.fixture_presets,
            "media_folders": self.media_folders,
        }

    @core.cl_context.entry_point
    def cl_load_group_file(
        self,
        data_str: str,
        filename: str,
        errs: bool = False,
        clear_old: bool = True,
    ):
        data = yaml.load(data_str, Loader=yaml.SafeLoader)

        data = snake_compat.snakify_dict_keys(data)

        # Detect if the user is trying to upload a single groupfile,
        # if so, wrap it in a multi-dict of groups to keep the reading code
        # The same for both
        if "uuid" in data and isinstance(data["uuid"], str):
            # Remove the .yaml
            data = {filename[:-5]: data}

        g = copy.copy(self.groups)

        if clear_old:
            for i in g:
                if clear_old or (i in data):
                    g[i].stop()
                    g[i].close()

            self.groups = {}

        self.cl_load_groups_from_dict(data, errs)

    @core.cl_context.entry_point
    def cl_load_groups_from_dict(
        self, data: dict[str, Any], errs: bool = False
    ):
        data = copy.deepcopy(data)
        data = snake_compat.snakify_dict_keys(data)

        # Note that validation could include integer keys, but we handle that
        for i in data:
            try:
                schemas.validate("chandler/group", data[i])
            except Exception:
                logger.exception(f"Error Validating group {i}, loading anyway")

            cues = data[i].get("cues", {})
            for j in cues:
                try:
                    schemas.validate("chandler/cue", cues[j])
                except Exception:
                    logger.exception(
                        f"Error Validating cue {j}, loading anyway"
                    )

        for i in data:
            # New versions don't have a name key at all, the name is the key
            if "name" in data[i]:
                pass
            else:
                data[i]["name"] = i
            n = data[i]["name"]

            # Delete existing groups we own
            if n in self.groups_by_name:
                old_id = self.groups_by_name[n].id
                if old_id in self.groups:
                    self.groups[old_id].stop()
                    self.groups[old_id].close()
                    try:
                        del self.groups[old_id]
                    except KeyError:
                        pass
                else:
                    raise ValueError(
                        "Group "
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

                s = Group(self, id=uuid, active=x, default_active=x, **data[i])

                self.groups[uuid] = s
                if x:
                    s.go()
                    s.poll_again_flag = True
                    s.lighting_manager.refresh()
            except Exception:
                if not errs:
                    logger.exception(
                        "Failed to load group "
                        + str(i)
                        + " "
                        + str(data[i].get("name", ""))
                    )
                    print(
                        "Failed to load group "
                        + str(i)
                        + " "
                        + str(data[i].get("name", ""))
                        + ": "
                        + traceback.format_exc(3)
                    )
                else:
                    raise

    @beartype.beartype
    def addGroup(self, group: Group):
        self.groups[group.id] = group

    @beartype.beartype
    def rmGroup(self, group: Group):
        try:
            del self.groups[group.id]
        except Exception:
            print(traceback.format_exc())

    def pushEv(self, event: str, target, time_unix=None, value=None, info=""):
        # TODO: Do we want a better way of handling this? We don't want to clog up the semi-re
        def f():
            if self.gui_send_lock.acquire(timeout=5):
                try:
                    self.linkSend(
                        [
                            "event",
                            [
                                event,
                                target,
                                unitsofmeasure.strftime(
                                    time_unix or time.time()
                                ),
                                value,
                                info,
                            ],
                        ]
                    )
                except Exception:
                    if time.monotonic() - self.last_logged_gui_send_error < 60:
                        logger.exception(
                            "Error when reporting event. (Log ratelimit: 30)"
                        )
                        self.last_logged_gui_send_error = time.monotonic()
                finally:
                    self.gui_send_lock.release()
            else:
                if time.monotonic() - self.last_logged_gui_send_error < 60:
                    logger.error(
                        "Timeout getting lock to push event. (Log ratelimit: 60)"
                    )
                    self.last_logged_gui_send_error = time.monotonic()

        workers.do(f)

    def push_setup(self):
        ps = copy.deepcopy(self.fixture_presets)
        for i in ps:
            ps[i]["labelImageTimestamp"] = self.get_file_timestamp_if_exists(
                ps[i].get("label_image", "")
            )
        "Errors in fixture list"
        self.linkSend(["ferrs", self.fixture_errors])
        self.linkSend(["fixtureAssignments", self.fixture_assignments])
        self.linkSend(["fixturePresets", ps])

        snapshot = getUniverses()

        # We don't need to send status data for every tag point universe
        # and the frontend doesn't even know how to handle stuff with slashes
        # in the name like tags have.
        # TODO: this special casng feels hacky
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
                    if not isinstance(snapshot[i], universes.OneTagpoint)
                },
            ]
        )

    @core.cl_context.entry_point
    def cl_get_groups(self):
        "Return serializable version of groups list"
        sd = {}
        for i in self.groups:
            x = self.groups[i]
            sd[x.name] = x.toDict()

        return sd

    def ml_cl_check_autosave(self, sync=False):
        """Only call sync if you already have the modules lock"""
        if self.initialized:
            self.ml_cl_save_project_data()

    @core.cl_context.entry_point
    def cl_get_project_data(self):
        project_file: dict[str, Any] = {
            "groups": self.cl_get_groups(),
            "setup": self.cl_get_setup_file(),
        }
        return copy.deepcopy(project_file)

    def ml_cl_save_project_data(self):
        """Only use sync if you have the modules lock"""
        with modules_lock:
            with core.cl_context:
                project_file = self.cl_get_project_data()

                if self.last_saved_version == project_file:
                    return

                self.last_saved_version = project_file
                self.ml_save_callback(project_file)

    def pushchannelInfoByUniverseAndNumber(self, u: str):
        "This has expanded to push more data than names"
        if not u[0] == "@":
            universe_object = getUniverse(u)

            if not universe_object:
                return

            d = {}

            for i in universe_object.channels:
                fixture = universe_object.channels[i]()
                if not fixture:
                    continue

                if not fixture.startAddress:
                    continue

                data = [
                    fixture.name,
                    fixture.channels[i - fixture.startAddress],
                ]
                d[i] = data
            self.linkSend(["cnames", u, d])
        else:
            d = {}
            if u[1:] in universes.fixtures:
                f = universes.fixtures[u[1:]]()
                if f:
                    for i in range(len(f.channels)):
                        d[f.channels[i]["name"]] = [u[1:], f.channels[i]]
            self.linkSend(["cnames", u, d])

    def pushPreset(self, preset):
        preset_data = copy.deepcopy(self.fixture_presets.get(preset, {}))
        preset_data["labelImageTimestamp"] = self.get_file_timestamp_if_exists(
            preset_data.get("label_image", "")
        )
        self.linkSend(["preset", preset, preset_data])

    def push_group_meta(
        self,
        groupid: str,
        statusOnly: bool = False,
        keys: Optional[
            List[Any] | Set[Any] | Dict[Any, Any] | Iterable[str]
        ] = None,
    ):
        "Statusonly=only the stuff relevant to a cue change. Keys is iterable of what to send, or None for all"
        group = self.groups.get(groupid, None)
        # Race condition of deleted groups
        if not group:
            return

        v = {}
        if group.script_context:
            try:
                for j in group.script_context.variables:
                    if not j == "_":
                        if isinstance(
                            group.script_context.variables[j],
                            (int, float, str, bool),
                        ):
                            v[j] = group.script_context.variables[j]

                        else:
                            v[j] = "__PYTHONDATA__"
            except Exception:
                print(traceback.format_exc())

        if not statusOnly:
            data: Dict[str, Any] = {
                # These dynamic runtime vars aren't part of the schema for stuff that gets saved
                "status": group.getStatusString(),
                "blendDesc": blendmodes.getblenddesc(group.blend),
                "cue": group.cue.id if group.cue else group.cues["default"].id,
                "ext": groupid not in self.groups,
                "id": groupid,
                "uuid": groupid,
                "vars": v,
                "timers": group.runningTimers,
                "entered_cue": group.entered_cue,
                "displayTagValues": group.display_tag_values,
                "displayTagMeta": group.display_tag_meta,
                "cuelen": group.cuelen,
                "name": group.name,
                # Placeholder because cues are separate in the web thing.
                "cues": {},
                "started": group.started,
                # TODO ?? this is confusing because in the files and schemas alpha means
                # default but everywhere else it means the current.  Maybe unify them.
                # Maybe unify active default too
                "alpha": group.alpha,
                "default_alpha": group.default_alpha,
                "default_active": group.default_active,
                "active": group.is_active(),
            }

            if (
                group.next_scheduled_cue
                and group.next_scheduled_cue.scheduler_object
            ):
                # Too race conditiony feeling with this property access chain TODO?
                try:
                    data["next_scheduled_cue"] = [
                        group.next_scheduled_cue.name,
                        group.next_scheduled_cue.scheduler_object.time,
                    ]
                except Exception:
                    print(traceback.format_exc())

            # Everything else should by as it is in the schema
            for i in groups.group_schema["properties"]:
                if i not in data:
                    data[i] = getattr(group, i)

        else:
            data = {
                "alpha": group.alpha,
                "id": groupid,
                "active": group.is_active(),
                "default_active": group.default_active,
                "displayTagValues": group.display_tag_values,
                "entered_cue": group.entered_cue,
                "cue": group.cue.id if group.cue else group.cues["default"].id,
                "cuelen": group.cuelen,
                "status": group.getStatusString(),
            }

        # TODO this do everything then filter approach seems excessively slow.
        # Maybe keep it for simplicity but use it less
        if keys:
            for i in keys:
                if i not in data:
                    raise KeyError(i)

        d = {i: data[i] for i in data if (not keys or (i in keys))}
        d = snake_compat.camelify_dict_keys(d)

        self.linkSend(["groupmeta", groupid, d])

    def pushCueMeta(self, cueid: str):
        try:
            cue = cues[cueid]

            d = cue.get_ui_data()

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

    def pushCueData(self, cueid: str):
        self.linkSend(["cuedata", cues[cueid].id, cues[cueid].values])

    def pushConfiguredUniverses(self):
        self.linkSend(["confuniverses", self.configured_universes])

    @core.cl_context.entry_point
    def cl_set_fixture_type(self, type: str, library: dict[str, Any]):
        self.fixture_classes[type] = library
        self.cl_reload_fixture_assignment_data()
        self.linkSend(["fixtureclass", type, self.fixture_classes[type]])

    @core.cl_context.entry_point
    def cl_del_group(self, sc):
        i = None
        if sc in self.groups:
            i = self.groups.pop(sc)
        if i:
            i.stop()
            self.groups_by_name.pop(i.name)
            self.linkSend(["del", i.id])
            persistance.del_checkpoint(i.id)

    @core.cl_context.entry_point
    def cl_add_to_active_groups(self, group: Group):
        if group not in self._active_groups:
            self._active_groups.append(group)

        self._active_groups = sorted(
            self._active_groups, key=lambda k: (k.priority, k.started)
        )
        self.active_groups = self._active_groups[:]

    @core.cl_context.entry_point
    def cl_rm_from_active_groups(self, group: Group):
        if group in self._active_groups:
            self._active_groups.remove(group)
            self.active_groups = self._active_groups[:]

        gc.collect()
        time.sleep(0.01)
        gc.collect()
        gc.collect()

    @core.cl_context.entry_point
    def cl_update_group_priorities(self):
        self._active_groups = sorted(
            self._active_groups, key=lambda k: (k.priority, k.started)
        )
        self.active_groups = self._active_groups[:]

    @core.cl_context.required
    def cl_gui_push(self, universes_snapshot):
        "Snapshot is a list of all universes because the getter for that is slow"
        while self.newDataFunctions:
            self.newDataFunctions.pop(0)(self)

        for i in universes_snapshot:
            if self.id not in universes_snapshot[i].statusChanged:
                # TODO just resend the whole universe object to prevent nuisance errors
                self.linkSend(
                    [
                        "universe_status",
                        i,
                        universes_snapshot[i].status,
                        universes_snapshot[i].ok,
                        universes_snapshot[i].telemetry,
                    ]
                )
                universes_snapshot[i].statusChanged[self.id] = True

        for i in self.groups:
            # Tell clients about any changed alpha values and stuff.
            if self.id not in self.groups[i].metadata_already_pushed_by:
                self.push_group_meta(i, statusOnly=True)
                self.groups[i].metadata_already_pushed_by[self.id] = False

        for i in self.active_groups:
            # Tell clients about any changed alpha values and stuff.
            if self.id not in i.metadata_already_pushed_by:
                self.push_group_meta(i.id)
                i.metadata_already_pushed_by[self.id] = False
