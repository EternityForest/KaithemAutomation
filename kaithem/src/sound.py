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

MAX_PRELOADED = 8
gst_preloaded = {}
preloadlock = threading.Lock()


def volumeToDB(vol):
    if vol < 0.001:
        return -100

    # Note: Preserve legacy, but fix that crosover?
    if vol <= 1:
        # Calculated usiung curve fitting, assuming that 0 is 0db,
        # 0.5 is 10db below, etc.
        return -38.33333 + 77.80645*vol - 39.56989*vol**2
    else:
        # New high-volume curve
        return -23.33333 + 17.98981*vol - 1.432762*vol**2


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
        for i in os.listdir(os.path.join(directories.vardir, "modules", 'data')):
            p = os.path.join(directories.vardir, "modules",
                             'data', i, "__filedata__", 'media')
            filename = util.search_paths(fn, [p])
            if filename:
                break

    # Raise an error if the file doesn't exist
    if not filename or not os.path.isfile(filename):
        raise ValueError("Specified audio file '"+fn+"' was not found")
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

    def resume(self,  handle="PRIMARY"):
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
            self.process = subprocess.Popen(["play", filename, "vol", str(
                vol), "trim", str(start), str(end)], stdout=f, stderr=g)
            self.loopcounter = -1 if loop is True else loop-1
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
                    self.process = subprocess.Popen(["play", filename, "vol", str(
                        vol), "trim", str(start), str(end)], stdout=f, stderr=g)
                    return True
                self.loop_repeat_func = loop_play_again
                scheduling.RepeatWhileEvent(loop_play_again, 0.02).register()
            else:
                self.process = subprocess.Popen(["play", filename, "vol", str(
                    vol), "trim", str(start), str(end)], stdout=f, stderr=g)

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
        self.runningSounds[handle] = self.SOXSoundContainer(
            fn, v, start, end, loop=kwargs.get('loop', 1))

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


