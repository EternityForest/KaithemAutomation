from __future__ import annotations
import os
import traceback
import time
from typing import List, Any, Dict
from tinytag import TinyTag

from . import ChandlerConsole

from ..alerts import getAlertState
from .. import snake_compat

from ..kaithemobj import kaithem
from .scenes import Scene, cues, event
from . import scenes
from . import core
from . import universes
from .core import disallow_special


def listsoundfolder(path: str):
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


def searchPaths(s: str, paths: list[str]):
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


class WebConsole(ChandlerConsole.ChandlerConsole):

    def __init__(self):
        self.link = None
        super().__init__()
        self.setup_link()

    def setup_link(self):

        class WrappedLink(kaithem.widget.APIWidget):
            def onNewSubscriber(s, user, connection_id, **kw):
                self.send_everything(connection_id)
            
        self.link = WrappedLink()
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

        kaithem.message.subscribe('/system/alerts/state', self.push_sys_alerts)

    def push_sys_alerts(self, t: str, m: dict[str, Any]):
        self.linkSend(['alerts', m])

    def linkSend(self, data: List[Any]):
        if self.link:
            return self.link.send(data)

    def linkSendTo(self, data: List[Any], target: str):
        if self.link:
            return self.link.sendTo(data, target)
    
    def send_everything(self, sessionid):
        with core.lock:
            self.linkSend(["presets", self.presets])
            self.pushUniverses()
            self.pushfixtures()
            self.linkSend(['alerts', getAlertState()])
            self.linkSend(['soundfolders', core.config.get('soundFolders')])

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
                    for j in s.slideshow_telemetry:
                        # TODO send more stuff to just the target
                        self.linkSendTo(['slideshow_telemetry', j, s.slideshow_telemetry[j]], sessionid)
                except Exception:
                    print(traceback.format_exc())

                try:
                    for j in self.scenememory[i].cues:
                        self.pushCueMeta(
                            self.scenememory[i].cues[j].id)
                except Exception:
                    print(traceback.format_exc())

            for i in scenes.active_scenes:
                # Tell clients about any changed alpha values and stuff.
                if i.id not in self.scenememory:
                    self.pushMeta(i.id)
            self.pushConfiguredUniverses()
            self.linkSend(["serports", getSerPorts()])

            shows = os.path.join(kaithem.misc.vardir, "chandler", "shows")
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

            setups = os.path.join(
                kaithem.misc.vardir, "chandler", "setups")
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

        
    def _onmsg(self, user: str, msg: List[Any], sessionid: str):
        # Getters

        cmd_name: str = str(msg[0])

        # read only commands

        if cmd_name == "gsd":
            # Could be long-running, so we offload to a workerthread
            # Used to be get scene data, Now its a general get everything to show pags thing
            def f():
                s = scenes.scenes[msg[1]]
                self.pushCueList(s.id)
                self.pushMeta(msg[1])
                self.pushfixtures()
            kaithem.misc.do(f)
            return

        elif cmd_name == "getallcuemeta":

            def f():
                for i in scenes.scenes[msg[1]].cues:
                    self.pushCueMeta(scenes.scenes[msg[1]].cues[i].id)

            kaithem.misc.do(f)
            return

        elif cmd_name == "getcuedata":
            s = cues[msg[1]]
            self.linkSend(["cuedata", msg[1], s.values])
            self.pushCueMeta(msg[1])
            return

        elif cmd_name == "getfixtureclass":
            self.linkSend(
                ["fixtureclass", msg[1], self.fixture_classes[msg[1]]])
            return

        elif cmd_name == "getfixtureclasses":
            # Send placeholder lists
            self.linkSend(
                ["fixtureclasses", {i: []
                                    for i in self.fixture_classes.keys()}]
            )
            return

        elif cmd_name == "getcuemeta":
            s = cues[msg[1]]
            self.pushCueMeta(msg[1])
            return

        elif cmd_name == "gasd":
            #Get All State Data, used to get all scene data
            self.send_everything(sessionid)
            return

        # There's such a possibility for an iteration error if universes changes.
        # I'm not going to worry about it, this is only for the GUI list of universes.
        elif cmd_name == "getuniverses":
            self.pushUniverses()
            return

        elif cmd_name == "getserports":
            self.linkSend(["serports", getSerPorts()])
            return

        elif cmd_name == "getCommands":
            c = scenes.rootContext.commands.scriptcommands
            commandInfo = {}
            for i in c:
                f = c[i]
                commandInfo[i] = kaithem.chandlerscript.get_function_info(f)
            self.linkSend(["commands", commandInfo])
            return

        elif cmd_name == "getconfuniverses":
            self.pushConfiguredUniverses()
            return

        elif cmd_name == "getcuehistory":
            self.linkSend(
                ["cuehistory", msg[1], scenes.scenes[msg[1]].cueHistory])
            return

        elif cmd_name == "getfixtureassg":
            self.linkSend(["fixtureAssignments", self.fixture_assignments])
            self.pushfixtures()
            return

        else:
            # Not in allowed read only commands, need chandler_operator below this point
            # Right now there's no separate chandler view, just operator
            if not kaithem.users.check_permission(user, 'chandler_operator'):
                if not kaithem.users.check_permission(user, 'system_admin'):
                    raise PermissionError(cmd_name + "requires chandler_operator or system_admin")

        # User level runtime stuff that can't change config

        if cmd_name == "jumptocue":
            if not cues[msg[1]].scene().active:
                cues[msg[1]].scene().go()

            cues[msg[1]].scene().goto_cue(cues[msg[1]].name, cause="manual")
            return

        elif cmd_name == "jumpbyname":
            scenes.scenes_by_name[msg[1]].goto_cue(msg[2], cause="manual")
            return

        elif cmd_name == "nextcue":
            scenes.scenes[msg[1]].next_cue(cause="manual")
            return

        elif cmd_name == "prevcue":
            scenes.scenes[msg[1]].prev_cue(cause="manual")
            return

        elif cmd_name == "nextcuebyname":
            scenes.scenes_by_name[msg[1]].next_cue(cause="manual")
            return

        elif cmd_name == "shortcut":
            scenes.shortcutCode(msg[1])
            return

        elif cmd_name == "gotonext":
            if cues[msg[1]].next_cue:
                try:
                    s = cues[msg[1]].scene()
                    if s:
                        s.next_cue(cause="manual")
                except Exception:
                    print(traceback.format_exc())
            return

        elif cmd_name == "go":
            scenes.scenes[msg[1]].go()
            self.pushMeta(msg[1])
            return

        elif cmd_name == "gobyname":
            scenes.scenes_by_name[msg[1]].go()
            self.pushMeta(scenes.scenes_by_name[msg[1]].id)
            return

        elif cmd_name == "stopbyname":
            scenes.scenes_by_name[msg[1]].stop()
            self.pushMeta(msg[1], statusOnly=True)
            return

        elif cmd_name == "stop":
            x = scenes.scenes[msg[1]]
            x.stop()
            self.pushMeta(msg[1], statusOnly=True)
            return

        elif cmd_name == "testSoundCard":
            kaithem.sound.ogg_test(output=msg[1])
            return

        elif cmd_name == "setalpha":
            scenes.scenes[msg[1]].setAlpha(msg[2])
            return

        elif cmd_name == "getcnames":
            self.pushChannelNames(msg[1])
            return

        else:
            # Not in allowed runtime only commands
            if not kaithem.users.check_permission(user, 'system_admin'):
                raise PermissionError(cmd_name + "requires system_admin")

        ###

        if cmd_name == "preset":
            if msg[2] is None:
                self.presets.pop(msg[2], None)
            else:
                self.presets[msg[1]] = msg[2]

        elif cmd_name == "saveState":
            self.save_scenes(force=True)
            self.save_setup()

        elif cmd_name == "loadShow":
            self.load_show(msg[1])

        elif cmd_name == "saveLibrary":
            self.saveAsFiles(
                "fixturetypes", self.fixture_classes, "lighting/fixtureclasses"
            )

        elif cmd_name == "addscene":
            s = Scene(msg[1].strip())
            self.scenememory[s.id] = s
            self.pushMeta(s.id)

        elif cmd_name == "addmonitor":
            s = Scene(msg[1].strip(), blend="monitor",
                      priority=100, active=True)
            self.scenememory[s.id] = s

        elif cmd_name == "setconfuniverses":
            if kaithem.users.check_permission(user, "system_admin"):
                self.configured_universes = msg[1]
                self.create_universes(self.configured_universes)
            else:
                raise RuntimeError("User does not have permission")

        elif cmd_name == "setfixtureclass":
            commandInfo = []
            for i in msg[2]:
                if i[1] not in ["custom", "fine", "fixed"]:
                    commandInfo.append(i[:2])
                else:
                    commandInfo.append(i)
            self.fixture_classes[msg[1]] = commandInfo
            self.refresh_fixtures()

        elif cmd_name == "setfixtureclassopz":
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
            self.fixture_classes[msg[1].replace(
                "-", " ").replace("/", " ")] = commandInfo
            self.refresh_fixtures()

        elif cmd_name == "rmfixtureclass":
            del self.fixture_classes[msg[1]]
            self.refresh_fixtures()

        elif cmd_name == "setFixtureAssignment":
            self.fixture_assignments[msg[1]] = msg[2]
            self.linkSend(["fixtureAssignments", self.fixture_assignments])
            self.refresh_fixtures()

        elif cmd_name == "rmFixtureAssignment":
            del self.fixture_assignments[msg[1]]

            self.linkSend(["fixtureAssignments", self.fixture_assignments])
            self.linkSend(["fixtureAssignments", self.fixture_assignments])

            self.refresh_fixtures()

        elif cmd_name == "clonecue":
            cues[msg[1]].clone(msg[2])

        elif cmd_name == "event":
            event(msg[1], msg[2])

        elif cmd_name == "setshortcut":
            cues[msg[1]].setShortcut(msg[2][:128])
        elif cmd_name == "setnumber":
            cues[msg[1]].setNumber(msg[2])

        elif cmd_name == "setrellen":
            cues[msg[1]].rel_length = msg[2]
            self.pushCueMeta(msg[1])

        elif cmd_name == "setsoundout":
            cues[msg[1]].sound_output = msg[2]
            self.pushCueMeta(msg[1])

        elif cmd_name == "seteventbuttons":
            scenes.scenes[msg[1]].event_buttons = msg[2]
            self.pushMeta(msg[1], keys={"event_buttons"})

        elif cmd_name == "sethide":
            scenes.scenes[msg[1]].hide = msg[2]
            self.pushMeta(msg[1], keys={"hide"})

        elif cmd_name == "setinfodisplay":
            scenes.scenes[msg[1]].info_display = msg[2]
            self.pushMeta(msg[1], keys={"info_display"})

        elif cmd_name == "setutility":
            scenes.scenes[msg[1]].utility = msg[2]
            self.pushMeta(msg[1], keys={"utility"})

        elif cmd_name == "setdisplaytags":
            scenes.scenes[msg[1]].setDisplayTags(msg[2])
            self.pushMeta(msg[1], keys={"display_tags"})

        elif cmd_name == "inputtagvalue":
            for i in scenes.scenes[msg[1]].display_tags:
                # Defensive programming, don't set a tag that wasn't ever actually configured
                if msg[2] == i[1]:
                    if not msg[2].startswith("/"):
                        msg[2] = "/" + msg[2]
                    kaithem.tags.all_tags_raw[msg[2]]().value = msg[3]
                    return

        elif cmd_name == "setMqttServer":
            if kaithem.users.check_permission(user, "system_admin"):
                scenes.scenes[msg[1]].setMqttServer(msg[2])
                self.pushMeta(msg[1], keys={"mqtt_server"})

        elif cmd_name == "namechannel":
            if msg[3]:
                u = universes.universes[msg[1]]()
                if u:
                    u.channels[msg[2]] = msg[3]
            else:
                del universes.universes[msg[1]]().channels[msg[2]]

        elif cmd_name == "add_cueval":
            if hasattr(cues[msg[1]].scene().blendClass, "default_channel_value"):
                val = cues[msg[1]].scene().blendClass.default_channel_value
            else:
                val = 0

            hadVals = len(cues[msg[1]].values)

            # Allow number:name format, but we only want the name
            cues[msg[1]].set_value(msg[2], str(msg[3]).split(":")[-1], val)
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
                if not i[1] in ("unused", "fixed"):
                    if hasattr(cue.scene().blendClass, "default_channel_value"):
                        val = cue.scene().blendClass.default_channel_value
                    else:
                        val = 0
                    # i[0] is the name of the channel
                    cue.set_value("@" + msg[2], i[0], val)

            if length > 1:
                # Set the length as if it were a ficture property
                cue.set_value("@" + msg[2], "__length__", length)
                cue.set_value("@" + msg[2], "__spacing__", spacing)

                # The __dest__ channels represet the color at the end of the channel
                for i in x.channels:
                    if not i[1] in ("unused", "fixed"):
                        if hasattr(cue.scene().blendClass, "default_channel_value"):
                            val = cue.scene().blendClass.default_channel_value
                        else:
                            val = 0
                        # i[0] is the name of the channel
                        cue.set_value(
                            "@" + msg[2], "__dest__." + str(i[0]), val)

            self.linkSend(["cuedata", msg[1], cue.values])
            self.pushCueMeta(msg[1])

        elif cmd_name == "rmcuef":
            s = cues[msg[1]]

            x = list(s.values[msg[2]].keys())

            for i in x:
                s.set_value(msg[2], i, None)
            self.linkSend(["cuedata", msg[1], s.values])
            self.pushCueMeta(msg[1])

        elif cmd_name == "listsoundfolder":
            self.linkSend(
                ["soundfolderlisting", msg[1], listsoundfolder(msg[1])])

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

            cues[msg[1]].set_value(msg[2], ch, v)
            self.linkSend(["scv", msg[1], msg[2], ch, v])

            if v is None:
                # Count of values in the metadata changed
                self.pushCueMeta(msg[1])

        elif cmd_name == "setMusicVisualizations":
            scenes.scenes[msg[1]].setMusicVisualizations(msg[2])

        elif cmd_name == "setDefaultNext":
            scenes.scenes[msg[1]].default_next = str(msg[2])[:256]
        elif cmd_name == "tap":
            scenes.scenes[msg[1]].tap(msg[2])
        elif cmd_name == "setbpm":
            scenes.scenes[msg[1]].setBPM(msg[2])

        elif cmd_name == "setcrossfade":
            scenes.scenes[msg[1]].crossfade = float(msg[2])

        elif cmd_name == "setdalpha":
            scenes.scenes[msg[1]].setAlpha(msg[2], sd=True)

        elif cmd_name == "add_cue":
            n = msg[2].strip()
            if not msg[2] in scenes.scenes[msg[1]].cues:
                scenes.scenes[msg[1]].add_cue(n)

        elif cmd_name == "rename_cue":
            if not msg[3]:
                return

            n = msg[2].strip()
            n2 = msg[3].strip()

            scenes.scenes[msg[1]].rename_cue(n, n2)

        elif cmd_name == "searchsounds":
            self.linkSend(
                [
                    "soundsearchresults",
                    msg[1],
                    searchPaths(msg[1], core.getSoundFolders()),
                ]
            )

        elif cmd_name == "mediaLinkCommand":
            scenes.scenes_by_name[msg[1]].mediaLink.sendTo(msg[3], msg[2])
            return

        elif cmd_name == "newFromSound":
            bn = os.path.basename(msg[2])
            bn = scenes.fnToCueName(bn)
            try:
                tags = TinyTag.get(msg[2])
                if tags.artist and tags.title:
                    bn = tags.title + " ~ " + tags.artist
            except Exception:
                print(traceback.format_exc())

            bn = disallow_special(bn, "_~", replaceMode=" ")
            if bn not in scenes.scenes[msg[1]].cues:
                scenes.scenes[msg[1]].add_cue(bn)
                scenes.scenes[msg[1]].cues[bn].rel_length = True
                scenes.scenes[msg[1]].cues[bn].length = 0.01

                soundfolders = core.getSoundFolders()
                s = None
                for i in soundfolders:
                    s = msg[2]
                    # Make paths relative.
                    if not i.endswith("/"):
                        i = i + "/"
                    if s.startswith(i):
                        s = s[len(i):]
                        break
                if not s:
                    raise RuntimeError("Unknown, linter said was possible")
                scenes.scenes[msg[1]].cues[bn].sound = s
                scenes.scenes[msg[1]].cues[bn].named_for_sound = True

                self.pushCueMeta(scenes.scenes[msg[1]].cues[bn].id)

        elif cmd_name == "newFromSlide":
            bn = os.path.basename(msg[2])
            bn = scenes.fnToCueName(bn)

            bn = disallow_special(bn, "_~", replaceMode=" ")
            if bn not in scenes.scenes[msg[1]].cues:
                scenes.scenes[msg[1]].add_cue(bn)
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

                if not scenes.is_static_media(s):
                    scenes.scenes[msg[1]].cues[bn].rel_length = True
                    scenes.scenes[msg[1]].cues[bn].length = 0.01

                self.pushCueMeta(scenes.scenes[msg[1]].cues[bn].id)

        elif cmd_name == "rmcue":
            c = cues[msg[1]]
            c.scene().rmCue(c.id)

        elif cmd_name == "setCueTriggerShortcut":
            v = msg[2]
            cues[msg[1]].trigger_shortcut = v
            self.pushCueMeta(msg[1])

        elif cmd_name == "setfadein":
            try:
                v = float(msg[2])
            except Exception:
                v = msg[2]
            cues[msg[1]].fade_in = v
            self.pushCueMeta(msg[1])

        elif cmd_name == "setSoundFadeOut":
            try:
                v = float(msg[2])
            except Exception:
                v = msg[2]
            cues[msg[1]].sound_fade_out = v
            self.pushCueMeta(msg[1])

        elif cmd_name == "setCueVolume":
            try:
                v = float(msg[2])
            except Exception:
                v = msg[2]
            cues[msg[1]].sound_volume = v
            self.pushCueMeta(msg[1])
            cues[msg[1]].scene().setAlpha(cues[msg[1]].scene().alpha)

        elif cmd_name == "setCueLoops":
            try:
                v = int(msg[2])
            except Exception:
                v = msg[2]
            cues[msg[1]].sound_loops = v if (
                not v == -1) else 99999999999999999

            self.pushCueMeta(msg[1])
            cues[msg[1]].scene().setAlpha(cues[msg[1]].scene().alpha)

        elif cmd_name == "setSoundFadeIn":
            try:
                v = float(msg[2])
            except Exception:
                v = msg[2]
            cues[msg[1]].sound_fade_in = v
            self.pushCueMeta(msg[1])

        elif cmd_name == "setreentrant":
            v = bool(msg[2])

            cues[msg[1]].reentrant = v
            self.pushCueMeta(msg[1])

        elif cmd_name == "setCueRules":
            cues[msg[1]].setRules(msg[2])
            self.pushCueMeta(msg[1])

        elif cmd_name == "setCueInheritRules":
            cues[msg[1]].setInheritRules(msg[2])
            self.pushCueMeta(msg[1])

        elif cmd_name == "setcuesound":
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

            if s.strip() and cues[msg[1]].sound and cues[msg[1]].named_for_sound:
                self.pushCueMeta(msg[1])
                raise RuntimeError(
                    "This cue was named for a specific sound file, forbidding change to avoid confusion.  To override, set to no sound first"
                )
            cues[msg[1]].sound = s
            self.pushCueMeta(msg[1])

        elif cmd_name == "setcueslide":
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

        elif cmd_name == "setcuesoundoutput":
            cues[msg[1]].sound_output = msg[2].strip()
            self.pushCueMeta(msg[1])

        elif cmd_name == "setcuesoundstartposition":
            cues[msg[1]].sound_start_position = float(msg[2].strip())
            self.pushCueMeta(msg[1])

        elif cmd_name == "setcuemediaspeed":
            cues[msg[1]].media_speed = float(str(msg[2]).strip())
            self.pushCueMeta(msg[1])

        elif cmd_name == "setcuemediawindup":
            cues[msg[1]].media_wind_up = float(str(msg[2]).strip())
            self.pushCueMeta(msg[1])

        elif cmd_name == "setcuemediawinddown":
            cues[msg[1]].media_wind_down = float(str(msg[2]).strip())
            self.pushCueMeta(msg[1])

        elif cmd_name == "settrack":
            cues[msg[1]].setTrack(msg[2])
            self.pushCueMeta(msg[1])

        # TODO: Almost everything should go through these two functions!!
        elif cmd_name == 'setSceneProperty':
            prop = snake_compat.camel_to_snake(msg[2])
            # Generic setter for things that are just simple value sets.

            # Try to get the attr, to ensure that it actually exists.
            old = getattr(scenes.scenes[msg[1]], prop)

            setattr(scenes.scenes[msg[1]], prop, msg[3])

            if not old == msg[3]:
                self.pushMeta(msg[1], keys={prop})

        elif cmd_name == 'setCueProperty':
            prop = snake_compat.camel_to_snake(msg[2])
            # Generic setter for things that are just simple value sets.

            # Try to get the attr, to ensure that it actually exists.
            old = getattr(cues[msg[1]], prop)

            setattr(cues[msg[1]], prop, msg[3])

            if not old == msg[3]:
                self.pushCueMeta(msg[1])

        elif cmd_name == "setmqttfeature":
            scenes.scenes[msg[1]].setMQTTFeature(msg[2], msg[3])
            self.pushMeta(msg[1], keys={"mqtt_sync_features"})

        elif cmd_name == "setscenesoundout":
            scenes.scenes[msg[1]].sound_output = msg[2]
            self.pushMeta(msg[1], keys={"sound_output"})

        elif cmd_name == "setsceneslideoverlay":
            scenes.scenes[msg[1]].slide_overlay_url = msg[2]
            self.pushMeta(msg[1], keys={"slide_overlay_url"})

        elif cmd_name == "setscenecommandtag":
            scenes.scenes[msg[1]].set_command_tag(msg[2])

            self.pushMeta(msg[1], keys={"command_tag"})

        elif cmd_name == "setlength":
            try:
                v = float(msg[2])
            except Exception:
                v = msg[2][:256]
            cues[msg[1]].length = v
            cues[msg[1]].scene().recalc_cue_len()
            self.pushCueMeta(msg[1])

        elif cmd_name == "setrandomize":
            try:
                v = float(msg[2])
            except Exception:
                v = msg[2][:256]
            cues[msg[1]].length_randomize = v
            cues[msg[1]].scene().recalc_randomize_modifier()
            self.pushCueMeta(msg[1])

        elif cmd_name == "setnext":
            if msg[2][:1024]:
                c = msg[2][:1024].strip()
            else:
                c = None
            cues[msg[1]].next_cue = c
            self.pushCueMeta(msg[1])

        elif cmd_name == "setprobability":
            cues[msg[1]].probability = msg[2][:2048]
            self.pushCueMeta(msg[1])

        elif cmd_name == "setblend":
            scenes.scenes[msg[1]].setBlend(msg[2])
        elif cmd_name == "setblendarg":
            scenes.scenes[msg[1]].setBlendArg(msg[2], msg[3])

        elif cmd_name == "setscenename":
            scenes.scenes[msg[1]].setName(msg[2])

        elif cmd_name == "del":
            # X is there in case the active_scenes listing was the last string reference, we want to be able to push the data still
            x = scenes.scenes[msg[1]]
            scenes.checkPermissionsForSceneData(x.toDict(), user)

            x.stop()
            self.delscene(msg[1])

        elif cmd_name == "setsoundfolders":
            # Set the global sound folders list
            core.config['soundFolders'] = [i.strip().replace("\r", '').replace("\t", ' ')
                                           for i in msg[1].split('\n') if i]

        else:
            raise ValueError("Unrecognized Command " + str(cmd_name))
