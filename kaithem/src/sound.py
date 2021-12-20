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

from . import gstwrapper
import subprocess
import os
import math
import time
import sys
import threading
import collections
import logging
import re
import uuid
import traceback
import scullery
from scullery import iceflow, fluidsynth
from . import util, scheduling, directories, workers, registry, widgets, messagebus, midi
from .config import config

import gc
from . import gstwrapper, jackmanager, jackmixer
log = logging.getLogger("system.sound")

jackAPIWidget = None

jackClientsFound = False


def tryCloseFds(p):
    if not p:
        return
    try:
        p.stdout.close()
    except:
        pass
    try:
        p.stderr.close()
    except:
        pass
    try:
        p.stdin.close()
    except:
        pass


sound_paths = [""]

p = config['audio-paths']
for i in p:
    if i == '__default__':
        sound_paths.append(os.path.join(directories.datadir, "sounds"))
    else:
        sound_paths.append(i)

builtinSounds = os.listdir(os.path.join(directories.datadir, "sounds"))


def soundPath(fn, extrapaths=[]):
    "Get the full path of a sound file by searching"
    filename = util.search_paths(fn, extrapaths)
    if not filename:
        filename = util.search_paths(fn, sound_paths)

    # Search all module media folders
    if not filename:
        for i in os.listdir(os.path.join(directories.vardir, "modules",
                                         'data')):
            p = os.path.join(directories.vardir, "modules", 'data', i,
                             "__filedata__", 'media')
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
                if not self.runningSounds[i].isPlaying():
                    self.runningSounds.pop(i)
            except KeyError:
                pass

    def stopAllSounds(self):
        x = list(self.runningSounds.keys())
        for i in x:
            try:
                self.runningSounds.pop(i)
            except KeyError:
                pass

    def getPosition(self, channel="PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].position()
        except KeyError:
            return False

    def setVolume(self, channel="PRIMARY"):
        pass

    def setEQ(self, channel="PRIMARY"):
        pass

    def playSound(self, filename, handle="PRIMARY", **kwargs):
        pass

    def stopSound(self, handle="PRIMARY"):
        pass

    def isPlaying(self, handle="blah"):
        return False

    def pause(self, handle="PRIMARY"):
        pass

    def resume(self, handle="PRIMARY"):
        pass

    def fadeTo(self, handle="PRIMARY"):
        self.playSound(self, handle)

    def preload(self, filename):
        pass

    def seek(self, position, channel="PRIMARY"):
        try:
            return self.runningSounds[channel].seek(position)
        except KeyError:
            pass


class MadPlayWrapper(SoundWrapper):
    backendname = "MadPlay Sound Player"

    # What this does is it keeps a reference to the sound player process and
    # If the object is destroyed it destroys the process stopping the sound
    # It also abstracts checking if its playing or not.
    class MadPlaySoundContainer(object):
        def __init__(self, filename, **kwargs):
            f = open(os.devnull, "w")
            g = open(os.devnull, "w")
            cmd = ["madplay", filename]
            self.loopcounter = - \
                1 if kwargs.get('loop', False) is True else kwargs.get(
                    'loop', False)-1
            if self.loopcounter:
                self.end = False

                def loop_play_again():
                    self.process.poll()
                    if self.process.returncode == None:
                        return True
                    if not self in backend.runningSounds.values():
                        return False
                    if not self.loopcounter:
                        return False
                    if self.end:
                        return
                    self.loopcounter -= 1
                    try:
                        self.process.terminate()
                        tryCloseFds(self.process)
                    except:
                        pass
                    self.process = subprocess.Popen(cmd, stdout=f, stderr=g)
                    return True

                self.loop_repeat_func = loop_play_again
                scheduling.RepeatWhileEvent(loop_play_again, 0.05).register()
            self.process = subprocess.Popen(cmd, stdout=f, stderr=g)

        def __del__(self):
            try:
                self.process.terminate()
                tryCloseFds(self.process)
                del self.loop_repeat_func
            except:
                pass

        def isPlaying(self):
            self.process.poll()
            return self.process.returncode == None or bool(self.loopcounter)

    def playSound(self, filename, handle="PRIMARY", extraPaths=[], **kwargs):
        # Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        fn = soundPath(filename, extraPaths)

        # Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.MadPlaySoundContainer(fn, **kwargs)

    def stopSound(self, handle="PRIMARY"):
        # Delete the sound player reference object and its destructor will stop the sound
        if handle in self.runningSounds:
            # Instead of using a lock lets just catch the error is someone else got there first.
            try:
                del self.runningSounds[handle]
            except KeyError:
                pass

    def stopAllSounds(self):
        x = list(self.runningSounds.keys())
        for i in x:
            try:
                self.runningSounds[i].end = True
                self.runningSounds.pop(i)
            except KeyError:
                raise


class Mpg123Wrapper(SoundWrapper):
    backendname = "MPG123 Sound Player"

    # What this does is it keeps a reference to the sound player process and
    # If the object is destroyed it destroys the process stopping the sound
    # It also abstracts checking if its playing or not.
    class Mpg123SoundContainer(object):
        def __init__(self, filename, **kwargs):
            f = open(os.devnull, "w")
            g = open(os.devnull, "w")
            cmd = ["mpg123", filename]
            self.loopcounter = - \
                1 if kwargs.get('loop') is True else kwargs.get('loop')-1
            if self.loopcounter:
                self.end = False

                def loop_play_again():
                    self.process.poll()
                    if self.process.returncode == None:
                        return True
                    if not self in backend.runningSounds.values():
                        return False
                    if not self.loopcounter:
                        return False
                    if self.end:
                        return
                    self.loopcounter -= 1
                    try:
                        self.process.terminate()
                    except:
                        pass
                    tryCloseFds(self.process)

                    self.process = subprocess.Popen(cmd, stdout=f, stderr=g)
                    return True

                self.loop_repeat_func = loop_play_again
                scheduling.RepeatWhileEvent(loop_play_again, 0.05).register()
            self.process = subprocess.Popen(cmd, stdout=f, stderr=g)

        def __del__(self):
            try:
                self.process.terminate()
                del self.loop_repeat_func
                tryCloseFds(self.process)
            except:
                pass

        def isPlaying(self):
            self.process.poll()
            return self.process.returncode == None or bool(self.loopcounter)

    def playSound(self, filename, handle="PRIMARY", extraPaths=[], **kwargs):
        # Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()

        fn = soundPath(filename, extraPaths)

        # Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.Mpg123SoundContainer(fn, **kwargs)

    def stopSound(self, handle="PRIMARY"):
        # Delete the sound player reference object and its destructor will stop the sound
        if handle in self.runningSounds:
            # Instead of using a lock lets just catch the error is someone else got there first.
            try:
                del self.runningSounds[handle]
            except KeyError:
                pass

    def stopAllSounds(self):
        x = list(self.runningSounds.keys())
        for i in x:
            try:
                self.runningSounds[i].end = True
                self.runningSounds.pop(i)
            except KeyError:
                raise


class SOXWrapper(SoundWrapper):
    backendname = "SOund eXchange"

    # What this does is it keeps a reference to the sound player process and
    # If the object is destroyed it destroys the process stopping the sound
    # It also abstracts checking if its playing or not.
    class SOXSoundContainer(object):
        def __init__(self, filename, vol, start, end, loop=1):
            f = open(os.devnull, "w")
            g = open(os.devnull, "w")
            self.started = time.time()
            self.process = subprocess.Popen([
                "play", filename, "vol",
                str(vol), "trim",
                str(start),
                str(end)
            ],
                                            stdout=f,
                                            stderr=g)
            self.loopcounter = -1 if loop is True else loop - 1
            if self.loopcounter:
                self.end = False

                def loop_play_again():
                    self.process.poll()
                    if self.process.returncode == None:
                        return True
                    if not self in backend.runningSounds.values():
                        return False
                    if not self.loopcounter:
                        return False
                    if self.end:
                        return
                    self.loopcounter -= 1
                    try:
                        self.process.terminate()
                    except:
                        pass
                    tryCloseFds(self.process)
                    self.process = subprocess.Popen([
                        "play", filename, "vol",
                        str(vol), "trim",
                        str(start),
                        str(end)
                    ],
                                                    stdout=f,
                                                    stderr=g)
                    return True

                self.loop_repeat_func = loop_play_again
                scheduling.RepeatWhileEvent(loop_play_again, 0.02).register()
            else:
                self.process = subprocess.Popen([
                    "play", filename, "vol",
                    str(vol), "trim",
                    str(start),
                    str(end)
                ],
                                                stdout=f,
                                                stderr=g)

        def __del__(self):
            try:
                self.process.terminate()
                del self.loop_repeat_func
                tryCloseFds(self.process)
            except:
                pass

        def isPlaying(self):
            self.process.poll()
            return self.process.returncode == None or bool(self.loopcounter)

        def position(self):
            return self.started

    def stopAllSounds(self):
        x = list(self.runningSounds.keys())
        for i in x:
            try:
                self.runningSounds[i].end = True
                self.runningSounds.pop(i)
            except KeyError:
                raise

    def playSound(self, filename, handle="PRIMARY", extraPaths=[], **kwargs):

        if 'volume' in kwargs:
            # odd way of throwing errors on non-numbers
            v = float(kwargs['volume'])
        else:
            v = 1

        if 'start' in kwargs:
            # odd way of throwing errors on non-numbers
            start = float(kwargs['start'])
        else:
            start = 0

        if 'end' in kwargs:
            # odd way of throwing errors on non-numbers
            end = float(kwargs['end'])
        else:
            end = "-0"

        # Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        # Raise an error if the file doesn't exist
        fn = soundPath(filename, extraPaths)

        # Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.SOXSoundContainer(fn,
                                                            v,
                                                            start,
                                                            end,
                                                            loop=kwargs.get(
                                                                'loop', 1))

    def stopSound(self, handle="PRIMARY"):
        # Delete the sound player reference object and its destructor will stop the sound
        if handle in self.runningSounds:
            # Instead of using a lock lets just catch the error is someone else got there first.
            try:
                self.runningSounds[i].end = True
                del self.runningSounds[handle]
            except KeyError:
                pass

    def isPlaying(self, channel="PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].isPlaying()
        except KeyError:
            return False


objectPoolLock = threading.Lock()

objectPool = []


class RemoteMPV():
    def __del__(self):
        self.stop()

    def __init__(self, *a, **k):
        # -*- coding: utf-8 -*-

        #If del can't find this it would to an infinite loop
        self.worker = None
        self.stopping = False
        from jsonrpyc import RPC
        from subprocess import PIPE, STDOUT
        from reap import Popen
        f = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "mpv_server.py")
        self.lock = threading.RLock()
        env = {}
        env.update(os.environ)
        env['GST_DEBUG'] = '0'
        self.worker = Popen(['python3', f],
                            stdout=PIPE,
                            stdin=PIPE,
                            stderr=STDOUT,
                            env=env)
        self.rpc = RPC(target=self,
                       stdin=self.worker.stdout,
                       stdout=self.worker.stdin,
                       daemon=True)

        self.usesCounter = 0

    def stop(self):
        if self.stopping:
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
        except:
            #I hate this. But I guess it's rather obvious if the stop function doesn't work,
            #And this makes nuisance errors if the process is already dead.
            pass

        self.worker.kill()
        self.worker.wait()
        tryCloseFds(self.worker)

    def print(self, s):
        print(s)