class MPlayerWrapper(SoundWrapper):
    backendname = "MPlayer"

    # What this does is it keeps a reference to the sound player process and
    # If the object is destroyed it destroys the process stopping the sound
    # It also abstracts checking if its playing or not.
    class MPlayerSoundContainer(object):
        def __init__(self, filename, vol, start, end, extras, **kw):
            self.lock = threading.RLock()
            f = open(os.devnull, "w")
            g = open(os.devnull, "w")
            self.nocallback = False
            self.paused = False
            self.volume = vol
            cmd = ["mplayer", "-nolirc", "-slave",
                   "-quiet", "-softvol", "-ss", str(start)]

            if end:
                cmd.extend(["-endpos", str(end)])

            if "output" in kw and kw['output']:
                x = kw['output']

                cmd.extend(["-ao", x])


            if "video_output" in kw:
                cmd.extend(["-vo", kw['output']])

            if "fs" in kw and kw['fs']:
                cmd.extend(["-fs"])

            if "novideo" in kw and kw['novideo']:
                cmd.extend(["-novideo"])

            if "pan" in kw and kw['pan']:
                pan = ",pan="+":".join(str(i) for i in kw["pan"])
            else:
                pan = ""

            if 'eq' in extras:
                if extras['eq'] == 'party':
                    cmd.extend(['-af', 'equalizer=0:1.5:2:-7:-10:-5:-10:-10:1:1,volume='+str((10*math.log10(vol or 10**-30)+5))+pan

                                ])
                else:
                    cmd.extend(['-af', 'equalizer=' + ":".join(extras['eq'])+",volume="+str((10*math.log10(vol or 10**-30)+5))+pan
                                ])
            else:
                cmd.extend(
                    ["-af", "volume="+str(10*math.log10(vol or 10**-30))+pan])

            if 'loop' in kw:
                cmd.extend(
                    ["-loop", str(0 if kw['loop'] is True else int(kw['loop']))])

            self.started = time.time()
            cmd.append(filename)
            self.process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=f, stderr=g)
            # We don't want to slow things down by waiting, but we can at least catch some of the errors that happen fast.
            self.process.poll()
            if not self.process.returncode in (None, 0):
                raise RuntimeError(
                    "Mplayer nonzero error code: "+str(self.process.returncode))

            x = kw.get('callback', False)
            if x:
                def f():
                    if self.isPlaying():
                        return True
                    else:
                        if not self.nocallback:
                            x()
                        return False
                self.callback = f
                scheduling.RepeatWhileEvent(f, 0.1).register()

        def __del__(self):
            try:
                self.process.terminate()
                tryCloseFds(self.process)
            except:
                pass

        def stop(self):
            try:
                self.process.terminate()
                tryCloseFds(self.process)

            except:
                pass

        def isPlaying(self):
            self.process.poll()
            return self.process.returncode == None

        def position(self):
            return time.time() - self.started

        def wait(self):
            # Block until sound is finished playing.
            self.process.wait()

        def seek(self, position):
            with self.lock:
                if self.isPlaying():
                    try:
                        if sys.version_info < (3, 0):
                            self.process.stdin.write(
                                bytes("pausing_keep seek "+str(position)+" 2\n"))
                        else:
                            self.process.stdin.write(
                                bytes("pausing_keep seek "+str(position)+" 2\n", 'utf8'))
                        self.process.stdin.flush()
                        self.started = time.time()-position
                    except:
                        pass

        def setVol(self, volume):
            self.volume = volume
            with self.lock:
                if self.isPlaying():
                    try:
                        if sys.version_info < (3, 0):
                            self.process.stdin.write(
                                bytes("pausing_keep volume "+str(volume*100)+" 1\n"))
                        else:
                            self.process.stdin.write(
                                bytes("pausing_keep volume "+str(volume*100)+" 1\n", 'utf8'))
                        self.process.stdin.flush()
                    except:
                        pass

        def setEQ(self, eq):
            with self.lock:
                if self.isPlaying():
                    try:
                        if sys.version_info < (3, 0):
                            self.process.stdin.write(bytes(
                                "pausing_keep af_cmdline equalizer "+":".join([str(i) for i in eq]) + "\n"))
                        else:
                            self.process.stdin.write(bytes(
                                "pausing_keep af_cmdline equalizer "+":".join([str(i) for i in eq]) + "\n", "utf8"))
                        self.process.stdin.flush()
                    except Exception as e:
                        raise e

        def pause(self):
            with self.lock:
                try:
                    if not self.paused:
                        self.process.stdin.write(b"pause \n")
                        self.process.stdin.flush()
                        self.paused = True
                except:
                    pass

        def resume(self):
            with self.lock:
                try:
                    if self.paused:
                        self.process.stdin.write(b"pause \n")
                        self.process.stdin.flush()
                        self.paused = False
                except:
                    pass

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
            end = None

        if 'output' in kwargs:
            e = {"output": kwargs['output']}
        else:
            e = {}

        if 'fs' in kwargs:
            e['fs'] = kwargs['fs']

        if 'loop' in kwargs:
            e['loop'] = kwargs['loop']
        if 'pan' in kwargs:
            e['pan'] = kwargs['pan']

        if 'novideo' in kwargs:
            e['novideo'] = kwargs['novideo']

        if 'eq' in kwargs:
            extras = {'eq': kwargs['eq']}
        else:
            extras = {}
        # Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        # Raise an error if the file doesn't exist
        fn = soundPath(filename, extraPaths)
        # Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.MPlayerSoundContainer(
            fn, v, start, end, extras, **e)

    def stopSound(self, handle="PRIMARY"):
        # Delete the sound player reference object and its destructor will stop the sound
        if handle in self.runningSounds:
            # Instead of using a lock lets just catch the error is someone else got there first.
            try:
                x = self.runningSounds[handle]
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

    def setVolume(self, vol, channel="PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].setVol(vol)
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

    def fadeTo(self, file, length=1.0, block=False, handle="PRIMARY", **kwargs):
        try:
            x = self.runningSounds[handle]
        except KeyError:
            x = None
        if x and not length:
            x.stop()

        k = kwargs.copy()
        k.pop('volume', 0)

        # Allow fading to silence
        if file:
            self.playSound(file, handle=handle, volume=0, **kwargs)

        if not x:
            return
        if not length:
            return

        try:
            v = x.volume
        except:
            return

        def f():
            t = time.monotonic()

            while x and time.monotonic()-t < length:
                x.setVol(max(0, v * (1-(time.monotonic()-t)/length)))
                self.setVolume(min(1, kwargs.get('volume', 1) *
                                   ((time.monotonic()-t)/length)), handle)
                time.sleep(1/48.0)
            if x:
                x.stop()
        if block:
            f()
        else:
            workers.do(f)




objectPoolLock = threading.Lock()

objectPool = []


class RemoteMPV():
    def __del__(self):
        self.stop()

    def __init__(self, *a,**k):
        # -*- coding: utf-8 -*-

        #If del can't find this it would to an infinite loop
        self.worker = None
        self.stopping=False
        from jsonrpyc import RPC
        from subprocess import Popen, PIPE, STDOUT
        f = os.path.join(os.path.dirname(os.path.abspath(__file__)),"mpv_server.py")
        self.lock=threading.RLock()
        env={}
        env.update(os.environ)
        env['GST_DEBUG']='0'
        self.worker = Popen(['python3', f], stdout=PIPE, stdin=PIPE, stderr=STDOUT, env=env)
        self.rpc = RPC(target=self,stdin=self.worker.stdout, stdout=self.worker.stdin,daemon=True)

        self.usesCounter = 0

    def stop(self):
        if self.stopping:
            return
        self.stopping=True
        self.rpc.stopFlag=True
        # v =  self.rpc.call('get',['volume'],block=0.001)
        # self.rpc.call('set',['volume',v/2])
        # self.rpc.call('set',['volume',v/8])
        # self.rpc.call('set',['volume',0])

        try:
            self.rpc.call("call",["stop"],block=0.001,timeout=1)
        except TimeoutError:
            pass
        except:
            #I hate this. But I guess it's rather obvious if the stop function doesn't work,
            #And this makes nuisance errors if the process is already dead.
            pass

        self.worker.kill()
        self.worker.wait()
        tryCloseFds(self.worker)

    def print(self,s):
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
        def __init__(self, filename, vol, finalGain,output, loop):            
            self.lock = threading.RLock()

            if output=="__disable__":
                return

            #I think this leaks memory when created and destroyed repeatedly
            with objectPoolLock:
                if len(objectPool):
                    self.player=objectPool.pop()
                else:
                    self.player = RemoteMPV()

            #Avoid somewhat slow RPC calls if we can
            if not hasattr(self.player, 'isConfigured'):
                cname = "kplayer"+str(time.monotonic())+"_out"

                self.player.rpc.call('set',['no_video',True])
                self.player.rpc.call('set',['ao','jack,pulse,alsa'])
                self.player.rpc.call('set',['jack_name',cname])
                self.player.rpc.call('set',['gapless_audio','weak'])
                self.player.isConfigured=True

            #Due to memory leaks, these have a limited lifespan
            self.player.usesCounter +=1
            if not loop==-1:
                self.player.rpc.call('set',['loop_playlist',int(max(loop,1))])
            else:
                self.player.rpc.call('set',['loop_playlist',"inf"])

            self.player.rpc.call('set',['volume',vol*100])
            self.volume = vol
            self.finalGain=finalGain if not finalGain==None else vol


            if output:
                if not ":" in output:
                    self.player.rpc.call('set',['jack_port',output+":*"])
                else:
                    self.player.rpc.call('set',['jack_port',output])
            self.started = time.time()

            if filename:
                self.player.rpc.call('call',['play',filename],block=0.001,timeout=3)



        def __del__(self):
            self.stop()

        def stop(self):
            bad=True
            if hasattr(self,'player'):
                #Only do the maybe recycle logic when stopping a still good SFX
                try:
                    w=self.player.worker
                except:
                    return
                if w.poll()==None:
                    try:
                        with self.lock:
                            self.player.rpc.call('call',["stop"],block=0.001,timeout=1)
                        bad=False
                    except:
                        #Sometimes two threads try to stop this at the same time and we get a race condition
                        #I really hate this but stopping a crashed sound can't be allowed to take down anything else.
                        pass
                    

                if bad or self.player.usesCounter>10:
                    if len(objectPool)<4:
                        def f():
                            #Can't make it under lock that is slow
                            o=RemoteMPV()
                            with objectPoolLock:
                                if len(objectPool)<4:
                                    objectPool.append(o)
                                    return
                            o.stop()
                        workers.do(f)
                                                    
                    self.player.stop()

                else:
                    with objectPoolLock:
                        p=self.player
                        if p:
                            if len(objectPool)<4:
                                objectPool.append(p)
                            else:
                                self.player.stop()
                self.player=None
            


        def isPlaying(self):
            with self.lock:
                if not hasattr(self,'player'):
                    return False
                try:
                    return self.player.rpc.call('get',['eof_reached'],block=0.001)==False
                except:
                    logging.exception("Error getting playing status, assuming closed")
                    return False

        def position(self):
            return time.time() - self.started

        def wait(self):
            with self.lock:
                # Block until sound is finished playing.
                self.player.rpc.call('wait_for_playback',block=0.001,timeout=5)

        def seek(self, position):
            pass

        def setVol(self, volume,final=True):
            with self.lock:
                self.volume = volume
                if final:
                    self.finalGain = volume
                self.player.rpc.call('set',['volume',volume*100],block=0.001)

        def getVol(self):
            with self.lock:
                return self.player.rpc.call('get',['volume'],block=0.001)

        def setEQ(self, eq):
            pass

        def pause(self):
            with self.lock:
                self.player.rpc.call('set',['pause',True])

        def resume(self):
            with self.lock:
                self.player.rpc.call('set',['pause',False])

    def playSound(self, filename, handle="PRIMARY", extraPaths=[], volume=1, finalGain=None,output='',loop=1):

        # Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        # Raise an error if the file doesn't exist
        fn = soundPath(filename, extraPaths)
        # Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.MPVSoundContainer(
            fn, volume, finalGain,output,loop)

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

    def setVolume(self, vol, channel="PRIMARY",final=True):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].setVol(vol,final=final)
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

    def fadeTo(self, file, length=1.0, block=False, handle="PRIMARY", output='', volume=1, **kwargs):
        x = self.runningSounds.pop(handle,None)

        if x and not length:
            x.stop()

        k = kwargs.copy()
        k.pop('volume', 0)

        # Allow fading to silence
        if file:
            self.playSound(file, handle=handle, volume=0,output=output, finalGain= volume,loop=kwargs.get('loop',1))

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

            targetVol =1
            while time.monotonic()-t < length:
                ratio = max(0, min(1,((time.monotonic()-t)/length)))

              

                tr=time.monotonic()

                if x:
                    x.setVol(max(0, v * (1-ratio)))

                if file and (handle in self.runningSounds):
                    targetVol = self.runningSounds[handle].finalGain
                    self.setVolume(min(1, targetVol*ratio),
                                   handle, final=False)

                #Don't overwhelm the backend with commands
                time.sleep(max(1/48.0, time.monotonic()-tr))
            
            try:
                targetVol = self.runningSounds[handle].finalGain
            except KeyError:
                targetVol=-1

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

