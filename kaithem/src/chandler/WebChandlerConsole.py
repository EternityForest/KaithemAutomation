"""Don't waste too much time cleaning this.
The way forward is moving individual setters to setCueProperty and setGroupProperty"""

from __future__ import annotations

import copy
import os
import time
import traceback
from typing import Any

from icemedia import sound_player
from scullery import messagebus
from tinytag import TinyTag

from kaithem.api import tags
from kaithem.api.midi import list_midi_inputs
from kaithem.api.web import has_permission
from kaithem.api.widgets import APIWidget

from .. import assetlib, directories, scriptbindings, tagpoints
from ..alerts import getAlertState
from ..auth import canUserDoThis
from . import (
    ChandlerConsole,
    blendmodes,
    core,
    global_actions,
    groups,
    soundmanager,
    universes,
)
from .core import disallow_special
from .cue import fnToCueName
from .global_actions import cl_event
from .groups import Group, cues

once = [0]


def limitedTagsListing():
    # Make a list of all the tags,
    # Unless there's way too many
    # Then only list some of them

    v = {}
    for i in tagpoints.allTagsAtomic:
        if len(v) > 1024:
            break
        t = tagpoints.allTagsAtomic[i]()
        if t:
            v[i] = t.subtype
    return v


def listsoundfolder(path: str, extra_folders: list[str] = []):
    """return format [ [subfolderfolder,displayname],[subfolder2,displayname]  ],
    [[fn, fn_relative_to_its_configured_folder]...]

    Note we store things as relative paths excluding the folder,
    so users can move things around
    """
    soundfolders = core.getSoundFolders()

    if extra_folders:
        for i in extra_folders:
            soundfolders[i] = i
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
            match = i
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
    x = assetlib.assetpacks.ls(path)

    return (
        sorted(
            [
                [os.path.join(path, i), os.path.join(path, i)]
                for i in x
                if i.endswith("/")
            ]
        ),
        sorted(
            [
                [i, os.path.join(path, i)[len(match) :]]
                for i in x
                if not i.endswith("/")
            ]
        ),
    )


def searchPaths(s: str, paths: list[str]):
    """return is [[path, relpath]...]
    Where repath appended to path is the full path to the file
    and path is one of the input folder
    """
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
            relpath = dir[len(path) :]
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