class MPVBackend(SoundWrapper):
    @staticmethod
    def testAvailable():
        try:
            import mpv
            return True
        except:
            pass

    backendname = "MPV"

    # What this does is it keeps a reference to the sound player process and
    # If the object is destroyed it destroys the process stopping the sound
    # It also abstracts checking if its playing or not.
    class MPVSoundContainer(object):
        def __init__(self, filename, vol, finalGain, output, loop):
            self.lock = threading.RLock()

            if output == "__disable__":
                return

            #I think this leaks memory when created and destroyed repeatedly
            with objectPoolLock:
                if len(objectPool):
                    self.player = objectPool.pop()
                else:
                    self.player = RemoteMPV()

            #Avoid somewhat slow RPC calls if we can
            if (not hasattr(self.player,
                            'isConfigured')) or (not self.player.isConfigured):
                cname = "kplayer" + str(time.monotonic()) + "_out"

                self.player.rpc.call('set', ['vid', 'no'])
                self.player.rpc.call('set', ['ao', 'jack,pulse,alsa'])
                self.player.rpc.call('set', ['jack_name', cname])
                self.player.rpc.call('set', ['gapless_audio', 'weak'])
                self.player.isConfigured = True

            #Due to memory leaks, these have a limited lifespan
            self.player.usesCounter += 1
            #For legavy reasons some stuff used tens of millions instead of actual infinite loop.
            #But it seems mpv ignores everything past a certain number. So we replace effectively forever with
            #actually forever to get the same effect, assuming that was user intent.
            if not (loop == -1 or loop > 900000000):
                self.player.rpc.call(
                    'set',
                    ['loop_playlist', int(max(loop, 1))])
            else:
                self.player.rpc.call('set', ['loop_playlist', "inf"])

            self.player.rpc.call('set', ['volume', vol * 100])
            self.volume = vol
            self.finalGain = finalGain if not finalGain == None else vol

            if output:
                if not ":" in output:
                    self.player.rpc.call('set', ['jack_port', output + ":*"])
                else:
                    self.player.rpc.call('set', ['jack_port', output])
            self.started = time.time()

            if filename:
                self.player.rpc.call('call', ['play', filename],
                                     block=0.001,
                                     timeout=3)

        def __del__(self):
            self.stop()

        def stop(self):
            bad = True
            if hasattr(self, 'player'):
                #Only do the maybe recycle logic when stopping a still good SFX
                try:
                    w = self.player.worker
                except:
                    return
                if w.poll() == None:
                    try:
                        with self.lock:
                            self.player.rpc.call('call', ["stop"],
                                                 block=0.001,
                                                 timeout=1)
                        bad = False
                    except:
                        #Sometimes two threads try to stop this at the same time and we get a race condition
                        #I really hate this but stopping a crashed sound can't be allowed to take down anything else.
                        pass

                #When the player only has a few uses left, if we don't have many spare objects in
                #the pool, we are going to make the replacement ahead of time in a background thread.
                #But try tpo only make one replacement per object, we don't actually want to go up to the max
                #in the pool because they can use CPU in the background
                if bad or self.player.usesCounter > 8:
                    if not hasattr(self.player, "alreadyMadeReplacement"):
                        if (len(objectPool) <
                                3) or self.player.usesCounter > 10:
                            self.player.alreadyMadeReplacement = True

                            def f():
                                #Can't make it under lock that is slow
                                o = RemoteMPV()
                                with objectPoolLock:
                                    if len(objectPool) < 4:
                                        objectPool.append(o)
                                        return
                                o.stop()

                            workers.do(f)

                if bad or self.player.usesCounter > 10:
                    self.player.stop()

                else:
                    with objectPoolLock:
                        p = self.player
                        if p:
                            if len(objectPool) < 4:
                                objectPool.append(p)
                            else:
                                self.player.stop()
                self.player = None

        def isPlaying(self):
            with self.lock:
                if not hasattr(self, 'player'):
                    return False
                try:
                    return self.player.rpc.call('get', ['eof_reached'],
                                                block=0.001) == False
                except:
                    logging.exception(
                        "Error getting playing status, assuming closed")
                    return False

        def position(self):
            return time.time() - self.started

        def wait(self):
            with self.lock:
                # Block until sound is finished playing.
                self.player.rpc.call('wait_for_playback',
                                     block=0.001,
                                     timeout=5)

        def seek(self, position):
            pass

        def setVol(self, volume, final=True):
            with self.lock:
                self.volume = volume
                if final:
                    self.finalGain = volume
                self.player.rpc.call('set', ['volume', volume * 100],
                                     block=0.001)

        def getVol(self):
            with self.lock:
                return self.player.rpc.call('get', ['volume'], block=0.001)

        def setEQ(self, eq):
            pass

        def pause(self):
            with self.lock:
                self.player.rpc.call('set', ['pause', True])

        def resume(self):
            with self.lock:
                self.player.rpc.call('set', ['pause', False])

    def playSound(self,
                  filename,
                  handle="PRIMARY",
                  extraPaths=[],
                  volume=1,
                  finalGain=None,
                  output='',
                  loop=1):

        # Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        # Raise an error if the file doesn't exist
        fn = soundPath(filename, extraPaths)
        # Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.MPVSoundContainer(
            fn, volume, finalGain, output, loop)

    def stopSound(self, handle="PRIMARY"):
        # Delete the sound player reference object and its destructor will stop the sound
        if handle in self.runningSounds:
            # Instead of using a lock lets just catch the error is someone else got there first.
            try:
                x = self.runningSounds[handle]
                try:
                    x.stop()
                except:
                    logging.exception("Error stopping")
                del self.runningSounds[handle]
                x.nocallback = True
                del x
            except KeyError:
                pass

    def isPlaying(self, channel="PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].isPlaying()
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

    def seek(self, position, channel="PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].seek(position)
        except KeyError:
            pass

    def setEQ(self, eq, channel="PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].setEQ(eq)
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

    def fadeTo(self,
               file,
               length=1.0,
               block=False,
               handle="PRIMARY",
               output='',
               volume=1,
               **kwargs):
        x = self.runningSounds.pop(handle, None)

        if x and not length:
            x.stop()

        k = kwargs.copy()
        k.pop('volume', 0)

        # Allow fading to silence
        if file:
            self.playSound(file,
                           handle=handle,
                           volume=0,
                           output=output,
                           finalGain=volume,
                           loop=kwargs.get('loop', 1))

        #if not x:
        #    return
        if not length:
            return

        def f():
            t = time.monotonic()
            try:
                v = x.volume
            except:
                v = 0

            targetVol = 1
            while time.monotonic() - t < length:
                ratio = max(0, min(1, ((time.monotonic() - t) / length)))

                tr = time.monotonic()

                if x:
                    x.setVol(max(0, v * (1 - ratio)))

                if file and (handle in self.runningSounds):
                    targetVol = self.runningSounds[handle].finalGain
                    self.setVolume(min(1, targetVol * ratio),
                                   handle,
                                   final=False)

                #Don't overwhelm the backend with commands
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


import weakref

l = {
    'sox': SOXWrapper,
    'mpg123': Mpg123Wrapper,
    "madplay": MadPlayWrapper,
    'mpv': MPVBackend
}

backend = SoundWrapper()
if util.which('pulseaudio'):
    pulseaudio = True
else:
    pulseaudio = False

#MPV is alwaus auto chosen if available!!!
#All the others are deprecated!!
for i in ['mpv'] + list(config['audio-backends']):
    if not i in l:
        continue
    try:
        if util.which(i) or l[i].testAvailable():
            backend = l[i]()
            break
    except:
        messagebus.postMessage(
            "/system/notifications/errors",
            "Failed to initialize audio backend " + i +
            " may be able to use fallback:\n" + traceback.format_exc())


def stopAllSounds():
    midi.allNotesOff()
    backend.stopAllSounds()


# Stop any old pulseaudio or something sound players that
# May have been running before jack started, otherwise they will just sit
# there doing nothing and that may be a problem.


def sasWrapper(*a):
    stopAllSounds()


messagebus.subscribe("/system/sound/jackstart", sasWrapper)


def oggSoundTest(output=None):
    t = "KaithemOggSoundTest"
    playSound("alert.ogg", output=output, handle=t)
    for i in range(100):
        if isPlaying(t):
            return
        time.sleep(0.01)
    raise RuntimeError("Sound did not report as playing within 1000ms")


# Make fake module functions mapping to the bound methods.
playSound = backend.playSound
stopSound = backend.stopSound
isPlaying = backend.isPlaying
resolveSound = soundPath
pause = backend.pause
resume = backend.resume
setvol = backend.setVolume
setEQ = backend.setEQ
position = backend.getPosition
fadeTo = backend.fadeTo
readySound = backend.readySound
preload = backend.preload

isStartDone = []
if jackmanager.settings.get('jackMode',
                            None) in ("manage", "use", 'dummy', 'pipewire'):

    def f():
        try:
            logging.debug("Initializing JACK")
            jackmanager.reloadSettings()
            jackmanager.startManaging()

        except:
            log.exception("Error managing JACK")
        try:
            isStartDone.append(True)
        except:
            pass

    workers.do(f)
    # Wait up to 5 seconds
    t = time.monotonic()
    while (time.monotonic() - t) < 5:
        if len(isStartDone):
            break
        time.sleep(0.1)