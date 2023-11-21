# Copyright Daniel Dunn 2013-2015
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

import subprocess

import os
import time
import threading
import collections
import logging
import traceback
from subprocess import PIPE, STDOUT, Popen

from . import util, scheduling, directories, workers, messagebus, midi
from .config import config
from typing import List, Any, Optional, Dict

log = logging.getLogger("system.sound")

jackAPIWidget = None

jackClientsFound = False


def tryCloseFds(p: Optional[subprocess.Popen[Any]]):
    if p:
        try:
            if p.stdout:
                p.stdout.close()
        except Exception:
            pass
        try:
            if p.stderr:
                p.stderr.close()
        except Exception:
            pass
        try:
            if p.stdin:
                p.stdin.close()
        except Exception:
            pass


sound_paths = [""]

p = config["audio-paths"]
for i in p:
    if i == "__default__":
        sound_paths.append(os.path.join(directories.datadir, "sounds"))
    else:
        sound_paths.append(i)

builtinSounds = os.listdir(os.path.join(directories.datadir, "sounds"))


sound_paths.append(os.path.join(directories.vardir, "static"))
sound_paths.append(os.path.join(directories.vardir, "assets"))


def soundPath(fn: str, extrapaths: List[str] = []) -> str:
    "Get the full path of a sound file by searching"
    filename = util.search_paths(fn, extrapaths)
    if not filename:
        filename = util.search_paths(fn, sound_paths)

    # Search all module media folders
    if not filename:
        for i in os.listdir(os.path.join(directories.vardir, "modules", "data")):
            p = os.path.join(
                directories.vardir, "modules", "data", i, "__filedata__", "media"
            )
            filename = util.search_paths(fn, [p])
            if filename:
                break

    # Raise an error if the file doesn't exist
    if not filename or not os.path.isfile(filename):
        raise ValueError("Specified audio file '" + fn + "' was not found")
    return filename