class WebConsole(ChandlerConsole.ChandlerConsole):
    def __init__(self, name: str = "WebConsole"):
        self.link = None
        super().__init__(name)
        self.setup_link()
        # For the apps page link
        self.app: Any = None

    def setup_link(self):
        class WrappedLink(APIWidget):
            def on_new_subscriber(s, user: str, connection_id: str, **kw: Any):
                pass

            def on_subscriber_disconnected(
                s, user: str, connection_id: str, **kw: Any
            ) -> None:
                if canUserDoThis(user, "system_admin"):
                    self.ml_cl_check_autosave()
                return super().on_subscriber_disconnected(
                    user, connection_id, **kw
                )

        self.link = WrappedLink(
            id=f"WebChandlerConsole:{self.name}", echo=False
        )
        self.link.require("chandler_operator")
        self.link.echo = False
        # Bound method weakref nonsense prevention
        # also wrapping

        def f(x, y, z):
            try:
                self._onmsg(x, y, z)
            except Exception:
                core.rl_log_exc("Error handling command")
                self.pushEv(
                    "board.error",
                    "__this_lightboard__",
                    time.time(),
                    traceback.format_exc(8),
                )
                print(y, traceback.format_exc(8))

        self.onmsg = f
        self.link.attach2(self.onmsg)

        messagebus.subscribe("/system/alerts/state", self.push_sys_alerts)

    def push_sys_alerts(self, t: str, m: dict[str, Any]):
        self.linkSend(["alerts", m])

    def linkSend(self, data: list[Any]):
        if self.link:
            return self.link.send(data)

    def linkSendTo(self, data: list[Any], target: str):
        if self.link:
            return self.link.send_to(data, target)

    def send_fixture_assignments(self):
        f = copy.deepcopy(self.fixture_assignments)
        for i in f:
            ts = 0
            x = f[i].get("label_image", "")
            if x:
                try:
                    x = core.resolve_sound(x, self.media_folders)
                    ts = self.get_file_timestamp_if_exists(x)
                except Exception:
                    pass
                if ts:
                    f[i]["labelImageTimestamp"] = ts

        self.linkSend(["fixtureAssignments", f])

    @core.cl_context.entry_point
    def send_everything(self, sessionid: str):
        self.push_setup()
        self.push_setup()
        self.linkSend(["alerts", getAlertState()])
        self.linkSend(["soundfolders", self.media_folders])

        self.linkSend(["availableTags", limitedTagsListing()])

        self.linkSend(
            ["soundoutputs", [i for i in soundmanager.list_outputs()]]
        )

        self.linkSend(["midiInputs", list_midi_inputs()])

        self.linkSend(["blendModes", list(blendmodes.blendmodes.keys())])
        self.linkSend(["fixtureclasses", self.fixture_classes])

        sc = []

        for i in global_actions.shortcut_codes:
            if not i.isdecimal():
                sc.append(i)

        self.linkSend(["shortcuts", sc])

        for i in self.groups:
            s = self.groups[i]
            self.push_group_meta(i)
            if self.groups[i].cue:
                try:
                    self.pushCueMeta(self.groups[i].cue.id)
                except Exception:
                    print(traceback.format_exc())
            try:
                self.pushCueMeta(self.groups[i].cues["default"].id)
            except Exception:
                print(traceback.format_exc())

            try:
                for j in s.media_link.slideshow_telemetry:
                    # TODO send more stuff to just the target
                    self.linkSendTo(
                        [
                            "slideshow_telemetry",
                            j,
                            s.media_link.slideshow_telemetry[j],
                        ],
                        sessionid,
                    )
            except Exception:
                print(traceback.format_exc())

        for i in self.active_groups:
            # Tell clients about any changed alpha values and stuff.
            if i.id not in self.groups:
                self.push_group_meta(i.id)
        self.pushConfiguredUniverses()
        self.linkSend(["serports", getSerPorts()])

        shows = os.path.join(directories.vardir, "chandler", "shows")
        if os.path.isdir(shows):
            self.linkSend(
                [
                    "shows",
                    [
                        i
                        for i in os.listdir(shows)
                        if os.path.isdir(os.path.join(shows, i))
                    ],
                ]
            )

        setups = os.path.join(directories.vardir, "chandler", "setups")
        if os.path.isdir(setups):
            self.linkSend(
                [
                    "setups",
                    [
                        i
                        for i in os.listdir(setups)
                        if os.path.isdir(os.path.join(setups, i))
                    ],
                ]
            )

    def _onmsg(self, user: str, msg: list[Any], sessionid: str):
        # Getters

        cmd_name: str = str(msg[0])

        if cmd_name == "get_state":
            self.send_everything(sessionid)
            return

        elif cmd_name == "getcuedata":
            if msg[1] not in cues:
                self.linkSend(["cuedata", msg[1], None])
                return
            s = cues[msg[1]]
            self.linkSend(["cuedata", msg[1], s.values])
            self.pushCueMeta(msg[1])
            return

        elif cmd_name == "getfixtureclass":
            self.linkSend(
                ["fixtureclass", msg[1], self.fixture_classes[msg[1]]]
            )
            return

        elif cmd_name == "getfixtureclasses":
            self.linkSend(["fixtureclasses", self.fixture_classes])
            return

        elif cmd_name == "getcuemeta":
            if msg[1] not in cues:
                self.linkSend(["cuemeta", msg[1], None])
                return
            s = cues[msg[1]]
            self.pushCueMeta(msg[1])
            return

        # There's such a possibility for an iteration error if universes changes.
        # I'm not going to worry about it, this is only for the GUI list of universes.
        elif cmd_name == "getuniverses":
            self.push_setup()
            return

        elif cmd_name == "getserports":
            self.linkSend(["serports", getSerPorts()])
            return

        elif cmd_name == "getCommands":
            c = groups.rootContext.commands.scriptcommands
            ch_info = {}
            for i in c:
                f = c[i]
                ch_info[i] = scriptbindings.get_function_info(f)
            self.linkSend(["commands", ch_info])
            return

        elif cmd_name == "getconfuniverses":
            self.pushConfiguredUniverses()
            return

        elif cmd_name == "getcuehistory":
            self.linkSend(
                ["cuehistory", msg[1], groups.groups[msg[1]].cueHistory]
            )
            return

        elif cmd_name == "getfixtureassg":
            self.send_fixture_assignments()
            self.push_setup()
            return

        else:
            # Not in allowed read only commands, need chandler_operator below this point
            # Right now there's no separate chandler view, just operator
            if not has_permission("chandler_operator", user=user):
                if not has_permission("system_admin", user=user):
                    raise PermissionError(
                        cmd_name + "requires chandler_operator or system_admin"
                    )

        # User level runtime stuff that can't change config

        if cmd_name == "gotoNextCue":
            groups.groups[msg[1]].next_cue(cause="manual")
            return

        elif cmd_name == "gotoPreviousCue":
            groups.groups[msg[1]].prev_cue(cause="manual")
            return
        # TODO suspected unused
        elif cmd_name == "nextcuebyname":
            self.groups_by_name[msg[1]].next_cue(cause="manual")
            return

        elif cmd_name == "shortcut":

            def f():
                groups.cl_trigger_shortcut_code(msg[1])

            core.serialized_async_with_core_lock(f)
            return

        elif cmd_name == "addTimeToGroup":
            "Just this time, add a little extra"
            if groups.groups[msg[1]].cuelen:
                groups.groups[msg[1]].cuelen += float(msg[2]) * 60
                self.push_group_meta(msg[1])
            return

        elif cmd_name == "gotonext":
            if cues[msg[1]].next_cue:
                try:
                    s = cues[msg[1]].group()
                    if s:
                        s.next_cue(cause="manual")
                except Exception:
                    print(traceback.format_exc())
            return

        elif cmd_name == "testSoundCard":
            sound_player.test(output=msg[1])
            return

        elif cmd_name == "setalpha":
            groups.groups[msg[1]].setAlpha(msg[2])
            return

        elif cmd_name == "getcnames":
            self.pushchannelInfoByUniverseAndNumber(msg[1])
            return

        else:
            # Not in allowed runtime only commands
            if not has_permission("system_admin", user=user):
                raise PermissionError(cmd_name + "requires system_admin")

        ###

        if cmd_name == "preset":
            if msg[2] is None:
                self.fixture_presets.pop(msg[1], None)
            else:
                self.fixture_presets[msg[1]] = msg[2]
            self.linkSend(["fixturePresets", self.fixture_presets])

        elif cmd_name == "saveState":
            self.ml_cl_check_autosave()

        elif cmd_name == "addgroup":
            sc = Group(self, msg[1].strip())
            self.groups[sc.id] = sc
            self.push_group_meta(sc.id)
            sc.go()

        elif cmd_name == "setconfuniverses":
            if has_permission("system_admin", user=user):
                self.configured_universes = msg[1]
                self.cl_create_universes(self.configured_universes)
            else:
                raise RuntimeError("User does not have permission")

        elif cmd_name == "setfixtureclass":
            ch_info = []
            d = copy.deepcopy(msg[2])

            for i in d["channels"]:
                assert isinstance(i, dict)
                assert "name" in i
                assert "type" in i
                ch_info.append(i)

            d["channels"] = ch_info

            self.cl_set_fixture_type(msg[1], d)

        elif cmd_name == "setfixtureclassopz":
            x = []

            for i in msg[2]["channels"]:
                i = str(i)
                if i in ("red", "green", "blue", "white", "fog", "uv"):
                    x.append(
                        {
                            "name": i,
                            "type": i,
                        }
                    )

                elif i.startswith("knob"):
                    x.append(
                        {
                            "name": i,
                            "type": "generic",
                        }
                    )

                elif i == "intensity":
                    x.append(
                        {
                            "name": "dim",
                            "type": "intensity",
                        }
                    )
                elif i == "off":
                    x.append({"name": i, "type": "fixed", "value": 0})
                elif i == "on":
                    x.append({"name": i, "type": "fixed", "value": 255})
                elif i.isnumeric():
                    x.append({"name": i, "type": "fixed", "value": int(i)})
                elif i == "color":
                    x.append(
                        {
                            "name": "hue",
                            "type": "hue",
                        }
                    )
                else:
                    raise RuntimeError("Unknown channel type: " + i)

            fix = {"channels": x}

            self.fixture_classes[msg[1].replace("-", " ").replace("/", " ")] = (
                fix
            )
            self.cl_reload_fixture_assignment_data()
            self.linkSend(
                ["fixtureclass", msg[1], self.fixture_classes[msg[1]]]
            )

        elif cmd_name == "rmfixtureclass":
            del self.fixture_classes[msg[1]]
            self.cl_reload_fixture_assignment_data()
            self.linkSend(["fixtureclass", msg[1], None])

        elif cmd_name == "setFixtureAssignment":
            if not msg[2]["type"]:
                raise RuntimeError("Fixture type must be specified")
            self.fixture_assignments[msg[1]] = msg[2]
            self.send_fixture_assignments()
            self.cl_reload_fixture_assignment_data()

        elif cmd_name == "rmFixtureAssignment":
            del self.fixture_assignments[msg[1]]

            self.send_fixture_assignments()
            self.cl_reload_fixture_assignment_data()

        elif cmd_name == "clonecue":
            cues[msg[1]].clone(msg[2])

        elif cmd_name == "event":
            cl_event(msg[1], msg[2])

        elif cmd_name == "setnumber":
            cues[msg[1]].setNumber(msg[2])

        elif cmd_name == "setsoundout":
            cues[msg[1]].sound_output = msg[2]
            self.pushCueMeta(msg[1])

        elif cmd_name == "seteventbuttons":
            groups.groups[msg[1]].event_buttons = msg[2]
            self.push_group_meta(msg[1], keys={"event_buttons"})

        elif cmd_name == "setinfodisplay":
            groups.groups[msg[1]].info_display = msg[2]
            self.push_group_meta(msg[1], keys={"info_display"})

        elif cmd_name == "inputtagvalue":
            for i in groups.groups[msg[1]].display_tags:
                # Defensive programming, don't set a tag that wasn't ever actually configured
                if msg[2] == i[1]:
                    tags.existing_tag(msg[2]).value = msg[3]
                    return

        elif cmd_name == "setMqttServer":
            if has_permission("system_admin", user=user):
                groups.groups[msg[1]].setMqttServer(msg[2])
                self.push_group_meta(msg[1], keys={"mqtt_server"})

        elif cmd_name == "add_cueval":
            sc = cues[msg[1]].group()
            assert sc

            if hasattr(sc.lighting_manager.blendClass, "default_channel_value"):
                val = sc.lighting_manager.blendClass.default_channel_value
            else:
                val = 0

            hadVals = len(cues[msg[1]].values)

            # Allow number:name format, but we only want the name
            cues[msg[1]].set_value_immediate(
                msg[2], str(msg[3]).split(":")[-1], val
            )
            # Tell clients that now there is values in that cue
            if not hadVals:
                self.pushCueMeta(msg[1])

        elif cmd_name == "add_cuef":
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
                if i["type"] not in ("unused", "fixed"):
                    sc = cue.group()
                    assert sc
                    if hasattr(
                        sc.lighting_manager.blendClass, "default_channel_value"
                    ):
                        val = (
                            sc.lighting_manager.blendClass.default_channel_value
                        )
                    else:
                        val = 0
                    cue.set_value_immediate("@" + msg[2], i["name"], val)

            if length > 1:
                # Set the length as if it were a ficture property
                cue.set_value_immediate("@" + msg[2], "__length__", length)
                cue.set_value_immediate("@" + msg[2], "__spacing__", spacing)

                # The __dest__ channels represet the color at the end of the channel
                for i in x.channels:
                    if i["type"] not in ("unused", "fixed"):
                        sc = cue.group()
                        assert sc
                        if hasattr(
                            sc.lighting_manager.blendClass,
                            "default_channel_value",
                        ):
                            val = sc.lighting_manager.blendClass.default_channel_value
                        else:
                            val = 0
                        # i[0] is the name of the channel
                        cue.set_value_immediate(
                            "@" + msg[2], "__dest__." + str(i["name"]), val
                        )

            self.linkSend(["cuedata", msg[1], cue.values])
            self.pushCueMeta(msg[1])

        elif cmd_name == "rmcuef":
            s = cues[msg[1]]

            x = list(s.values[msg[2]].keys())

            for i in x:
                s.set_value_immediate(msg[2], i, None)
            self.linkSend(["cuedata", msg[1], s.values])
            self.pushCueMeta(msg[1])

        elif cmd_name == "listsoundfolder":
            lst = listsoundfolder(msg[1], extra_folders=self.media_folders)
            self.linkSend(["soundfolderlisting", msg[1], lst])

        elif cmd_name == "scv":
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

            cues[msg[1]].set_value_immediate(msg[2], ch, v)
            self.linkSend(["scv", msg[1], msg[2], ch, v])

            if v is None:
                # Count of values in the metadata changed
                self.pushCueMeta(msg[1])

        elif cmd_name == "setMusicVisualizations":
            groups.groups[msg[1]].setMusicVisualizations(msg[2])

        elif cmd_name == "tap":
            groups.groups[msg[1]].tap(msg[2])
        elif cmd_name == "setbpm":
            groups.groups[msg[1]].setBPM(msg[2])

        elif cmd_name == "setcrossfade":
            groups.groups[msg[1]].crossfade = float(msg[2] or 0)

        elif cmd_name == "add_cue":
            n = msg[2].strip()
            if msg[2] not in groups.groups[msg[1]].cues:
                groups.groups[msg[1]].add_cue(n, after=int(msg[3]))

        elif cmd_name == "rename_cue":
            if not msg[3]:
                return

            n = msg[2].strip()
            n2 = msg[3].strip()

            groups.groups[msg[1]].rename_cue(n, n2)

        elif cmd_name == "searchsounds":
            self.linkSend(
                [
                    "soundsearchresults",
                    msg[1],
                    searchPaths(
                        msg[1], core.getSoundFolders(self.media_folders)
                    ),
                ]
            )

        elif cmd_name == "mediaLinkCommand":
            self.groups_by_name[msg[1]].media_link_socket.send_to(
                msg[3], msg[2]
            )
            return

        elif cmd_name == "newFromSound":
            bn = os.path.basename(msg[2])
            bn = fnToCueName(bn)
            try:
                media_tags = TinyTag.get(msg[2])
                if media_tags.artist and media_tags.title:
                    bn = media_tags.title + " ~ " + media_tags.artist
            except Exception:
                print(traceback.format_exc())

            bn = disallow_special(bn, "_~", replaceMode=" ")
            if bn not in groups.groups[msg[1]].cues:
                groups.groups[msg[1]].add_cue(bn)
                groups.groups[msg[1]].cues[bn].rel_length = True
                groups.groups[msg[1]].cues[bn].length = 0.01

                soundfolders = core.getSoundFolders(
                    extra_folders=self.media_folders
                )
                s = None
                for i in soundfolders:
                    s = msg[2]
                    # Make paths relative.
                    if not i.endswith("/"):
                        i = i + "/"
                    if s.startswith(i):
                        s = s[len(i) :]
                        break
                if not s:
                    raise RuntimeError("Unknown, linter said was possible")
                groups.groups[msg[1]].cues[bn].sound = s
                groups.groups[msg[1]].cues[bn].named_for_sound = True

                self.pushCueMeta(groups.groups[msg[1]].cues[bn].id)

        elif cmd_name == "newFromSlide":
            bn = os.path.basename(msg[2])
            bn = fnToCueName(bn)

            bn = disallow_special(bn, "_~", replaceMode=" ")
            if bn not in groups.groups[msg[1]].cues:
                groups.groups[msg[1]].add_cue(bn)
                soundfolders = core.getSoundFolders(
                    extra_folders=self.media_folders
                )
                assert soundfolders
                s = ""
                for i in soundfolders:
                    s = msg[2]
                    # Make paths relative.
                    if not i.endswith("/"):
                        i = i + "/"
                    if s.startswith(i):
                        s = s[len(i) :]
                        break
                assert s
                groups.groups[msg[1]].cues[bn].slide = s

                if not groups.is_static_media(s):
                    groups.groups[msg[1]].cues[bn].rel_length = True
                    groups.groups[msg[1]].cues[bn].length = 0.01

                self.pushCueMeta(groups.groups[msg[1]].cues[bn].id)

        elif cmd_name == "rmcue":
            c = cues[msg[1]]
            gr = c.group()
            assert gr
            gr.rmCue(c.id)

        elif cmd_name == "setmqttfeature":
            groups.groups[msg[1]].setMQTTFeature(msg[2], msg[3])
            self.push_group_meta(msg[1], keys={"mqtt_sync_features"})

        elif cmd_name == "setgroupslideoverlay":
            groups.groups[msg[1]].slide_overlay_url = msg[2]
            self.push_group_meta(msg[1], keys={"slide_overlay_url"})

        elif cmd_name == "setgroupcommandtag":
            groups.groups[msg[1]].set_command_tag(msg[2])

            self.push_group_meta(msg[1], keys={"command_tag"})

        elif cmd_name == "setnext":
            if msg[2][:1024]:
                c = msg[2][:1024].strip()
            else:
                c = None
            cues[msg[1]].next_cue = c or ""
            self.pushCueMeta(msg[1])

        elif cmd_name == "setprobability":
            cues[msg[1]].probability = msg[2][:2048]
            self.pushCueMeta(msg[1])

        elif cmd_name == "setgroupname":
            groups.groups[msg[1]].setName(msg[2])

        elif cmd_name == "setsoundfolders":
            self.media_folders = [
                i.strip().replace("\r", "").replace("\t", " ")
                for i in msg[1].split("\n")
                if i
            ]

        else:
            raise ValueError("Unrecognized Command " + str(cmd_name))
