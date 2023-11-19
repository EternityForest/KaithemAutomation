import os
import traceback
import time

from tinytag import TinyTag

from . import ChandlerConsole

from ..kaithemobj import kaithem
from .scenes import Scene, cues, event
from . import scenes
from . import core
from . import universes
from .core import disallow_special


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

    # Sometimes used as a stylized S
    fn = fn.replace("$", "S")
    fn = fn.replace("@", " at ")

    # Usually going to be the number sign, we can ditch
    fn = fn.replace("#", "")

    # Handle spaces already there or not
    fn = fn.replace(" & ", " and ")
    fn = fn.replace("&", " and ")
    
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


class WebConsole(ChandlerConsole.ChandlerConsole):

    def __init__(self):
        self.link = None
        super().__init__()
        self.setup_link()

    def setup_link(self):
        self.link = kaithem.widget.APIWidget("api_link")
        self.link.require("users.chandler.admin")
        self.link.echo = False
        # Bound method weakref nonsense prevention
        # also wrapping

        def f(x, y):
            try:
                self._onmsg(x, y)
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
        self.link.attach(self.onmsg)

    def linkSend(self, *a, **k):
        if self.link:
            return self.link.send(*a, **k)

    def _onmsg(self, user, msg):
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
            self.linkSend(["cuedata", msg[1], s.values])
            self.pushCueMeta(msg[1])

        elif msg[0] == "getfixtureclass":
            self.linkSend(
                ["fixtureclass", msg[1], self.fixtureClasses[msg[1]]])

        elif msg[0] == "getfixtureclasses":
            # Send placeholder lists
            self.linkSend(
                ["fixtureclasses", {i: []
                                    for i in self.fixtureClasses.keys()}]
            )
        elif msg[0] == "getcuemeta":
            s = cues[msg[1]]
            self.pushCueMeta(msg[1])

        elif msg[0] == "gasd":
            with core.lock:
                self.linkSend(["presets", self.presets])
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

        # There's such a possibility for an iteration error if universes changes.
        # I'm not going to worry about it, this is only for the GUI list of universes.
        elif msg[0] == "getuniverses":
            self.pushUniverses()

        elif msg[0] == "getserports":
            self.linkSend(["serports", getSerPorts()])

        elif msg[0] == "getCommands":
            c = scenes.rootContext.commands.scriptcommands
            commandInfo = {}
            for i in c:
                f = c[i]
                commandInfo[i] = kaithem.chandlerscript.get_function_info(f)
            self.linkSend(["commands", commandInfo])

        elif msg[0] == "getconfuniverses":
            self.pushConfiguredUniverses()

        # User level runtime stuff that can't change config

        elif msg[0] == "jumptocue":
            if not cues[msg[1]].scene().active:
                cues[msg[1]].scene().go()

            cues[msg[1]].scene().goto_cue(cues[msg[1]].name, cause="manual")

        elif msg[0] == "jumpbyname":
            scenes.scenes_by_name[msg[1]].goto_cue(msg[2], cause="manual")

        elif msg[0] == "nextcue":
            scenes.scenes[msg[1]].next_cue(cause="manual")

        elif msg[0] == "prevcue":
            scenes.scenes[msg[1]].prev_cue(cause="manual")

        elif msg[0] == "nextcuebyname":
            scenes.scenes_by_name[msg[1]].next_cue(cause="manual")

        elif msg[0] == "shortcut":
            scenes.shortcutCode(msg[1])

        elif msg[0] == "gotonext":
            if cues[msg[1]].next_cue:
                try:
                    s =  cues[msg[1]].scene()
                    if s:
                        s.next_cue(cause="manual")
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
            kaithem.sound.ogg_test(output=msg[1])

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
            self.linkSend(["newscene", msg[1].strip(), s.id])
            self.pushMeta(s.id)

        elif msg[0] == "addmonitor":
            s = Scene(msg[1].strip(), blend="monitor",
                      priority=100, active=True)
            self.scenememory[s.id] = s
            self.linkSend(["newscene", msg[1].strip(), s.id])

        elif msg[0] == "setconfuniverses":
            if kaithem.users.check_permission(user, "/admin/settings.edit"):
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
            self.linkSend(["fixtureAssignments", self.fixtureAssignments])
            self.refreshFixtures()

        elif msg[0] == "getcuehistory":
            self.linkSend(
                ["cuehistory", msg[1], scenes.scenes[msg[1]].cueHistory])

        elif msg[0] == "rmFixtureAssignment":
            del self.fixtureAssignments[msg[1]]

            self.linkSend(["fixtureAssignments", self.fixtureAssignments])
            self.linkSend(["fixtureAssignments", self.fixtureAssignments])

            self.refreshFixtures()

        elif msg[0] == "getfixtureassg":
            self.linkSend(["fixtureAssignments", self.fixtureAssignments])
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
            cues[msg[1]].sound_output = msg[2]
            self.pushCueMeta(msg[1])

        elif msg[0] == "setNotes":
            scenes.scenes[msg[1]].notes = msg[2]
            self.pushMeta(msg[1], keys={"notes"})

        elif msg[0] == "seteventbuttons":
            scenes.scenes[msg[1]].event_buttons = msg[2]
            self.pushMeta(msg[1], keys={"event_buttons"})

        elif msg[0] == "setinfodisplay":
            scenes.scenes[msg[1]].info_display = msg[2]
            self.pushMeta(msg[1], keys={"info_display"})

        elif msg[0] == "setutility":
            scenes.scenes[msg[1]].utility = msg[2]
            self.pushMeta(msg[1], keys={"utility"})

        elif msg[0] == "setdisplaytags":
            scenes.scenes[msg[1]].setDisplayTags(msg[2])
            self.pushMeta(msg[1], keys={"display_tags"})

        elif msg[0] == "setMqttServer":
            if kaithem.users.check_permission(user, "/admin/modules.edit"):
                scenes.scenes[msg[1]].setMqttServer(msg[2])
                self.pushMeta(msg[1], keys={"mqtt_server"})

        elif msg[0] == "getcnames":
            self.pushChannelNames(msg[1])

        elif msg[0] == "namechannel":
            if msg[3]:
                u = universes.universes[msg[1]]()
                if u:
                    u.channels[msg[2]] = msg[3]
            else:
                del universes.universes[msg[1]]().channels[msg[2]]

        elif msg[0] == "addcueval":
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
                    cues[msg[1]].set_value(i, j, msg[2][i][j])

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

        elif msg[0] == "rmcuef":
            s = cues[msg[1]]

            x = list(s.values[msg[2]].keys())

            for i in x:
                s.set_value(msg[2], i, None)
            self.linkSend(["cuedata", msg[1], s.values])
            self.pushCueMeta(msg[1])

        elif msg[0] == "listsoundfolder":
            self.linkSend(
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

            cues[msg[1]].set_value(msg[2], ch, v)
            self.linkSend(["scv", msg[1], msg[2], ch, v])

            if v is None:
                # Count of values in the metadata changed
                self.pushCueMeta(msg[1])

        elif msg[0] == "setMidiSource":
            scenes.scenes[msg[1]].setMidiSource(msg[2])

        elif msg[0] == "setMusicVisualizations":
            scenes.scenes[msg[1]].setMusicVisualizations(msg[2])

        elif msg[0] == "setDefaultNext":
            scenes.scenes[msg[1]].default_next = str(msg[2])[:256]
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
            self.linkSend(
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
                
            bn = disallow_special(bn, "_~", replaceMode=" ")
            if bn not in scenes.scenes[msg[1]].cues:
                scenes.scenes[msg[1]].addCue(bn)
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

        elif msg[0] == "newFromSlide":
            bn = os.path.basename(msg[2])
            bn = fnToCueName(bn)


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
            cues[msg[1]].trigger_shortcut = v
            self.pushCueMeta(msg[1])

        elif msg[0] == "setfadein":
            try:
                v = float(msg[2])
            except Exception:
                v = msg[2]
            cues[msg[1]].fade_in = v
            self.pushCueMeta(msg[1])

        elif msg[0] == "setSoundFadeOut":
            try:
                v = float(msg[2])
            except Exception:
                v = msg[2]
            cues[msg[1]].sound_fade_out = v
            self.pushCueMeta(msg[1])

        elif msg[0] == "setCueVolume":
            try:
                v = float(msg[2])
            except Exception:
                v = msg[2]
            cues[msg[1]].sound_volume = v
            self.pushCueMeta(msg[1])
            cues[msg[1]].scene().setAlpha(cues[msg[1]].scene().alpha)

        elif msg[0] == "setCueLoops":
            try:
                v = int(msg[2])
            except Exception:
                v = msg[2]
            cues[msg[1]].sound_loops = v if (
                not v == -1) else 99999999999999999

            self.pushCueMeta(msg[1])
            cues[msg[1]].scene().setAlpha(cues[msg[1]].scene().alpha)

        elif msg[0] == "setSoundFadeIn":
            try:
                v = float(msg[2])
            except Exception:
                v = msg[2]
            cues[msg[1]].sound_fade_in = v
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

            if s.strip() and cues[msg[1]].sound and cues[msg[1]].named_for_sound:
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
            cues[msg[1]].sound_output = msg[2].strip()
            self.pushCueMeta(msg[1])

        elif msg[0] == "setcuesoundstartposition":
            cues[msg[1]].sound_start_position = float(msg[2].strip())
            self.pushCueMeta(msg[1])

        elif msg[0] == "setcuemediaspeed":
            cues[msg[1]].media_speed = float(msg[2].strip())
            self.pushCueMeta(msg[1])

        elif msg[0] == "setcuemediawindup":
            cues[msg[1]].media_wind_up = float(msg[2].strip())
            self.pushCueMeta(msg[1])

        elif msg[0] == "setcuemediawinddown":
            cues[msg[1]].media_wind_down = float(msg[2].strip())
            self.pushCueMeta(msg[1])

        elif msg[0] == "settrack":
            cues[msg[1]].setTrack(msg[2])
            self.pushCueMeta(msg[1])

        elif msg[0] == "setcuenotes":
            cues[msg[1]].notes = msg[2].strip()
            self.pushCueMeta(msg[1])

        elif msg[0] == "setdefault_active":
            scenes.scenes[msg[1]].default_active = bool(msg[2])
            self.pushMeta(msg[1], keys={"active"})

        elif msg[0] == "setbacktrack":
            scenes.scenes[msg[1]].setBacktrack(bool(msg[2]))
            self.pushMeta(msg[1], keys={"backtrack"})

        elif msg[0] == "setmqttfeature":
            scenes.scenes[msg[1]].setMQTTFeature(msg[2], msg[3])
            self.pushMeta(msg[1], keys={"mqtt_sync_features"})

        elif msg[0] == "setscenesoundout":
            scenes.scenes[msg[1]].sound_output = msg[2]
            self.pushMeta(msg[1], keys={"sound_output"})

        elif msg[0] == "setsceneslideoverlay":
            scenes.scenes[msg[1]].slide_overlay_url = msg[2]
            self.pushMeta(msg[1], keys={"slide_overlay_url"})

        elif msg[0] == "setscenecommandtag":
            scenes.scenes[msg[1]].setCommandTag(msg[2])

            self.pushMeta(msg[1], keys={"command_tag"})

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
            cues[msg[1]].length_randomize = v
            cues[msg[1]].scene().recalcRandomizeModifier()
            self.pushCueMeta(msg[1])

        elif msg[0] == "setnext":
            if msg[2][:1024]:
                c = msg[2][:1024].strip()
            else:
                c = None
            cues[msg[1]].next_cue = c
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