gstplayers = weakref.WeakValueDictionary()


class GSTAudioFilePlayer(gstwrapper.Pipeline):
    def __init__(self, file, volume=1, output="@auto", onBeat=None, _prevPlayerObject=None, systemTime=False, loop=False):
        
        #Fix rare getattr and del related loop
        self.ended =None
        self.worker =None


        gstplayers[id(self)]=self

        try:
            nplayers=len(gstplayers)
        except:
            nplayers=0
        
        if nplayers>32:
            gc.collect()
            if nplayers>32:
               raise RuntimeError("Way too many running sounds here, somethingis probably wrong.")


        gstwrapper.Pipeline.__init__(self, str(uuid.uuid4()), systemTime=False)

        global jackClientsFound
      
        if not output:
            output = "@auto"
        
        self.output = output

        self.outputName = output
        self.filename = file

        self.finalGain = volume

        self.lastFileSize = os.stat(file).st_size

        if self.lastFileSize == 0:
            for i in range(10):
                self.lastFileSize = os.stat(file).st_size
                if self.lastFileSize > 0:
                    break
                time.sleep(1)

        if self.lastFileSize == 0:
            raise RuntimeError("File was still zero bytes after 10 seconds")

        self.lastPosition = 0

        self.lastFileSizeChange = 0
        self.aw = None
        self.ended = False

        self.lastBeat = 0
        self.peakDetect = 0
        self.detectedBeatInterval = 1/60
        self.beat = onBeat

        self._prevPlayerObject = _prevPlayerObject

        if not file=="__empty__":
            self.src = self.addElement('filesrc', location=file)
        else:
            self.src = self.addElement('filesrc')
        #self.queue = self.addElement("queue")

        if not file.endswith(".mid"):
            decodeBin = self.addElement('decodebin', low_percent=15)
            # if loop:
            #    decodeBin.connect('drained',self.doLoop)
        else:
            # Use FluidSynth to handle MIDI, the default seems to crash on the Pi and not have very good quality.
            self.addElement("midiparse")
            decodeBin = self.addElement(
                "fluiddec", synth_chorus=False, soundfont=fluidsynth.findSoundFont())
        # self.addElement('audiotestsrc')
        isVideo = False

        for i in (".mkv", ".flv", ".wmv", ".mp4", ".avi"):
            if file.endswith(i):
                isVideo = True
        if isVideo:
            decodeBin.set_property("low-percent", 80)
            # TODO queue in a better place

            self.addElement('audiorate', connectToOutput=decodeBin,
                            connectWhenAvailable="audio")
            self.addElement('audioconvert')

        else:
            self.addElement(
                'audioconvert', connectToOutput=decodeBin, connectWhenAvailable="audio")

        self.addElement('audioresample')

        self.lastQueue = self.addElement('queue')
        self.lastQueue.set_property("max-size-buffers", 100000)
        self.lastQueue.set_property("max-size-time", 20*10**9)

        self.loopsRemaining = loop

        if onBeat:
            self.addLevelDetector()

        self.addElement("audiorate")
        self.fader = self.addElement('volume')
        # Jump to the proper perceptual gain
        self.setFader(volume)


        doAirwire = False


        if output == "__disable__":
            self.addElement("fakesink", sync=False)

        elif output == "@auto":
            # Recheck if we thing the server hasn't started yet
            if not jackClientsFound:
                jackClientsFound = len(jackmanager.getPorts()) > 0

            if jackClientsFound:
                cname = "kplayer"+str(time.monotonic())+"_out"
                self.sink = self.addElement('jackaudiosink', buffer_time=32000,
                                            latency_time=32000, slave_method=0, port_pattern="jhjkhhhfdrhtecytey",
                                            connect=0, client_name=cname, sync=False)

                doAirwire=True

            else:
                if not scullery.jack.manageJackProcess:
                    self.sink = self.addElement('autoaudiosink')
                else:
                    self.stop()
                    logging.error(
                        "JACK is enabled but not running, cannot autoselect non-jack driver as this could interfere with JACK")
                    return

        elif output.startswith("@pulse"):
            s = output.split(":")
            if len(s) > 1:
                s = s[1]
            else:
                s = s[0]
            self.sink = self.addElement('pulsesink')

        elif output.startswith("@alsa:"):
            self.addElement('alsasink', device=output[6:])

        # No jack clients at all means it probably isn't running
        elif not jackClientsFound:

            if not jackmanager.settings.get('jackMode', None) in ("manage", "use"):
                self.stop()
                logging.error(
                    "JACK is enabled but not running, cannot autoselect non-jack driver as this could interfere with JACK")
                return
            if "hw:" in output or "usb:" in output:
                self.addElement('alsasink', device=output)
            else:
                raise ValueError("Bad output: "+output)

        # Default to just using jack
        else:
            cname = "player"+str(time.monotonic())+"_out"

            self.sink = self.addElement('jackaudiosink', buffer_time=16000 if not isVideo else 80000,
                                        latency_time=8000 if not isVideo else 40000, slave_method=0, port_pattern="jhjkhhhfdrhtecytey",
                                        connect=0, client_name=cname, sync=False)

            # Default to the system outout if nothing selected, even if jack in use.
            if not output:
                output = 'system'
            doAirwire=True
            
        # Get ready!
        self.pause()


        if doAirwire:
            self.aw = jackmanager.Airwire(cname, output)
            self.aw.connect()

    # def loopCallback(self):
    #     size= os.stat(self.filename).st_size
    #     if not size==self.lastFileSize:
    #         self.lastFileSizeChange = time.monotonic()
    #         self.lastFileSize=size

    #     self.lastPosition = self.getPosition()

    def doLoop(self, flush=False, *a, **k):
        # Implement native loop support
        if self.lock.acquire(timeout=1):
            try:

                if self.loopsRemaining > 0:
                    # HideousHack!
                    if self.getPosition() < 1:
                        time.sleep(max(0, 1-self.getPosition()))
                    self.seek(0, _offset=0, flush=flush,
                              segment=self.loopsRemaining > 0, sync=True)
                    # self.play(segment=self.loopsRemaining>0)
                    self.loopsRemaining -= 1
                else:
                    self.exitSegmentMode()

            finally:
                self.lock.release()



    def onSegmentDone(self):
        # If the file has changed size recently, this might not be a real EOS,
        # Just a buffer underrun. Lets just try again

        # For extremely small files, return to the preload queue. It may be a quick sound effect that should have the best response time
        # Probably best not to do this on early stop.  If the user is hammering a button maybe something is wrong.
        # try:
        #     if os.stat(self.filename).st_size< 300000:
        #         self.pause()
        #         self.seek(0)
        #         gst_preloaded[self.filename, self.outputName] = (self,time.monotonic())
        #         return
        # except:
        #     logging.exception("Preload logic err")

        if self.lastFileSizeChange > (time.monotonic()-3):
            self.pause()
            self.seek(self.lastPosition-0.1)
            time.sleep(3)
            self.play(segment=self.loopsRemaining > 0)
        else:
            # Don't shut everything off if we must loop!
            if self.loopsRemaining <= 0:
                gstwrapper.Pipeline.onEOS(self)
            else:
                self.doLoop()

    def setVol(self, v):
        # We are going to do a perceptual gain algorithm here
        db = volumeToDB(v)
        # Now convert to a raw gain
        vGain = 10**(db/20)
        self.setFader(vGain if not vGain < -0.01 else 0)

    def setFader(self, level,maxWait=5):

        #Lock is no longer critical. still try to keep it to rate
        #limit under heavy activity
        if self.lock.acquire(timeout=1):
            hasLock=True
        else:
            hasLock=False

        try:
            self.faderLevel = level
            if self.fader:
                self.fader.set_property('volume', level,maxWait=maxWait)
        except ReferenceError:
            pass

        finally:
            if hasLock:
                self.lock.release()


    def stop(self,preQuiet=True):

        # Prevent any ugly noise that GSTreamer might make when stopped at
        # The wrong time.  First an ultrafast fade, then disconnect, then stop,
        # For the best possible sound

        if self.worker.poll() is not None:
            self.worker.wait()
            return
        
        try:
            if not self.lock:
                return
            if self.ended:
                return
    
            
            self.loopsRemaining=0

            if preQuiet:
                try:
                    try:
                        self.setFader(self.faderLevel/1.5,maxWait=0.5)
                    except:
                        pass

                    try:
                        self.setFader(self.faderLevel/2,maxWait=0.1)
                    except:
                        pass
                    self.setFader(self.faderLevel/4,maxWait=0.1)
                except:
                    print(traceback.format_exc())
                    self.worker.kill()
                    workers.do(self.worker.wait)



    
            #Move this to a preload cache
            if False:#("__empty__",self.output) in gst_preloaded and not self.output in ["@auto",'__disable__']:
                with preloadlock:
                    if not ("__empty__",self.output) in gst_preloaded:
                        gst_preloaded[("__empty__", self.output)]= (self,time.monotonic())
            else:
                try:
                    if self.aw:
                        self.aw.disconnect()
                except:
                    logging.exception("Err disconnecting airwire")
                gstwrapper.Pipeline.stop(self)



            if self._prevPlayerObject:
                p = self._prevPlayerObject()
                #No idea how p could be self,but be defensive
                if p and not p is self:
                    p.stop()
            self.ended = True
        finally:
            def clean():
                self.worker.kill()
                self.worker.wait()
            workers.do(clean)

    

    def resume(self):
        self.play(segment=self.loopsRemaining > 0)

    def onStreamFinished(self):
        if self.loopsRemaining <= 0:
            #No pre quiet needed if already stoppe
            self.stop(False)
        


    def isPlaying(self):
        return not self.ended

    def addLevelDetector(self):
        self.addElement("level", post_messages=True,
                        peak_ttl=300*1000*1000, peak_falloff=60,interval=10**9/48)

    def onLevelMessage(self, src, rms,decay):
            if self.board:
                self.peakDetect = max(self.peakDetect, rms)
                timeSinceBeat = time.monotonic()-self.lastBeat

                threshold = self.peakDetect - \
                    (1 + (3*max(1, timeSinceBeat/self.detectedBeatInterval)))
                if timeSinceBeat > self.detectedBeatInterval/8:
                    if rms > threshold:
                        self.beat()
                        self.detectedBeatInterval = (
                            self.detectedBeatInterval*3 + timeSinceBeat)/4
                        self.peakDetect *= 0.996
            return True


