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

from . import util, directories, workers, messagebus, midi
from .config import config
from typing import List, Any, Optional
from python_mpv_jsonipc import MPV

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
    assert isinstance(filename, str)
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
    def delete_stopped_sounds(self):
        x = list(self.runningSounds.keys())
        for i in x:
            try:
                if not self.runningSounds[i].is_playing():
                    self.runningSounds.pop(i)
            except KeyError:
                pass

    def stop_all_sounds(self):
        x = list(self.runningSounds.keys())
        for i in x:
            try:
                self.runningSounds.pop(i)
            except KeyError:
                pass

    def get_position(self, channel: str = "PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].position()
        except KeyError:
            return False

    def set_volume(self, vol: float, channel: str = "PRIMARY"):
        pass

    def set_speed(self, speed: float, channel: str = "PRIMARY", *a, **kw):
        pass

    def play_sound(self,
                   filename: str,
                   handle: str = "PRIMARY",
                   extraPaths: List[str] = [],
                   volume: float = 1,
                   finalGain: Optional[float] = None,
                   output: Optional[str] = "",
                   loop: float = 1,
                   start: float = 0,
                   speed: float = 1):
        pass

    def stop_sound(self, handle: str = "PRIMARY"):
        pass

    def is_playing(self, handle: str = "blah", refresh: bool = False):
        return False

    def pause(self, handle: str = "PRIMARY"):
        pass

    def resume(self, handle: str = "PRIMARY"):
        pass

    def fade_to(self,
                file: str | None,
                length: float = 1.0,
                block: bool = False,
                handle: str = "PRIMARY",
                output: Optional[str] = "",
                volume: float = 1,
                windup: float = 0,
                winddown: float = 0,
                loop: int = 1,
                start: float = 0,
                speed: float = 1):
        if file:
            self.play_sound(file, handle)
        else:
            self.stop_sound(handle)

    def preload(self, filename: str):
        pass

    def seek(self, position: float, channel: str = "PRIMARY"):
        try:
            return self.runningSounds[channel].seek(position)
        except KeyError:
            pass


test_sound_logs = []
play_logs = []


class TestSoundWrapper(SoundWrapper):
    def play_sound(self, filename: str, handle: str = "PRIMARY",
                   extraPaths: List[str] = [], volume: float = 1,
                   finalGain: float | None = None, output: str | None = "",
                   loop: float = 1, start: float = 0, speed: float = 1):
        test_sound_logs.append(['play', handle, filename])
        play_logs.append(['play', handle, filename])

    def fade_to(self, file: str | None, length: float = 1,
                block: bool = False, handle: str = "PRIMARY",
                output: str | None = "", volume: float = 1,
                windup: float = 0, winddown: float = 0,
                loop: int = 1, start: float = 0, speed: float = 1):
        test_sound_logs.append(['fade_to', handle, file])
        play_logs.append(['fade_to', handle, file])

    def stop_sound(self, handle: str = "PRIMARY"):
        test_sound_logs.append(['stop', handle])


objectPoolLock = threading.RLock()

objectPool = []


class PlayerHolder(object):
    def __init__(self, p: MPV) -> None:
        self.player = p
        self.usesCounter = 0
        self.conf = [0]
        self.isConfigured = False
        self.lastvol = -99089798
        self.conf_speed = 1
        self.loop_conf = -1
        self.alreadyMadeReplacement = False
        self.lastjack = "hgfdxcghjkufdszcxghjkuyfgdx"


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
            start=0.0,
            speed=1.0,
            just_preload=False,
        ):
            self.lock = threading.RLock()
            self.stopped = False
            self.is_playingCache = None

            self.player: Optional[PlayerHolder] = None

            if output == "__disable__":
                return

            self.alreadySetCorrection = False

            # I think this leaks memory when created and destroyed repeatedly
            with objectPoolLock:
                if len(objectPool):
                    self.player = objectPool.pop()
                else:
                    self.player = PlayerHolder(MPV())

            # Avoid somewhat slow RPC calls if we can
            if not self.player.isConfigured:
                cname = "kplayer" + str(time.monotonic()) + "_out"
                self.player.player.vid = 'no'
                self.player.player.keep_open = 'yes'
                self.player.player.ao = "jack,pulse,alsa"
                self.player.player.jack_name = cname
                self.player.player.gapless_audio = "weak"
                self.player.player.isConfigured = True

            if speed != self.player.conf_speed:
                self.player.player.audio_pitch_correction = False
                self.player.player.speed = speed

            if not loop == self.player.loop_conf:
                # For legavy reasons some stuff used tens of millions instead of actual infinite loop.
                # But it seems mpv ignores everything past a certain number. So we replace effectively forever with
                # actually forever to get the same effect, assuming that was user intent.
                if not (loop == -1 or loop > 900000000):
                    self.player.player.loop_playlist = int(max(loop, 1))
                else:
                    self.player.player.loop_playlist = 'inf'

            # Due to memory leaks, these have a limited lifespan
            self.player.usesCounter += 1

            if (not hasattr(self.player, "lastvol")) or not self.player.lastvol == vol:
                self.player.lastvol = vol
                self.player.player.volume = vol * 100

            self.volume = vol
            self.finalGain = finalGain if finalGain is not None else vol

            jp = "system:*"
            if output:
                if ":" not in output:
                    jp = output + ":*"
                else:
                    jp = output

            if not self.player.lastjack == jp:
                self.player.player.jack_port = jp
                self.player.player.lastjack = jp

            self.started = time.time()

            if filename:
                if self.player:
                    self.is_playingCache = None
                    self.player.player.loadfile(filename)

                    self.player.player.pause = False
                    if start:
                        for i in range(50):
                            try:
                                time.sleep(0.01)
                                self.player.player.seek(str(start), "absolute")
                                break
                            except Exception:
                                pass
                            
                else:
                    raise RuntimeError("Player object is gone")

        def __del__(self):
            self.stop()

        def stop(self):
            if self.stopped:
                return
            self.stopped = True
            bad = True
            if self.player:
                # Only do the maybe recycle logic when stopping a still good SFX

                try:
                    with self.lock:
                        self.player.player.stop()
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
                    if not self.player.alreadyMadeReplacement:
                        if (len(objectPool) < 3) or self.player.usesCounter > 10:
                            self.player.alreadyMadeReplacement = True

                            def f():
                                # Can't make it under lock that is slow
                                from python_mpv_jsonipc import MPV
                                o = PlayerHolder(MPV())
                                with objectPoolLock:
                                    if len(objectPool) < 4:
                                        objectPool.append(o)
                                        return
                                o.player.stop()

                            workers.do(f)

                if bad or self.player.usesCounter > 10:
                    p = self.player

                    def f():
                        if p:
                            p.player.stop()

                    workers.do(f)

                else:
                    with objectPoolLock:
                        p = self.player
                        if p:
                            if len(objectPool) < 4:
                                objectPool.append(p)
                            else:
                                self.player.player.stop()
                self.player = None

        def is_playing(self, refresh=False):
            with self.lock:
                if not self.player:
                    return False
                try:
                    if not refresh:
                        if self.is_playingCache is not None:
                            return self.is_playingCache
                    c = self.player.player.eof_reached == False

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
                if self.player:
                    self.player.wait_for_playback()
                else:
                    raise RuntimeError("No player object")

        def seek(self, position):
            pass

        def setVol(self, volume, final=True):
            with self.lock:
                self.volume = volume
                if final:
                    self.finalGain = volume
                if self.player:
                    self.player.lastvol = volume
                    self.player.player.volume = volume * 100

        def set_speed(self, speed):
            with self.lock:
                if self.player:
                    if not self.alreadySetCorrection:
                        self.player.player.audio_pitch_correction = False
                        self.alreadySetCorrection = True
                    # Mark as needing to be updated
                    self.player.conf_speed = speed
                    self.player.player.speed = speed

        def getVol(self):
            with self.lock:
                if self.player:
                    return self.player.player.volume
                else:
                    return 0

        def pause(self):
            with self.lock:
                if self.player:
                    self.player.player.pause = True

        def resume(self):
            with self.lock:
                if self.player:
                    self.player.player.pause = False

    def play_sound(
        self,
        filename: str,
        handle: str = "PRIMARY",
        extraPaths: List[str] = [],
        volume: float = 1,
        finalGain: Optional[float] = None,
        output: Optional[str] = "",
        loop: float = 1,
        start: float = 0,
        speed: float = 1
    ):
        # Those old sound handles won't garbage collect themselves
        self.delete_stopped_sounds()
        # Raise an error if the file doesn't exist
        fn = soundPath(filename, extraPaths)
        # Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.MPVSoundContainer(
            fn, volume, finalGain, output, loop, start=start, speed=speed
        )

    def stop_sound(self, handle="PRIMARY"):
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

    def set_volume(self, vol, channel="PRIMARY", final=True):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].setVol(vol, final=final)
        except KeyError:
            pass

    def set_speed(self, speed, channel="PRIMARY", *a, **kw):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].set_speed(speed)
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
        file: str | None,
        length: float = 1.0,
        block: bool = False,
        handle: str = "PRIMARY",
        output: Optional[str] = "",
        volume: float = 1,
        windup: float = 0,
        winddown: float = 0,
        loop: int = 1,
        start: float = 0,
        speed: float = 1,
    ):
        x = self.runningSounds.pop(handle, None)

        if x and not (length or winddown):
            x.stop()

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
                loop=loop,
                start=start,
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
                            x.set_speed(max(0.1, speed * (1 - wdratio)))
                    except AttributeError:
                        print(traceback.format_exc())

                if file and (handle in self.runningSounds):
                    targetVol = self.runningSounds[handle].finalGain
                    self.set_volume(min(1, targetVol * firatio),
                                    handle, final=False)

                    if windup:
                        wuratio = max(
                            0, min(1, ((time.monotonic() - t) / windup)))
                        self.set_speed(
                            max(0.1, min(speed, wuratio * speed, 8)), handle)

                # Don't overwhelm the backend with commands
                time.sleep(max(1 / 48.0, time.monotonic() - tr))

            try:
                targetVol = self.runningSounds[handle].finalGain
            except KeyError:
                targetVol = -1

            if not targetVol == -1:
                try:
                    self.set_volume(min(1, targetVol), handle)
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
    "test": TestSoundWrapper
}

backend = SoundWrapper()
if util.which("pulseaudio"):
    pulseaudio = True
else:
    pulseaudio = False

# MPV is alwaus auto chosen if available!!!
# All the others are deprecated!!
for i in list(config["audio-backends"]):
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


def stop_all_sounds():
    midi.all_notes_off()
    backend.stop_all_sounds()


# Stop any old pulseaudio or something sound players that
# May have been running before jack started, otherwise they will just sit
# there doing nothing and that may be a problem.


def sasWrapper(*a):
    stop_all_sounds()


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
stop_sound = backend.stop_sound
is_playing = backend.is_playing
resolve_sound = soundPath
pause = backend.pause
resume = backend.resume
setvol = backend.set_volume
position = backend.get_position
fade_to = backend.fade_to
readySound = backend.readySound
preload = backend.preload

isStartDone = []