# This class provides some infrastructure to play sounds but if you use it directly it is a dummy.
class SoundWrapper(object):
    backendname = "Dummy Sound Driver(No real sound player found)"

    def __init__(self):
        # Prefetch cache for preloadng sound effects
        self.cache = collections.OrderedDict()
        self.runningSounds = {}

    def readySound(self, *args, **kwargs):
        pass

    @staticmethod
    def testAvailable():
        # Default to command based test
        return False

    # little known fact: Kaithem is actually a large collection of
    # mini garbage collectors and bookkeeping code...
    def deleteStoppedSounds(self):
        x = list(self.runningSounds.keys())
        for i in x:
            try:
                if not self.runningSounds[i].is_playing():
                    self.runningSounds.pop(i)
            except KeyError:
                pass

    def stop_allSounds(self):
        x = list(self.runningSounds.keys())
        for i in x:
            try:
                self.runningSounds.pop(i)
            except KeyError:
                pass

    def getPosition(self, channel: str = "PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].position()
        except KeyError:
            return False

    def setVolume(self, vol: float, channel: str = "PRIMARY"):
        pass

    def setSpeed(self, speed: float, channel: str = "PRIMARY", *a, **kw):
        pass

    def play_sound(self,
                   filename: str,
                   handle: str = "PRIMARY",
                   extraPaths: List[str] = [],
                   volume: float = 1,
                   finalGain: Optional[float] = None,
                   output: str = "",
                   loop: float = 1,
                   start: float = 0,
                   speed: float = 1):
        pass

    def stopSound(self, handle: str = "PRIMARY"):
        pass

    def is_playing(self, handle: str = "blah", refresh: bool = False):
        return False

    def pause(self, handle: str = "PRIMARY"):
        pass

    def resume(self, handle: str = "PRIMARY"):
        pass

    def fade_to(self,        
                file: str,
                length: float = 1.0,
                block: bool = False,
                handle: str = "PRIMARY",
                output: str = "",
                volume: float = 1,
                windup: float = 0,
                winddown: float = 0,
                speed: float = 1):
        self.play_sound(file, handle)

    def preload(self, filename: str):
        pass

    def seek(self, position: float, channel: str = "PRIMARY"):
        try:
            return self.runningSounds[channel].seek(position)
        except KeyError:
            pass


objectPoolLock = threading.RLock()

objectPool = []


class RemoteMPV:
    def __del__(self):
        self.stop()

    def __init__(self, *a, **k):
        # -*- coding: utf-8 -*-

        # If del can't find this it would to an infinite loop
        self.worker = None
        self.stopping = False
        from jsonrpyc import RPC

        f = os.path.join(os.path.dirname(
            os.path.abspath(__file__)), "mpv_server.py")
        self.lock = threading.RLock()
        env = {}
        env.update(os.environ)
        env["GST_DEBUG"] = "0"
        self.worker = Popen(
            ["python3", f], stdout=PIPE, stdin=PIPE, stderr=STDOUT, env=env
        )
        self.rpc = RPC(
            target=self, stdin=self.worker.stdout, stdout=self.worker.stdin, daemon=True
        )

        self.usesCounter = 0

    def stop(self):
        if self.stopping:
            return
        if not hasattr(self, "rpc"):
            return

        self.stopping = True
        self.rpc.stopFlag = True
        # v =  self.rpc.call('get',['volume'],block=0.001)
        # self.rpc.call('set',['volume',v/2])
        # self.rpc.call('set',['volume',v/8])
        # self.rpc.call('set',['volume',0])

        if self.worker.poll() is not None:
            tryCloseFds(self.worker)
            return

        try:
            self.rpc.call("call", ["stop"], block=0.001, timeout=3)
        except TimeoutError:
            pass
        except Exception:
            # I hate this. But I guess it's rather obvious if the stop function doesn't work,
            # And this makes nuisance errors if the process is already dead.
            pass

        self.worker.kill()
        self.worker.wait()
        tryCloseFds(self.worker)

    def print(self, s):
        print(s)


class MPVBackend(SoundWrapper):
    @staticmethod
    def testAvailable():
        if not util.which("mpv"):
            return False
        try:
            import python_mpv_jsonipc
            return True
        except Exception:
            pass

    backendname = "MPV"

    # What this does is it keeps a reference to the sound player process and
    # If the object is destroyed it destroys the process stopping the sound
    # It also abstracts checking if its playing or not.
    class MPVSoundContainer(object):
        def __init__(
            self,
            filename,
            vol,
            finalGain,
            output,
            loop,
            start=0,
            speed=1,
            just_preload=False,
        ):
            self.lock = threading.RLock()
            self.stopped = False
            self.is_playingCache = None

            if output == "__disable__":
                return

            self.alreadySetCorrection = False

            settings_key = (speed, loop)

            # I think this leaks memory when created and destroyed repeatedly
            with objectPoolLock:
                if len(objectPool):
                    self.player = objectPool.pop()
                else:
                    self.player = RemoteMPV()

            # Avoid somewhat slow RPC calls if we can
            if (not hasattr(self.player, "isConfigured")) or (
                not self.player.isConfigured
            ):
                cname = "kplayer" + str(time.monotonic()) + "_out"

                self.player.rpc.call("set", ["vid", "no"])
                self.player.rpc.call("set", ["keep_open", "yes"])

                self.player.rpc.call("set", ["ao", "jack,pulse,alsa"])
                self.player.rpc.call("set", ["jack_name", cname])
                self.player.rpc.call("set", ["gapless_audio", "weak"])
                self.player.isConfigured = True

            if (
                not hasattr(self.player, "conf")
            ) or not self.player.conf == settings_key:
                if (not speed == 1) or (
                    hasattr(self.player, "conf") and (
                        speed != self.player.conf[0])
                ):
                    self.player.rpc.call(
                        "set", ["audio_pitch_correction", False], block=0.001
                    )
                    self.player.rpc.call("set", ["speed", speed], block=0.001)
                self.player.conf = settings_key

                # For legavy reasons some stuff used tens of millions instead of actual infinite loop.
                # But it seems mpv ignores everything past a certain number. So we replace effectively forever with
                # actually forever to get the same effect, assuming that was user intent.
                if not (loop == -1 or loop > 900000000):
                    self.player.rpc.call(
                        "set", ["loop_playlist", int(max(loop, 1))])
                else:
                    self.player.rpc.call("set", ["loop_playlist", "inf"])

            # Due to memory leaks, these have a limited lifespan
            self.player.usesCounter += 1

            if (not hasattr(self.player, "lastvol")) or not self.player.lastvol == vol:
                self.player.lastvol = vol
                self.player.rpc.call("set", ["volume", vol * 100])

            self.volume = vol
            self.finalGain = finalGain if finalGain is not None else vol

            jp = "system:*"
            if output:
                if ":" not in output:
                    jp = output + ":*"
                else:
                    jp = output

            if (not hasattr(self.player, "lastjack")) or not self.player.lastjack == jp:
                self.player.rpc.call("set", ["jack_port", jp])
                self.player.lastjack = jp

            self.started = time.time()

            if filename:
                self.is_playingCache = None
                self.player.rpc.call(
                    "call", ["loadfile", filename], block=0.001, timeout=12
                )
                self.player.rpc.call("set", ["pause", False])
                if start:
                    self.player.rpc.call(
                        "call", ["seek", str(start), "absolute"])

        def __del__(self):
            self.stop()

        def stop(self):
            if self.stopped:
                return
            self.stopped = True
            bad = True
            if hasattr(self, "player"):
                # Only do the maybe recycle logic when stopping a still good SFX
                try:
                    w = self.player.worker
                except Exception:
                    return
                if w.poll() is None:
                    try:
                        with self.lock:
                            self.player.rpc.call(
                                "call", ["stop"], block=0.001, timeout=1
                            )
                        bad = False
                    except Exception:
                        # Sometimes two threads try to stop this at the same time and we get a race condition
                        # I really hate this but stopping a crashed sound can't be allowed to take down anything else.
                        pass

                # When the player only has a few uses left, if we don't have many spare objects in
                # the pool, we are going to make the replacement ahead of time in a background thread.
                # But try tpo only make one replacement per object, we don't actually want to go up to the max
                # in the pool because they can use CPU in the background
                if bad or self.player.usesCounter > 8:
                    if not hasattr(self.player, "alreadyMadeReplacement"):
                        if (len(objectPool) < 3) or self.player.usesCounter > 10:
                            self.player.alreadyMadeReplacement = True

                            def f():
                                # Can't make it under lock that is slow
                                o = RemoteMPV()
                                with objectPoolLock:
                                    if len(objectPool) < 4:
                                        objectPool.append(o)
                                        return
                                o.stop()

                            workers.do(f)

                if bad or self.player.usesCounter > 10:
                    p = self.player

                    def f():
                        p.stop()

                    workers.do(f)

                else:
                    with objectPoolLock:
                        p = self.player
                        if p:
                            if len(objectPool) < 4:
                                objectPool.append(p)
                            else:
                                self.player.stop()
                self.player = None

        def is_playing(self, refresh=False):
            with self.lock:
                if not hasattr(self, "player"):
                    return False
                try:
                    if not refresh:
                        if self.is_playingCache is not None:
                            return self.is_playingCache
                    c = (
                        self.player.rpc.call(
                            "get", ["eof_reached"], block=0.001, timeout=12
                        )
                        == False
                    )

                    if c is False:
                        self.is_playingCache = c

                    return c
                except Exception:
                    logging.exception(
                        "Error getting playing status, assuming closed")
                    return False

        def position(self):
            return time.time() - self.started

        def wait(self):
            with self.lock:
                # Block until sound is finished playing.
                self.player.rpc.call("wait_for_playback",
                                     block=0.001, timeout=3)

        def seek(self, position):
            pass

        def setVol(self, volume, final=True):
            with self.lock:
                self.volume = volume
                if final:
                    self.finalGain = volume
                self.player.lastvol = volume
                self.player.rpc.call(
                    "set", ["volume", volume * 100], block=0.001)

        def setSpeed(self, speed):
            with self.lock:
                if not self.alreadySetCorrection:
                    self.player.rpc.call(
                        "set", ["audio_pitch_correction", False], block=0.001
                    )
                    self.alreadySetCorrection = True
                # Mark as needing to be updated
                self.player.conf = (speed, self.player.conf[1])
                self.player.rpc.call("set", ["speed", speed], block=0.001)

        def getVol(self):
            with self.lock:
                return self.player.rpc.call("get", ["volume"], block=0.001)

        def pause(self):
            with self.lock:
                self.player.rpc.call("set", ["pause", True])

        def resume(self):
            with self.lock:
                self.player.rpc.call("set", ["pause", False])

    def play_sound(
        self,
        filename: str,
        handle: str = "PRIMARY",
        extraPaths: List[str] = [],
        volume: float = 1,
        finalGain: Optional[float] = None,
        output: str = "",
        loop: float = 1,
        start: float = 0,
        speed: float = 1
    ):
        # Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        # Raise an error if the file doesn't exist
        fn = soundPath(filename, extraPaths)
        # Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.MPVSoundContainer(
            fn, volume, finalGain, output, loop, start=start, speed=speed
        )

    def stopSound(self, handle="PRIMARY"):
        # Delete the sound player reference object and its destructor will stop the sound
        if handle in self.runningSounds:
            # Instead of using a lock lets just catch the error is someone else got there first.
            try:
                x = self.runningSounds[handle]
                try:
                    x.stop()
                except Exception:
                    logging.exception("Error stopping")
                del self.runningSounds[handle]
                x.nocallback = True
                del x
            except KeyError:
                pass

    def is_playing(self, channel="PRIMARY", refresh=False):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].is_playing(refresh)
        except KeyError:
            return False

    def wait(self, channel="PRIMARY"):
        "Block until any sound playing on a channel is finished"
        try:
            self.runningSounds[channel].wait()
        except KeyError:
            return False

    def setVolume(self, vol, channel="PRIMARY", final=True):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].setVol(vol, final=final)
        except KeyError:
            pass

    def setSpeed(self, speed, channel="PRIMARY", *a, **kw):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].setSpeed(speed)
        except KeyError:
            pass

    def seek(self, position, channel="PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].seek(position)
        except KeyError:
            pass

    def pause(self, channel="PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].pause()
        except KeyError:
            pass

    def resume(self, channel="PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].resume()
        except KeyError:
            pass

    def fade_to(
        self,
        file: str,
        length: float = 1.0,
        block: bool = False,
        handle: str = "PRIMARY",
        output: str = "",
        volume: float = 1,
        windup: float = 0,
        winddown: float = 0,
        speed: float = 1,
    ):
        x = self.runningSounds.pop(handle, None)

        if x and not (length or winddown):
            x.stop()

        k = kwargs.copy()
        k.pop("volume", 0)

        # Allow fading to silence
        if file:
            sspeed = speed
            if windup:
                sspeed = 0.1

            self.play_sound(
                file,
                handle=handle,
                volume=0,
                output=output,
                finalGain=volume,
                loop=kwargs.get("loop", 1),
                speed=sspeed,
            )

        # if not x:
        #    return
        if not (length or winddown or windup):
            return

        def f():
            t = time.monotonic()
            try:
                v = x.volume
            except Exception:
                v = 0

            targetVol = 1
            while time.monotonic() - t < max(length, winddown, windup):
                if max(length, winddown):
                    foratio = max(
                        0, min(1, ((time.monotonic() - t) / max(length, winddown)))
                    )
                else:
                    foratio = 1

                if length:
                    firatio = max(0, min(1, ((time.monotonic() - t) / length)))
                else:
                    firatio = 1

                tr = time.monotonic()

                if x and x.player:
                    # Player might have gotten itself stopped by now
                    try:
                        x.setVol(max(0, v * (1 - foratio)))

                        if winddown:
                            wdratio = max(
                                0, min(1, ((time.monotonic() - t) / winddown))
                            )
                            x.setSpeed(max(0.1, v * (1 - wdratio)))
                    except AttributeError:
                        print(traceback.format_exc())

                if file and (handle in self.runningSounds):
                    targetVol = self.runningSounds[handle].finalGain
                    self.setVolume(min(1, targetVol * firatio),
                                   handle, final=False)

                    if windup:
                        wuratio = max(
                            0, min(1, ((time.monotonic() - t) / windup)))
                        self.setSpeed(
                            max(0.1, min(1, wuratio * speed)), handle)

                # Don't overwhelm the backend with commands
                time.sleep(max(1 / 48.0, time.monotonic() - tr))

            try:
                targetVol = self.runningSounds[handle].finalGain
            except KeyError:
                targetVol = -1

            if not targetVol == -1:
                try:
                    self.setVolume(min(1, targetVol), handle)
                except Exception as e:
                    print(e)

            if x:
                x.stop()

        if block:
            f()
        else:
            workers.do(f)


l = {
    "mpv": MPVBackend,
}

backend = SoundWrapper()
if util.which("pulseaudio"):
    pulseaudio = True
else:
    pulseaudio = False

# MPV is alwaus auto chosen if available!!!
# All the others are deprecated!!
for i in ["mpv"] + list(config["audio-backends"]):
    if i not in l:
        continue
    try:
        if util.which(i) or l[i].testAvailable():
            backend = l[i]()
            break
    except Exception:
        messagebus.post_message(
            "/system/notifications/errors",
            "Failed to initialize audio backend "
            + i
            + " may be able to use fallback:\n"
            + traceback.format_exc(),
        )

try:
    if backend.backendname == "Dummy Sound Driver(No real sound player found)":
        messagebus.post_message(
            "/system/notifications/errors",
            "Using adummy sound backend. Suggest installing MPV if you want sound",
        )
except Exception:
    print(traceback.format_exc())


def stop_allSounds():
    midi.all_notes_off()
    backend.stop_allSounds()


# Stop any old pulseaudio or something sound players that
# May have been running before jack started, otherwise they will just sit
# there doing nothing and that may be a problem.


def sasWrapper(*a):
    stop_allSounds()


messagebus.subscribe("/system/sound/jackstart", sasWrapper)


def ogg_test(output=None):
    t = "Kaithemogg_test"
    play_sound("alert.ogg", output=output, handle=t)
    for i in range(100):
        if is_playing(t, refresh=True):
            return
        time.sleep(0.01)
    raise RuntimeError("Sound did not report as playing within 1000ms")


# Make fake module functions mapping to the bound methods.
play_sound = backend.play_sound
stopSound = backend.stopSound
is_playing = backend.is_playing
resolve_sound = soundPath
pause = backend.pause
resume = backend.resume
setvol = backend.setVolume
position = backend.getPosition
fade_to = backend.fade_to
readySound = backend.readySound
preload = backend.preload

isStartDone = []