class GStreamerBackend(SoundWrapper):
    backendname = "Gstreamer"

    @staticmethod
    def testAvailable():

        return not gstwrapper.testGst() == None
    # What this does is it keeps a reference to the sound player process and
    # If the object is destroyed it destroys the process stopping the sound
    # It also abstracts checking if its playing or not.

    class GStreamerContainer(object):
        def __init__(self, filename, output="@auto", **kwargs):

            self.pl=None
            self.ended = False
            if (filename, output) in gst_preloaded or  ("__empty__", output) in gst_preloaded:
                if preloadlock.acquire(timeout=1):
                    try:
                        if not kwargs.get('loop', 0) and (filename, output) in gst_preloaded:
                            self.pl = gst_preloaded[filename, output][0]
                            del gst_preloaded[filename, output]


                        #As it takes a really long time to spin up a new python instance,
                        # #We are going to always try to keep a ready to go player.
                        # elif not kwargs.get('loop', 0) and ("__empty__", output) in gst_preloaded:
                        #     self.pl = gst_preloaded['__empty__', output][0]
                        #     del gst_preloaded['__empty__', output]

                        #     #If we just used up the ready to go player, make another one unless we guess that this effect will be over before we need ot play anything else on the channel.
                        #     #Do that guess based on file size.  Since sound responsiveness is so noticable, assume that we always need 1 extra player channel per output.
                        #     if os.path.isfile(filename) and os.stat(filename).st_size> 512000:
                        #         def f():
                        #             with preloadlock:
                        #                 gst_preloaded['__empty__', output] =GSTAudioFilePlayer(filename, kwargs.get('volume', 1), output=output, loop=kwargs.get('loop', 0))
                        #         workers.do(f)
                        #     self.pl.location=filename
                        #     self.pl.seek(0)

                    finally:
                        preloadlock.release()
                else:
                    raise RuntimeError("Could not get lock")
            
            if not self.pl:
                self.pl = GSTAudioFilePlayer(filename, kwargs.get(
                                'volume', 1), output=output, loop=kwargs.get('loop', 0))

            self.pl.setVol(kwargs.get('volume', 1))
            if not kwargs.get('pause', 0):
                self.pl.start(segment=kwargs.get('loop', 0) > 0)
            else:
                self.pl.pause()

            self.volume = kwargs.get('volume', 1)

        def __del__(self):

            #All the graceful stopping stuff should have already happened by now.  At this
            #point we do not need to block things up redoing that.

            #Kill the json RPC thread associated with the pipeline proxy
            try:
                self.pl.stopFlag=True
            except:
                pass

            #Kill the actual BG process.
            try:
                self.pl.worker.kill()
            except:
                print(traceback.format_exc())

            workers.do(self.pl.worker.wait)


        def isPlaying(self):
            return not self.pl.ended

        def setVol(self, v, final=True):
            self.volume = v
            if final:
                self.finalGain = v
            self.pl.setVol(v)

        def pause(self):
            self.pl.pause()

        def resume(self):
            self.pl.start(segment=self.pl.loopsRemaining > 0)

        def stop(self):
            self.pl.loopsRemaining = 0
            self.pl.stop()
            try:
                self.pl.stopFlag=True
            except:
                pass

        def seek(self):
            self.pl.seek()

        def position():
            try:
                return self.pl.getPosition()
            except:
                return 0

    def preload(self, filename, output="@auto",timeout=0.2):
        if not os.path.exists(filename):
            return

        # Has to be in a background thread to actually make sense

        def f():
            #By default only do this opportunistically, not if everything is insanely busy.
            if not preloadlock.acquire(timeout=timeout):
                raise TimeoutError("Could not get lock to preload audio file")
            try:
                if (filename, output) in gst_preloaded:
                    return
                t = time.monotonic()
                torm = {}

                # Clean up any unused preload requests
                for i in gst_preloaded:
                    if t-gst_preloaded[i][1] > 600:
                        torm[i] = 1

                # Out of space, but nothing marked for deletion, now we shorten
                # The window to find something deletable
                if len(gst_preloaded) > MAX_PRELOADED and not torm:
                    for i in gst_preloaded:
                        if t-gst_preloaded[i][1] > 5:
                            torm[i] = 1
                            break

                # Actually remove from list
                for i in torm:
                    try:
                        gst_preloaded[i][0].stop()
                        del gst_preloaded[i]
                    except:
                        logging.exception("Error cleaning up preloaded sound")

                # We still might not have anything to delete. Assume in that case
                # It's nonsense churn spamming up everything, and that we can safely
                # just ignore the preload and load it on demand
                if len(gst_preloaded) < MAX_PRELOADED:
                    try:
                        if not os.path.exists(filename):
                            return
                        p = GSTAudioFilePlayer(filename, output=output)
                        gst_preloaded[(filename, output)] = (
                            p, time.monotonic())
                    except:
                        logging.exception("Error preloading sound")
            finally:
                preloadlock.release()
        workers.do(f)

    def playSound(self, filename, handle="PRIMARY", extraPaths=[], _prevPlayerObject=None, finalGain=None, **kwargs):
        jackmanager.check_exclude()
        #Stop the old thing in this channel
        self.stopSound(handle)

        # Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        fn = soundPath(filename, extraPaths)

        if 'volume' in kwargs:
            # odd way of throwing errors on non-numbers
            v = float(kwargs['volume'])
        else:
            v = 1
        if finalGain is None:
            finalGain = v

        if 'start' in kwargs:
            # odd way of throwing errors on non-numbers
            start = float(kwargs['start'])
        else:
            start = 0

        if 'end' in kwargs:
            # odd way of throwing errors on non-numbers
            end = float(kwargs['end'])
        else:
            end = None

        if "output" in kwargs and kwargs['output']:
            x = kwargs['output']
            output = x
        else:
            output = "@auto"
        # Play the sound with a background process and keep a reference to it
        pl = self.GStreamerContainer(
            fn, volume=v, output=output, _prevPlayerObject=_prevPlayerObject, loop=kwargs.get('loop', 0))
        pl.finalGain = finalGain
        self.runningSounds[handle] = pl

    def isPlaying(self, channel="PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].isPlaying()
        except KeyError:
            return False

    def stopSound(self, handle="PRIMARY"):
        # Delete the sound player reference object and its destructor will stop the sound
        if handle in self.runningSounds:
            # Instead of using a lock lets just catch the error is someone else got there first.
            try:
                self.runningSounds[handle].loopsRemaining = 0
                self.runningSounds[handle].stop()
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

    def setVolume(self, vol, channel="PRIMARY", final=True):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].setVol(vol, final)
        except (KeyError, ReferenceError):
            pass

    def pause(self, channel="PRIMARY"):
        try:
            return self.runningSounds[channel].pause()
        except KeyError:
            pass

    def resume(self, channel="PRIMARY"):
        try:
            return self.runningSounds[channel].pause()
        except KeyError:
            pass

    def fadeTo(self, file, length=1.0, block=False, detach=True, handle="PRIMARY", **kwargs):
        jackmanager.check_exclude()
        try:
            x = self.runningSounds[handle]
            if detach:
                # Detach from that handle name
                del self.runningSounds[handle]
        except KeyError:
            x = None
        if x and not length:
            x.stop()

        k = kwargs.copy()

        if 'volume' in kwargs:
            del k['volume']

        # Allow fading to silence
        if file:
            # PrevplayerObject makes the new sound reference the old, so the old doesn't
            # get GCed and stop
            self.playSound(file, handle=handle, _prevPlayerObject=x,
                           volume=0, finalGain=kwargs.get('volume', 1), **k)

        def f():
            t = time.monotonic()
            try:
                v = x.volume
            except:
                v = 0

            while time.monotonic()-t < length:
                ratio = ((time.monotonic()-t)/length)

                try:
                    targetVol = self.runningSounds[handle].finalGain
                except:
                    pass

                if x:
                    x.setVol(max(0, v * (1-ratio)))

                if file:
                    self.setVolume(min(1, targetVol*ratio),
                                   handle, final=False)
                time.sleep(1/48.0)

            try:
                targetVol = self.runningSounds[handle].finalGain
                self.setVolume(min(1, targetVol), handle)
            except Exception as e:
                print(e)

            if x:
                x.stop()

        if block:
            f()
        else:
            workers.do(f)


l = {'sox': SOXWrapper, 'mpg123': Mpg123Wrapper, "mplayer": MPlayerWrapper,
     "madplay": MadPlayWrapper, 'gstreamer': GStreamerBackend,'mpv':MPVBackend}


backend = SoundWrapper()
if util.which('pulseaudio'):
    pulseaudio = True
else:
    pulseaudio = False


#MPV is alwaus auto chosen if available!!!
#All the others are deprecated!!
for i in ['mpv']+list(config['audio-backends']):
    try:
        if util.which(i) or l[i].testAvailable():
            backend = l[i]()
            break
    except:
        messagebus.postMessage("/system/notifications/errors", "Failed to initialize audio backend " +
                               i+" may be able to use fallback:\n"+traceback.format_exc())


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
if jackmanager.settings.get('jackMode', None) in ("manage", "use",'dummy'):
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
    while(time.monotonic()-t) < 5:
        if len(isStartDone):
            break
        time.sleep(0.1)