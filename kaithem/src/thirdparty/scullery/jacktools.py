# Copyright Daniel Dunn 2019
# This file is part of Scullery.

# Scullery is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.

# Scullery is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Scullery.  If not, see <http://www.gnu.org/licenses/>.
__doc__ = ''


import weakref
import threading
import base64
import functools
import os
import re
import time
import subprocess
import hashlib
import struct
import threading
import atexit
import select
import traceback
import random
import sys

import collections

@functools.cache
def which(program):
    "Check if a program is installed like you would do with UNIX's which command."

    # Because in windows, the actual executable name has .exe while the command name does not.
    if sys.platform == "win32" and not program.endswith(".exe"):
        program += ".exe"

    # Find out if path represents a file that the current user can execute.
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    # If the input was a direct path to an executable, return it
    if fpath:
        if is_exe(program):
            return program

    # Else search the path for the file.
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    # If we got this far in execution, we assume the file is not there and return None
    return None

# Util is not used anywhere else
from . import workers, mnemonics, util
wordlist = mnemonics.wordlist

# This is an acceptable dependamcy, it will be part of libkaithem if such a thing exists
from . import messagebus, iceflow


#These events have to happen in a consistent order, the same order that the actual JACK callbacks happen.
#We can't do them within the jack callback becauuse that could do a deadlock.

jackEventHandlingQueue = []
jackEventHandlingQueueLock = threading.Lock()





import weakref
portInfoByID = weakref.WeakValueDictionary()

class PortInfo():
    def __init__(self, name, isInput, sname, isAudio,aliases=None):
        self.isOutput = self.is_output = not isInput
        self.isInput = self.is_input = isInput
        self.isAudio = self.is_audio = isAudio
        self.name = name
        self.shortname = sname
        self.clientName = name[:-len(":" + sname)]
        portInfoByID[id(self)] = self
        self.aliases=aliases or []

    def toDict(self):
        return({
            'name': self.name,
            'isInput': self.is_input,
            'sname': self.shortname,
            'isAudio': self.isAudio,
            'aliases':self.aliases
        })


class JackClientProxy():
    def __getattr__(self,attr):
        if  self.ended or not self.worker.poll() is None:
            raise RuntimeError("This process is already dead")
        check_exclude()

        def f(*a,timeout=10,**k):
            try:
                #Can't serialize ports
                a = [i.name if isinstance(i,PortInfo) else i for i in a]
                x=self.rpc.call(attr,args=a,kwargs=k,block=0.001,timeout=timeout)
                if isinstance(x,dict):
                    x=PortInfo(**x)

                return x
            except TimeoutError:
                if timeout >8:
                    print(traceback.format_exc())
                    self.worker.kill()
                    workers.do(self.worker.wait)
                raise
            except Exception:
                print(traceback.format_exc())
                raise

        return f 

    def get_all_connections(self,*a,**k):
        check_exclude()

        a = [i.name if isinstance(i,PortInfo) else i for i in a]
        x=self.rpc.call("get_all_connections",args=a,kwargs=k,block=0.001)
        x=[PortInfo(**i) for i in x]
        return x


    def get_ports(self,*a,**k):
        check_exclude()

        if self.ended or not self.worker.poll() is None:
            raise RuntimeError("This process is already dead")
        try:
            a = [i.name if isinstance(i,PortInfo) else i for i in a]
            x=self.rpc.call("get_ports",args=a,kwargs=k,block=0.001)
            x=[PortInfo(**i) for i in x]
            return x

        except TimeoutError:
            print(traceback.format_exc())
            self.worker.kill()
            workers.do(self.worker.wait)
            raise



    def __del__(self):
        self.worker.kill()
        workers.do(self.worker.wait)

    def onPortRegistered(self,name, is_input, shortname, is_audio, registered):
        def f():
            try:
                global realConnections
                "Same function for register and unregister"
                # if not port:
                #     return

                p = PortInfo(name, is_input, shortname, is_audio)

                if registered:
                    #log.debug("JACK port registered: "+port.name)
                    with portsListLock:
                        portsList[name] = p
                    messagebus.postMessage("/system/jack/newport", p)
                else:
                    torm = []
                    with portsListLock:
                        for i in _realConnections:
                            if i[0] == name or i[1] == name:
                                torm.append(i)
                        for i in torm:
                            del _realConnections[i]

                        try:
                               del portsList[name]
                        except Exception:
                            pass
                        realConnections = _realConnections.copy()

                    messagebus.postMessage("/system/jack/delport", p)
            except Exception:
                print(traceback.format_exc())

        jackEventHandlingQueue.append(f)
        workers.do(handleJackEvent)

    
    def onPortConnected(self, a_is_output, a_name, b_name, connected):
        # Whem things are manually disconnected we don't
        # Want to always reconnect every time
        if self.ended:
            return
        def f():
            global realConnections

            if connected:
                with portsListLock:
                    if a_is_output:
                        _realConnections[a_name, b_name] = True
                    else:
                        _realConnections[b_name, a_name] = True

                    realConnections = _realConnections.copy()

            if not connected:
                i = (a_name, b_name)
                with portsListLock:
                    if (a_name, b_name) in _realConnections:
                        try:
                            del _realConnections[a_name, b_name]
                        except KeyError:
                            pass

                    if (b_name, a_name) in _realConnections:
                        try:
                            del _realConnections[b_name, a_name]
                        except KeyError:
                            pass

                    realConnections = _realConnections.copy()

                # Try to stop whatever airwire or set therof
                # from remaking the connection
                if i in activeConnections:
                    try:
                        # Deactivate first, that must keep it from using the api
                        # From within the callback
                        activeConnections[i].active = False
                        del allConnections[i]
                        del activeConnections[i]
                    except Exception:
                        pass

                # def f():
                #     if not connected:
                #         log.debug("JACK port "+ a.name+" disconnected from "+b.name)
                #     else:
                #         log.debug("JACK port "+ a.name+" connected to "+b.name)

                # workers.do(f)
        jackEventHandlingQueue.append(f)
        workers.do(handleJackEvent)


    def close(self):
        if self.ended:
            return
            
        
        self.ended=True
        if not self.worker.poll() is None:
            return
        try:
            x= self.rpc.call("close")
            self.rpc.stopFlag=True
        except Exception:
            self.rpc.stopFlag=True
            self.worker.kill()
            workers.do(self.worker.wait)
            raise

    def __init__(self, *a,**k):
        # -*- coding: utf-8 -*-
        #If del can't find this it would to an infinite loop
        self.worker = None


        from scullery.jsonrpyc import RPC
        from subprocess import PIPE, STDOUT
        from reap import Popen
        self.ended=False
        f = os.path.join(os.path.dirname(os.path.abspath(__file__)),"jack_client_subprocess.py")
        env = {}
        env.update(os.environ)

        # Always use installed version.
        # TODO this will cause using the old one
        # if the new one isn't there, but is needed
        # for nixos et al compatibility
        if which("kaithem._jackmanager_server"):
            self.worker = Popen(["kaithem._jackmanager_server"], stdout=PIPE, stdin=PIPE, stderr=STDOUT, env=env)
        else:
            self.worker = Popen(["python3", f], stdout=PIPE, stdin=PIPE, stderr=STDOUT, env=env)
        self.rpc = RPC(target=self,stdin=self.worker.stdout, stdout=self.worker.stdin,daemon=True)
        self.rpc.call("init")

    def print(self,s):
        print(s)







def handleJackEvent():
    with jackEventHandlingQueueLock:
        if jackEventHandlingQueue:
            f = jackEventHandlingQueue.pop(False)
            f()


dummy = False


def shouldAllowGstJack(*a):
    global _jackclient
    for i in range(0, 10):
        # Repeatedly retry, because this might just be a case
        # Of jack not being ready at boot yet.
        if lock.acquire(timeout=1):
            try:
                if getPortsListCache():
                    return True
            except Exception:
                if i > 8:
                    print(traceback.format_exc())
            finally:
                lock.release()

            time.sleep(1)

    return False


iceflow.GstreamerPipeline.shouldAllowGstJack = shouldAllowGstJack

import logging

log = logging.getLogger("system.jack")

_jackclient = None


lock = threading.RLock()


def onJackFailure():
    pass


def onJackStart():
    pass


prevJackStatus = False


# Default settings
jackPeriods = 3
periodSize = 512
jackDevice = "hw:0,0"

useAdditionalSoundcards = 'yes'

# Make sure the alsa_in manager knows what we select as the primary, so that
# It doesn't get stepped on
currentPrimaryDevice = "hw:0,0"
# These apply to soundcards other than the main system card
usbPeriodSize = -1
usbPeriods = -1

usbLatency = -1
usbQuality = 0

realtimePriority = 70

# Do we want to run PulseAudio and the pulse jack backend?
usePulse = True

sharePulse = None



# Should we auto restart the jack process?
# No by default, gets auto set to True by startJackProcess()
manageJackProcess = False


#No other lock should ever be gotten under this, to ensure anti deadlock ordering.

#This also protects the list of connections.  There is a theoretical race condition currently,
#Siomeone else could disconnect a port right as we connect it, and we currently mark things connected by ourselves
#without waiting for jack to tell us, to avoid double connects if at all possible on the "Don't touch the scary server" principle.

#However, in basically all intended use cases there will never be any external things changing anything around, other than manual users who can quicky fix au
#misconnections.
portsListLock = threading.Lock()
portsList = {}

def settingsReloader():
    pass


# Currently we only support using the default system card as the
# JACK backend. We prefer this because it's easy to get Pulse working right.
usingDefaultCard = True


def isConnected(f, t):
    if not isinstance(f, str):
        f = f.name
    if not isinstance(t, str):
        t = t.name

    if (t, f) in _realConnections:
        return True
    if (f, t) in _realConnections:
        return True


def setupPulse():

    log.debug("Setting pulseaudio integration for JACK")
    try:
        subprocess.call(['pulseaudio', '-k'], timeout=5,
                        stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    except Exception:
        print(traceback.format_exc())

    if not usePulse:
        return

    if not which("pulseaudio"):
        logging.error("Pulseaudio requested but not installed")
        return

    time.sleep(0.1)
    # -n prevents loading the defaults, which would otherwise
    # Cause trouble with pulseaudio
    cmd = ['pulseaudio', "-D", "-n", "--file=" +
           os.path.join(os.path.dirname(__file__), "pulse_jack_rc.txt")]

    if sharePulse == "system-wide":
        cmd.extend(["--system", "--disallow-exit",
                    "--disallow-module-loading"])

    try:
        # This may mean it's already running, but hanging in some way
        try:
            subprocess.check_call(cmd, timeout=5)
        except Exception:
            subprocess.call(['killall', '-9', 'pulseaudio'], timeout=5,
                            stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.check_call(cmd, timeout=5)
            pass
        time.sleep(0.1)
        try:
            if sharePulse == "localhost":
                subprocess.check_call(
                    "pactl load-module module-native-protocol-tcp auth-ip-acl=127.0.0.1", timeout=5, shell=True)
            elif sharePulse == "network":
                subprocess.check_call(
                    "pactl load-module module-native-protocol-tcp auth-ip-acl=127.0.0.1;192.168.0.0/24;10.0.0.0/24 auth-anonymous=1", timeout=5, shell=True)
                subprocess.check_call(
                    "pactl load-module module-zeroconf-publish", timeout=5, shell=True)
        except Exception:
            log.exception("Error configuring pulseaudio sharing")

    except Exception:
        log.exception("Error configuring pulseaudio")



ensureConnectionsQueued = [0]


def _ensureConnections(*a, **k):
    "Auto restore connections in the connection list"

    #Someone else is already gonna run this
    #It is ok to have excess runs, but there must always be atleast 1 run after every change
    if ensureConnectionsQueued[0]:
        return
    ensureConnectionsQueued[0]=1

    try:
        with lock:
            #Avoid race conditions, set flag BEFORE we check.
            #So we can't miss anything.  The other way would cause them to think we would check,
            #so they exit, but actually we already did.
            ensureConnectionsQueued[0]=0
            x = list(allConnections.keys())
        for i in x:
            try:
                allConnections[i].reconnect()
            except KeyError:
                pass
            except Exception:
                print(traceback.format_exc())
    except Exception:
        ensureConnectionsQueued[0]=0
        log.exception("Probably just a weakref that went away.")

def _checkNewAvailableConnection(*a, **k):
    "Auto restore connections in the connection list"
    try:
        with lock:
            x = list(allConnections.keys())
        for i in x:
            try:
                allConnections[i].reconnect()
            except Exception:
                print(traceback.format_exc())
    except Exception:
        log.exception("Probably just a weakref that went away.")


messagebus.subscribe("/system/jack/newport", _ensureConnections)

import weakref
allConnections = weakref.WeakValueDictionary()

activeConnections = weakref.WeakValueDictionary()

# Things as they actually are
realConnections = {}

_realConnections = {}


def findReal():
    with lock:
        p = _jackclient.get_ports(is_output=True)
        pl = {}
        for i in p:
            try:
                for j in _jackclient.get_all_connections(i):
                    pl[i.name, j.name] = True
            except Exception:
                log.exception("Err")
        global realConnections,_realConnections
        with portsListLock:
            _realConnections=pl
            realConnections = _realConnections.copy()



errlog = []


latestAirWireForGivenPair =  weakref.WeakValueDictionary()

class MonoAirwire():
    """Represents a connection that should always exist as long as there
    is a reference to this object. You can also enable and disable it with 
    the connect() and disconnect() functions.

    They start out in the connected state
    """

    def __init__(self, orig, to):
        self.orig = orig
        self.to = to
        self.active = True

        if isinstance(orig, PortInfo):
            orig = orig.name
        if isinstance(to, PortInfo):
            to = to.name
        self.tupleid = (orig,to)
        latestAirWireForGivenPair[self.tupleid] = self

    def disconnect(self,force=True):
        global realConnections
        self.disconnected = True
        try:
            del allConnections[self.orig, self.to]
        except Exception:
            pass

        if not force:
            # As garbage collection happens at uppredicatble times, 
            # Don't disconnect if this airwire has been taken over by a new connection between the ports
            x = None
            try:
                x = latestAirWireForGivenPair[self.tupleid]
            except KeyError:
                pass

            if x and not x is self:
                return

        try:
            if lock.acquire(timeout=10):
                try:
                    if isConnected(self.orig, self.to):
                        disconnect(self.orig, self.to)
                        del activeConnections[self.orig, self.to]
                    try:
                        with portsListLock:
                            del _realConnections[self.orig, self.to]
                            realConnections = _realConnections.copy()
                    except KeyError:
                        pass
                    try:
                        with portsListLock:
                            del _realConnections[self.to, self.orig]
                            realConnections = _realConnections.copy()
                    except KeyError:
                        pass
                finally:
                    lock.release()
            else:
                raise RuntimeError("getting lock")

        except Exception:
            pass

    def __del__(self):
        # TODO: Is there any possible deadlock risk at all here?
        if self.active:
            self.disconnect(False)

    def connect(self):
        allConnections[self.orig, self.to] = self
        activeConnections[self.orig, self.to] = self

        self.connected = True
        self.reconnect()

    def reconnect(self):
        if (self.orig, self.to) in activeConnections:
            if self.orig and self.to:
                try:
                    if not isConnected(self.orig, self.to):
                        if lock.acquire(timeout=10):
                            try:
                                connect(self.orig, self.to)
                                with portsListLock:
                                    _realConnections[self.orig, self.to] = True
                                    global realConnections
                                    realConnections = _realConnections.copy()
                            finally:
                                lock.release()
                        else:
                            raise RuntimeError("Could not get lock")
                except Exception:
                    print(traceback.format_exc())


class MultichannelAirwire(MonoAirwire):
    "Link all outputs of f to all inputs of t, in sorted order"

    def _getEndpoints(self):
        f = self.orig
        if not f:
            return None, None

        t = self.to
        if not t:
            return None, None
        return f, t

    def reconnect(self):
        """Connects the outputs of channel strip(Or other JACK thing)  f to the inputs of t, one to one, until
        you run out of ports. 

        Note that channel strips only have the main inputs but can have sends,
        so we have to distinguish them in the regex.
        """
        if not self.active:
            return
        f, t = self._getEndpoints()
        if not f:
            return

        if portsListLock.acquire(timeout=10):
            try:
                outPorts = sorted([portsList[i] for i in portsList if i.startswith(
                    f) and portsList[i].is_audio and portsList[i].is_output], key=lambda x: x.name)
                inPorts = sorted([portsList[i] for i in portsList if i.startswith(
                    t) and portsList[i].is_audio and (not portsList[i].is_output)], key=lambda x: x.name)
            finally:
                portsListLock.release()
        else:
            raise RuntimeError("Getting lock")

        #outPorts = _jackclient.get_ports(f+":*",is_output=True,is_audio=True)
        #inPorts = _jackclient.get_ports(t+":*",is_input=True,is_audio=True)
        # Connect all the ports
        for i in zip(outPorts, inPorts):
            if not isConnected(i[0].name, i[1].name):
                if lock.acquire(timeout=10):
                    try:
                        connect(i[0], i[1])
                        with portsListLock:
                            _realConnections[i[0].name, i[1].name] = True
                            realConnections = _realConnections.copy()
                    finally:
                        lock.release()
                else:
                    raise RuntimeError("Getting lock")

    def disconnect(self,force=True):
        check_exclude()

        if hasattr(self,"noNeedToDisconnect"):
            return
        if not _jackclient:
            return
        f, t = self._getEndpoints()
        if not f:
            return

        if not force:
            # As garbage collection happens at uppredicatble times, 
            # Don't disconnect if this airwire has been taken over by a new connection between the ports
            x = None
            try:
                x = latestAirWireForGivenPair[self.tupleid]
            except KeyError:
                pass

            if x and not x is self:
                return

        if portsListLock.acquire(timeout=10):
            try:
                outPorts = sorted([portsList[i] for i in portsList if i.startswith(
                    f) and portsList[i].is_audio and portsList[i].is_output], key=lambda x: x.name)
                inPorts = sorted([portsList[i] for i in portsList if i.startswith(
                    t) and portsList[i].is_audio and (not portsList[i].is_output)], key=lambda x: x.name)
            finally:
                portsListLock.release()

        if lock.acquire(timeout=10):
            try:
                # Connect all the ports
                for i in zip(outPorts, inPorts):
                    if isConnected(i[0], i[1]):
                        disconnect(i[0], i[1])
                        try:
                            del activeConnections[i[0].name, i[1].name]
                        except KeyError:
                            pass
            finally:
                lock.release()
        else:
            raise RuntimeError("getting lock")

    def __del__(self):
        workers.do(self.disconnect)


class CombiningAirwire(MultichannelAirwire):
    def reconnect(self):
        """Connects the outputs of channel strip f to the port t. As in all outputs
        to one input. If the destination is a client, connect all channnels of src to all of dest.
        """
        if not self.active:
            return
        f, t = self._getEndpoints()
        if not f:
            return
        if lock.acquire(timeout=10):
            try:
               
                if t.endswith("*"):
                    t=t[:-1]
                
                if f.endswith("*"):
                    f=f[:-1]
                

                outPorts=[]
                inPorts=[]
                with portsListLock:
                    for i in portsList:
                        if i.startswith(f + ":"):
                            if portsList[i].is_output and portsList[i].is_audio:
                                outPorts.append(i)
                        if i.startswith(t):
                            if portsList[i].is_input and  portsList[i].is_audio:
                                inPorts.append(i)

                # Connect all the ports
                for i in outPorts:
                    for j in inPorts:
                        if not isConnected(i, j):
                            connect(i, j)

            finally:
                lock.release()

    def disconnect(self,force=False):
        f, t = self._getEndpoints()
        if not f:
            return

        if not force:
            # As garbage collection happens at uppredicatble times, 
            # Don't disconnect if this airwire has been taken over by a new connection between the ports
            x = None
            try:
                x = latestAirWireForGivenPair[self.tupleid]
            except KeyError:
                pass

            if x and not x is self:
                return

        if lock.acquire(timeout=10):
            try:
     
                if t.endswith("*"):
                    t=t[:-1]
                
                if f.endswith("*"):
                    f=f[:-1]

                outPorts=[]
                inPorts=[]
                with portsListLock:
                    for i in portsList:
                        if i.startswith(f + ":"):
                            if portsList[i].is_output and portsList[i].is_audio:
                                outPorts.append(i)
                        if i.startswith(t):
                            if portsList[i].is_input and  portsList[i].is_audio:
                                inPorts.append(i)

                if not inPorts:
                    return          
                # Disconnect all the ports
                for i in outPorts:
                    for j in inPorts:
                        if isConnected(i, j):
                            try:
                                disconnect(i, j)
                            except Exception:
                                print(traceback.format_exc())
                            try:
                                del activeConnections[i, j]
                            except KeyError:
                                pass
            finally:
                lock.release()


def Airwire(f, t, forceCombining=False):

    # Can't connect to nothing, for now lets use a hack and make these nonsense
    # names so emoty strings don't connect to stuff
    if not f or not t:
        f = "jdgdsjfgkldsf"
        t = "dsfjgjdsfjgkl"
    if forceCombining:
        return CombiningAirwire(f, t)
    elif f == None or t == None:
        return MonoAirwire(None, None)
    elif ":" in f:
        if not ":" in t:
            return CombiningAirwire(f, t)
        return MonoAirwire(f, t)
    else:
        return MultichannelAirwire(f, t)




############################################################################
# This section manages the actual sound IO and creates jack ports


# This code runs once when the event loads. It also runs when you save the event during the test compile
# and may run multiple times when kaithem boots due to dependancy resolution
__doc__ = ''

oldi, oldo, oldmidis = None, None, None


alsa_in_instances = {}
alsa_out_instances = {}

failcards = {}


toretry_in = {}
toretry_out = {}


def compressnumbers(s):
    """Take a string that's got a lot of numbers and try to make something 
        that represents that number. Tries to make
        unique strings from things like usb-0000:00:14.0-2

    """
    n = ''
    currentnum = ''
    for i in s:
        if i in '0123456789':
            # Exclude leading zeros
            if currentnum or (not(i == '0')):
                currentnum += i
        else:
            n += currentnum
            currentnum = ''

    return n + currentnum


def tryCloseFds(p):
    if not p:
        return
    try:
        p.stdout.close()
    except Exception:
        pass
    try:
        p.stderr.close()
    except Exception:
        pass
    try:
        p.stdin.close()
    except Exception:
        pass


def try_stop(p):
    try:
        p.terminate()
    except Exception:
        pass
    tryCloseFds(p)


def closeAlsaProcess(x):
    # Why not a proper terminate?
    # It seemed to ignore that sometimes.
    x.kill()
    x.wait()
    tryCloseFds(x)


def cleanupstring(s):
    "Get rid of special characters and common redundant words that provide no info"
    x = s.replace(":0", "0")
    x = s.replace(":0", ":")
    x = s.replace(":0", ":")

    x = s.replace(" ", "").replace("\n", "").replace("*", "").replace("(", "")
    x = x.replace(")", "").replace(
        "-", "").replace(":", ".").replace("Audio", "")
    x = x.replace("Lpe", "").replace(
        "-", "").replace("Generic", "").replace("Device", '')
    return x


def enumeratePCI():
    "generate the PCI numbering that cardsfromregex needs"
    # We are going to list out all the PCI bus devices and give them numbers
    # So we can use fewer bits for that. Here we assign them all numbers hopefully
    # From 0 to 128. Scatter around by hash to at least try to stay consistent if
    # They change.
    pciNumbers = {}
    usedNumbers = {}
    if os.path.exists("/sys/bus/pci/devices"):
        for i in sorted(os.listdir("/sys/bus/pci/devices")):
            n = struct.unpack("<Q", hashlib.sha1(
                i.encode('utf8')).digest()[:8])[0] % 128
            while n in usedNumbers:
                n += 1
            usedNumbers[n] = i
            pciNumbers[n] = i
    return pciNumbers


def assignName(locator, longname, usedFirstWords, pciNumbers):
    """Given the relevant context, return a two-word easy to remember name to the card with the given
        'locator' which is usually something like usb-0000:00:14.0-1
    """
    # Handle USB locators
    if 'usb' in locator:
        x = locator.split("-")
        if len(x) > 2:
            controller = x[1]
            usbpath = x[2]

            if not controller in pciNumbers:
                # Not a PCI controller. We don't know how to enumerate these in a compact
                # Way, so we have to just trust that there is only one or two of them
                pval = 1
                accum = 0
                # Use base 8 to convert the usb path into a number. Assume that it's little endian.
                # We of course may have numbers that overflow and such, but we will deal with collisions
                # From that.
                digitNumber = 0
                for j in reversed(controller):
                    if j.lower() in '0123456789abcdef':
                        accum += int(j, 16) * pval
                        # Optimize for PCI bus stuff.  The last digit(Reversed to the first)
                        # Can only be 0 to 7. We use a nonlinear base system where the firt hex
                        # digit is multiplied by 8, and the second by 8*16, even though it can be up to 15.
                        # This is very confusing.
                        if digitNumber:
                            pval *= 16
                        else:
                            pval *= 8
                        digitNumber += 1

                # We just have to trust that we aren't likely to have two of these weird USB
                # things with locators separated by more than 128, and if we do the chance
                # of collision is low anyway.  This whole block is mostly for embedded ARM stuff
                # with one controller
                n = usbpath[0]
                if n in '0123456789':
                    accum = int(n) * 128
            else:
                # We know the PCI number we generated for this. Take the first digit
                # Of the path and add it in, so that the first word varies with root port.
                # This seems kinda nice, to group things by root port.
                n = usbpath[0]
                if n in '0123456789':
                    accum = int(n) * 128 + pciNumbers[controller]
                else:
                    accum = pciNumbers[controller]

            # Choose an unused first word based on what the controller is.
            first = wordlist[accum % 1621]
            s = 0
            # Now we are going to fix collisons.
            while first in usedFirstWords and s < 100:
                s += 1
                if usedFirstWords[first] == controller:
                    break
                first = memorableHash(controller + str(s))
            usedFirstWords[first] = controller

            pval = 1
            accum = 0
            # Use base 8 to convert the usb path into a number. Assume that it's little endian.
            # We of course may have numbers that overflow and such, but we will deal with collisions
            # From that.
            for j in usbpath:
                if j in '0123456789':
                    accum += int(j) * pval
                    pval *= 8
            # 1621 is a prime number. We use this for modulo
            # to prevent discarding higher order bits.
            second = wordlist[accum % 1621]
        else:
            first = memorableHash(x[2])
            second = memorableHash(x[1])
    # handle nonusb
    else:
        controller = locator
        first = memorableHash(controller)

        while first in usedFirstWords and s < 100:
            s += 1
            if usedFirstWords[first] == controller:
                break
            first = memorableHash(controller + str(s))
        second = memorableHash(longname)

    # Note that we could still have collisions. We are going to fix that
    # In the second step
    h = first + second
    return h


def generateJackName(words, longname, numberstring, taken, taken2):
    "Generate a name suitable for direct use as a jack client name"
    n = cleanupstring(longname)
    n = n.lower()

    # You can probably see why using the first four letters of this would be
    # Unprofessional and not informative.
    if n.startswith("analog"):
        n = "anlg"

    jackname = n[:4] + '_' + words
    jackname += numberstring
    jackname = jackname[:28]
    # If there's a collision, we're going to redo everything
    # This of course will mean we're going back to
    while (jackname in taken) or jackname in taken2:

        # This was some kind of cool algorithm or something.
        # At some point, fix it, but it clearly doesn't work, so lets use
        # The simple version.
        # h = memorableHash(jackname + cards[i[0]] + ":" + i[2])[:12]
        # n = cleanupstring(longname)
        # jackname = n[:4] + '_' + words
        # jackname += numberstring
        # jackname = jackname[:28]

        jackname = jackname[:-2]
        jackname += str(int(random.random() + 99))
    return jackname


def cardsfromregex(m, cards, usednames=[], pciNumbers={}, usedFirstWords={}):
    """Given the regex matches from arecord or aplay, match them up to the actual 
    devices and give them memorable aliases"""

    d = {}
    # Why sort? We need consistent ordering so that our conflict resolution
    # has the absolute most possible consistency

    def key(a):
        "Sort USBs last, so that PCI stuff gets the first pick"
        return(1 if ('usb' in a[2].lower()) else 0, a)

    m = sorted(m)
    for i in m:
        # Filter out HDMI
        if 'HDMI' in i[3]:
            continue
        # We generate a name that contains both the device path and subdevice
        generatedName = cards[i[0]] + "." + i[2]

        longname = i[3]
        locator = cards[i[0]]
        numberstring = compressnumbers(locator)

        h = assignName(locator, longname, usedFirstWords, pciNumbers)

        jackname = generateJackName(h, longname, numberstring, d, usednames)

        longname = h + "_" + \
            memorableHash(cards[i[0]] + ":" + i[2], num=4,
                          caps=True) + "_" + cards[i[0]]

        try:
            d[jackname] = ("hw:" + i[0] + "," + i[2], cards[i[0]],
                           (int(i[0]), int(i[2])), longname)
        except KeyError:
            d[jackname] = ("hw:" + i[0] + "," + i[2], cards[i[0]],
                           (int(i[0]), int(i[2])), longname)
    return d


def midiClientsToCardNumbers():
    # Groups are clientnum, name, cardnumber, only if the client actually has a card number
    pattern = r"client\s+(\d+):.+?'(.+?)'.+?card=(\d+)."
    x = subprocess.check_output(
        ['aconnect', '-i'], stderr=subprocess.DEVNULL).decode("utf8")
    x = re.findall(pattern, x)

    clients = {}
    for i in x:
        clients[int(i[0])] = (i[1], int(i[2]))

    x = subprocess.check_output(
        ['aconnect', '-o'], stderr=subprocess.DEVNULL).decode("utf8")
    x = re.findall(pattern, x)

    clients = {}
    for i in x:
        clients[int(i[0])] = (i[1], int(i[2]))
    return clients


midip = None




def readAllSoFar(proc, retVal=b''):
    counter = 1024
    while counter:
        x = (select.select([proc.stdout], [], [], 0.1)[0])
        if x:
            retVal += proc.stdout.read(1)
        else:
            break
        counter -= 1
    return retVal


def readAllErrSoFar(proc, retVal=b''):
    counter = 1024
    while counter:
        x = (select.select([proc.stderr], [], [], 0.1)[0])
        if x:
            retVal += proc.stderr.read(1)
        else:
            break
        counter -= 1
    return retVal


def getPersistentCardNames():
    "Get a simple dict mapping persistent name to ALSA name, for all cards"
    i, o, x = listSoundCardsByPersistentName()

    d = {}

    for c in i:
        d[c] = i[c][0]
    for c in o:
        d[c] = o[c][0]

    return d


lastOutput = None
cacheCards = None


def listSoundCardsByPersistentName():
    """
        Only works on linux or maybe mac

       List devices in a dict indexed by human-readable and persistant easy to memorize
       Identifiers. Output is tuples:
       (cardnamewithsubdev(Typical ASLA identifier),physicalDevice(persistent),devicenumber, subdevice)

    """

    global lastOutput, cacheCards
    with open("/proc/asound/cards") as f:
        d = f.read()

    # RE pattern produces cardnumber, cardname, locator
    c = re.findall(
        r"[\n\r]*\s*(\d)+\s*\[(\w+)\s*\]:\s*.*?[\n\r]+\s*.*? at (.*?)[\n\r]+", d)

    # Catch the ones that don't have an "at"
    c2 = re.findall(
        r"[\n\r]*\s*(\d)+\s*\[(\w+)\s*\]:\s*.*?[\n\r]+\s*(.*?)[\n\r]+", d)

    cards = {}
    # find physical cards
    for i in c:
        n = i[2].strip().replace(" ", "").replace(
            ",fullspeed", "").replace("[", "").replace("]", "")
        cards[i[0]] = n

    # find physical cards
    for i in c2:
        # Ones with at are caught in c
        if ' at ' in i[2]:
            continue
        n = i[2].strip().replace(" ", "").replace(
            ",fullspeed", "").replace("[", "").replace("]", "")
        cards[i[0]] = n

    if cacheCards == cards:
        if not lastOutput is None:
            return lastOutput

    cacheCards = cards

    pci = enumeratePCI()
    usedFirstWords = {}

    x = subprocess.check_output(
        ['aplay', '-l'], stderr=subprocess.DEVNULL).decode("utf8")
    # Groups are cardnumber, cardname, subdevice, longname
    sd = re.findall(
        r"card (\d+): (\w*)\s\[.*?\], device (\d*): (.*?)\s+\[.*?]", x)
    outputs = cardsfromregex(sd, cards, pciNumbers=pci,
                             usedFirstWords=usedFirstWords)

    x = subprocess.check_output(
        ['arecord', '-l'], stderr=subprocess.DEVNULL).decode("utf8")
    # Groups are cardnumber, cardname, subdevice, longname
    sd = re.findall(
        r"card (\d+): (\w*)\s\[.*?\], device (\d*): (.*?)\s+\[.*?]", x)
    inputs = cardsfromregex(sd, cards, pciNumbers=pci,
                            usedFirstWords=usedFirstWords)

    midis = []

    x= inputs, outputs, midis
    lastOutput = x
    return x


def memorableHash(x, num=1, separator="", caps=False):
    "Use the diceware list to encode a hash. Not meant to be secure."
    o = ""

    if isinstance(x, str):
        x = x.encode("utf8")
    for i in range(num):
        while 1:
            x = hashlib.sha256(x).digest()
            n = struct.unpack("<Q", x[:8])[0] % len(wordlist)
            e = wordlist[n]
            if caps:
                e = e.capitalize()
            # Don't have a word that starts with the letter the last one ends with
            # So it's easier to read
            if o:
                if e[0] == o[-1]:
                    continue
                o += separator + e
            else:
                o = e
            break
    return o


def shortHash(x, num=8, separator=""):
    "Use the diceware list to encode a hash. Not meant to be secure."
    o = ""

    if isinstance(x, str):
        x = x.encode("utf8")
    x = hashlib.sha256(x).digest()
    b = base64.b64encode(x).decode("utf8").replace("+", "").replace("/", "")
    return b[:num]



jackShouldBeRunning = False


def stopJackServer():
    with lock:
        global jackShouldBeRunning
        jackShouldBeRunning = False

        _stopJackProcess()


jackp = None
lastJackStartAttempt = 0


def _stopJackProcess():
    global _jackclient, jackp
    import subprocess
    from . import fluidsynth
    log.info("Stopping JACK and all related processes")
    # Get rid of old stuff
    iceflow.stopAllJackUsers()
    fluidsynth.stopAll()

    try:
        subprocess.call(['killall', 'alsa_in'],
                        stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    except Exception:
        print(traceback.format_exc())
    try:
        subprocess.call(['killall', 'alsa_out'],
                        stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    except Exception:
        print(traceback.format_exc())
    try:
        subprocess.call(['killall', 'a2jmidid'],
                        stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    except Exception:
        print(traceback.format_exc())

    try:
        subprocess.call(['killall', 'jackd'],
                        stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    except Exception:
        logging.exception("Failed to stop, retrying with -9")

    time.sleep(1)

    try:
        subprocess.call(['killall', '-9', 'jackd'],
                        stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    except Exception:
        print(traceback.format_exc())
    try:
        # Close any existing stuff
        if _jackclient:
            _jackclient.close()
            _jackclient = None
    except Exception:
        print(traceback.format_exc())
        log.exception("Probably just already closed")
    tryCloseFds(jackp)
    jackp = None


def _startJackProcess(p=None, n=None, logErrs=True):
    # Start the JACK server, and related processes
    global jackp
    global periodSize
    global jackPeriods
    global jackDevice
    global currentPrimaryDevice

    period = p or periodSize
    jackPeriods = n or jackPeriods

    log.info("Attempting to start JACK")
    if not jackp or not jackp.poll() == None:
        tryCloseFds(jackp)
        jackp = None
        if midip:
            try:
                midip.kill()
            except Exception:
                print(traceback.format_exc())

        try:
            subprocess.call(
                ['pulseaudio', '-k'], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        except Exception:
            print(traceback.format_exc())

        # Let's be real sure it's gone
        try:
            subprocess.call(['killall', '-9', 'pulseaudio'],
                            stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        except Exception:
            print(traceback.format_exc())

        # TODO: Explicitly close all the FDs we open!
        f = open(os.devnull, "w")
        my_env = os.environ.copy()

        if not 'DBUS_SESSION_BUS_ADDRESS' in my_env or not my_env['DBUS_SESSION_BUS_ADDRESS']:
            my_env['DBUS_SESSION_BUS_ADDRESS'] = "unix:path=/run/dbus/system_bus_socket"
            os.environ['DBUS_SESSION_BUS_ADDRESS'] = "1"

        os.environ['JACK_NO_AUDIO_RESERVATION'] = "1"
        my_env['JACK_NO_AUDIO_RESERVATION'] = "1"

        settingsReloader()

        lastJackStartAttempt = time.monotonic()

        useDevice = "hw:0,0"

        # If the user supplied a perisistent name, translate it.
        if jackDevice:
            useDevice = jackDevice
            incards, outcards, x = listSoundCardsByPersistentName()
            if jackDevice in incards:
                useDevice = incards[jackDevice][0]

            if jackDevice in outcards:
                useDevice = outcards[jackDevice][0]

        currentPrimaryDevice = useDevice
        # Not supplying an explicit d -o2 breaks sound on raspberry pi for some horrendous reason.
        # This also means we don't support surround sound unfortunately.
        # Not only that, -o2 must appear at the end.
        cmdline = ['jackd']

        if realtimePriority:
            cmdline.extend(['--realtime', '-P', str(realtimePriority)])
        if dummy:
            d = ['-d', 'dummy']
        else:
            d = ['-d', 'alsa', '-d', useDevice]
        cmdline.extend(d)

        if not dummy:
            cmdline.extend(['-p', str(period), '-s', '-n',
                            str(jackPeriods), '-r', '48000', '-o2'])
        else:
            cmdline.extend(['-p', str(period)])

        logging.info(
            "Attempting to start JACKD server with: \n" + ' '.join(cmdline))

        jackp = subprocess.Popen(cmdline, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=my_env)

        time.sleep(0.5)

        if jackp.poll() != None:
            x = readAllErrSoFar(jackp)
            if x and logErrs:
                log.error("jackd:\n" + x.decode('utf8', 'ignore'))
            x = readAllSoFar(jackp)
            if x and logErrs:
                log.info("jackd:\n" + x.decode('utf8', 'ignore'))
            tryCloseFds(jackp)
            jackp = None

        if jackp and jackp.poll() != None:
            tryCloseFds(jackp)
            jackp = None
            raise RuntimeError("Could not start JACK process")

        startedClient = False

        # Try to start the JACK client
        for i in range(0, 10):
            try:
                if _checkJackClient(err=False):
                    startedClient = True
                    break
            except Exception:
                time.sleep(1)
        global prevJackStatus

        # Try again, but this time don't just hide the error.
        if not startedClient:
            if not _checkJackClient():
                if prevJackStatus:
                    prevJackStatus = False
                    onJackFailure()
        else:
            if not prevJackStatus:
                prevJackStatus = True
                onJackStart()
            logging.debug("Connected to JACKD server")

        if realtimePriority and jackp:
            try:
                subprocess.check_call(
                    ['chrt', '-f', '-p', str(realtimePriority), str(jackp.pid)])
            except Exception:
                log.exception("Error getting RT")

        try:
            setupPulse()
            log.debug("Set up pulse")
        except Exception:
            log.exception("Error starting pulse, ignoring")

        def f():
            global midip
            # Poll till it's actually started, then post the message
            for i in range(120):
                if getPorts(maxWait=0.5):
                    break
                time.sleep(0.5)
            messagebus.postMessage("/system/jack/started", {})

            # if util.which("a2jmidid"):
            #     midip = subprocess.Popen("a2jmidid -e", stdout=subprocess.DEVNULL,
            #                              stderr=subprocess.DEVNULL, shell=True, stdin=subprocess.DEVNULL)
            # else:
            #     logging.error(
            #         "a2jmidid not installed, MIDI may not work as expected.")

            from . import fluidsynth
            fluidsynth.remakeAll()

        workers.do(f)


def getIOOptionsForAdditionalSoundcard():
    settingsReloader()
    psize = usbPeriodSize
    iooptions = []

    if not psize < 0:
        iooptions += ["-p", str(psize)]

    if not usbLatency < 0:
        iooptions += ["-t", str(usbLatency)]

    if not usbPeriods < 0:
        iooptions += ["-n", str(usbPeriods)]

    iooptions += ["-q", str(usbQuality), "-r", "48000"]

    return iooptions


lastFullScan = 0


def handleManagedSoundcards():
    "Make sure that all of our alsa_in and out instances are working as they should be."
    global oldi
    global oldo
    global oldmidis
    global lastFullScan
    global useAdditionalSoundcards

    # There seems to be a bug in reading errors from the process
    # Right now it's a TODO, but most of the time
    # we catch things in the add/remove detection anyway
    if lock.acquire(timeout=10):
        try:
            try:
                tr = []
                for i in alsa_out_instances:

                    x = readAllSoFar(alsa_out_instances[i])
                    e = readAllErrSoFar(alsa_out_instances[i])
                    problem = b"err =" in x + e or alsa_out_instances[i].poll()
                    problem = problem or b"busy" in (x + e)

                    if problem:
                        log.error("Error in output " + i + (x + e).decode("utf8") +
                                  " status code " + str(alsa_out_instances[i].poll()))
                        closeAlsaProcess(alsa_out_instances[i])
                        tr.append(i)
                        # We have to delete the busy stuff but we can
                        # retry later
                        if b"busy" in (x + e):
                            toretry_out[i] = time.monotonic() + 5
                        elif b"No such" in (x + e):
                            toretry_out[i] = time.monotonic() + 10
                            log.error("Nonexistant card " + i)
                        else:
                            toretry_out[i] = time.monotonic()

                        log.info("Removed " + i + "o")

                    elif not alsa_out_instances[i].poll() == None:
                        tr.append(i)
                        log.info("Removed " + i + "o")

                for i in tr:
                    try_stop(alsa_out_instances[i])
                    del alsa_out_instances[i]

                tr = []
                for i in alsa_in_instances:

                    x = readAllSoFar(alsa_in_instances[i])
                    e = readAllErrSoFar(alsa_in_instances[i])
                    problem = b"err =" in x + e or alsa_in_instances[i].poll()
                    problem = problem or b"busy" in (x + e)
                    if problem:
                        log.error("Error in input " + i + (x + e).decode("utf8") +
                                  " status code " + str(alsa_in_instances[i].poll()))
                        closeAlsaProcess(alsa_in_instances[i])
                        tr.append(i)
                        if b"busy" in (x + e):
                            toretry_in[i] = time.monotonic() + 5

                        if b"No such" in (x + e):
                            toretry_in[i] = time.monotonic() + 10
                            log.error("Nonexistant card " + i)
                        else:
                            toretry_out[i] = time.monotonic()

                        log.info("Removed " + i + "i")

                    elif not alsa_in_instances[i].poll() == None:
                        tr.append(i)
                        log.info("Removed " + i + "i")

                for i in tr:
                    try_stop(alsa_in_instances[i])
                    del alsa_in_instances[i]
            except Exception:
                print(traceback.format_exc())

            # HANDLE CREATING AND GC-ING things
            inp, op, midis = listSoundCardsByPersistentName()

            # Ignore all except MIDI
            if not useAdditionalSoundcards.lower() in ("true", "yes", 'on'):
                inp = {}
                op = {}

            # This is how we avoid constantky retrying to connect the same few
            # clients that fail, which might make a bad periodic click that nobody
            # wants to hear.
            startPulse = False
            if (inp, op, midis) == (oldi, oldo, oldmidis):

                # However some things we need to retry.
                # Device or resource busy being the main one
                for i in inp:
                    if i in toretry_in:
                        if time.monotonic() < toretry_in[i]:
                            continue
                        del toretry_in[i]
                        if not i in alsa_in_instances:
                            # Pulse likes to take over cards so we have to stop it, take the card, then start it. It sucks
                            startPulse = True
                            try:
                                subprocess.call(
                                    ['pulseaudio', '-k'], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                            except Exception:
                                print(traceback.format_exc())
                            time.sleep(2)

                            log.debug(
                                "Starting alsa_in process, for " + inp[i][0])
                            x = subprocess.Popen(["alsa_in"] + getIOOptionsForAdditionalSoundcard() + [
                                                 "-d", inp[i][0], "-j", i + "i"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            try:
                                subprocess.check_call(
                                    ['chrt', '-f', '-p', '70', str(x.pid)])
                            except Exception:
                                log.exception("Error getting RT")

                            alsa_in_instances[i] = x
                            log.info("Added " + i + "i at" + inp[i][1])

                for i in op:
                    if i in toretry_out:
                        if time.monotonic() < toretry_out[i]:
                            continue
                        del toretry_out[i]
                        if not i in alsa_out_instances:
                            startPulse = True
                            try:
                                subprocess.call(
                                    ['pulseaudio', '-k'], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                            except Exception:
                                print(traceback.format_exc())

                            log.debug(
                                "Starting alsa_out process for " + op[i][0])
                            x = subprocess.Popen(["alsa_out"] + getIOOptionsForAdditionalSoundcard() + [
                                                 "-d", op[i][0], "-j", i + "o"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            alsa_out_instances[i] = x

                            try:
                                subprocess.check_call(
                                    ['chrt', '-f', '-p', '70', str(x.pid)])
                            except Exception:
                                log.exception("Error getting RT")
                            log.info("Added " + i + "o")

                # If we stopped it, start it again
                if startPulse:
                    try:
                        setupPulse()
                    except Exception:
                        log.exception("Error restarting pulse, ignoring")
                if lastFullScan > time.monotonic() - 10:
                    return
                lastFullScan = time.monotonic()
            oldi, oldo, oldmidis = inp, op, midis

            # Look for ports with the a2jmidid naming pattern and give them persistant name aliases.
            x = _jackclient.get_ports(is_midi=True)
            for i in midis:
                for j in x:
                    number = "[" + str(midis[i][1]) + "]"
                    if number in j.name:
                        if i[0] in j.name:
                            try:
                                if not i in j.aliases:
                                    j.set_alias(i)
                            except Exception:
                                log.exception("Error setting MIDI alias")

            for i in inp:
                # HDMI doesn't do inputs as far as I know
                if not i.startswith("HDMI"):
                    if not i in alsa_in_instances:
                        if inp[i][0] == currentPrimaryDevice:
                            # We don't do an alsa in for this card because it
                            # Is already the JACK backend

                            # But in dummy mode there is no real jack backend
                            if not dummy:
                                if usingDefaultCard:
                                    continue

                        log.debug("Starting alsa_in process for " + inp[i][0])
                        x = subprocess.Popen(["alsa_in"] + getIOOptionsForAdditionalSoundcard() + [
                                             "-d", inp[i][0], "-j", i + "i"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                        try:
                            subprocess.check_call(
                                ['chrt', '-f', '-p', '70', str(x.pid)])
                        except Exception:
                            log.exception("Error getting RT")
                        alsa_in_instances[i] = x
                        log.info("Added " + i + "i at " + inp[i][1])

            for i in op:
                if not i.startswith("HDMI"):
                    if not i in alsa_out_instances:
                        # We do not want to mess with the
                        if op[i][0] == currentPrimaryDevice:
                            if not dummy:
                                if usingDefaultCard:
                                    continue

                        log.debug("Starting alsa_out process, for " + op[i][0])
                        x = subprocess.Popen(["alsa_out"] + getIOOptionsForAdditionalSoundcard() + [
                                             "-d", op[i][0], "-j", i + 'o'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                        try:
                            subprocess.check_call(
                                ['chrt', '-f', '-p', '70', str(x.pid)])
                        except Exception:
                            log.exception("Error getting RT")
                        alsa_out_instances[i] = x
                        log.info("Added " + i + "o at " + op[i][1])

            # In case alsa_in doesn't properly tell us about a removed soundcard
            # Check for things that no longer exist.
            try:
                tr = []
                for i in alsa_out_instances:
                    if not i in op:
                        tr.append(i)
                for i in tr:
                    log.warning("Removed " + i +
                                "o because the card was removed")
                    try:
                        closeAlsaProcess(alsa_out_instances[i])
                    except Exception:
                        log.exception("Error closing process")
                    del alsa_out_instances[i]

                tr = []
                for i in alsa_in_instances:
                    if not i in inp:
                        tr.append(i)
                for i in tr:
                    log.warning("Removed " + i +
                                "i because the card was removed")
                    try:
                        closeAlsaProcess(alsa_in_instances[i])
                    except Exception:
                        log.exception("Error closing process")
                    del alsa_in_instances[i]
            except Exception:
                log.exception("Exception in loop")
            try:
                tr = []
                for i in alsa_out_instances:

                    x = readAllSoFar(alsa_out_instances[i])
                    e = readAllErrSoFar(alsa_out_instances[i])
                    problem = b"err =" in x + e or alsa_out_instances[i].poll()
                    problem = problem or b"busy" in (x + e)

                    if problem:
                        log.error("Error in output " + i + (x + e).decode("utf8") +
                                  " status code " + str(alsa_out_instances[i].poll()))
                        closeAlsaProcess(alsa_out_instances[i])
                        tr.append(i)
                        # We have to delete the busy stuff but we can
                        # retry later
                        if b"busy" in (x + e):
                            toretry_out[i] = time.monotonic() + 5
                        elif b"No such" in (x + e):
                            toretry_out[i] = time.monotonic() + 10
                            log.error("Nonexistant card " + i)
                        else:
                            toretry_out[i] = time.monotonic()

                        log.info("Removed " + i + "o")

                    elif not alsa_out_instances[i].poll() == None:
                        tr.append(i)
                        log.info("Removed " + i + "o")

                for i in tr:
                    try_stop(alsa_out_instances[i])
                    del alsa_out_instances[i]

                tr = []
                for i in alsa_in_instances:

                    x = readAllSoFar(alsa_in_instances[i])
                    e = readAllErrSoFar(alsa_in_instances[i])
                    problem = b"err =" in x + e or alsa_in_instances[i].poll()
                    problem = problem or b"busy" in (x + e)
                    if problem:
                        log.error("Error in input " + i + (x + e).decode("utf8") +
                                  " status code " + str(alsa_in_instances[i].poll()))
                        closeAlsaProcess(alsa_in_instances[i])
                        tr.append(i)
                        if b"busy" in (x + e):
                            toretry_in[i] = time.monotonic() + 5

                        if b"No such" in (x + e):
                            toretry_in[i] = time.monotonic() + 10
                            log.error("Nonexistant card " + i)
                        else:
                            toretry_out[i] = time.monotonic()

                        log.info("Removed " + i + "i")

                    elif not alsa_in_instances[i].poll() == None:
                        tr.append(i)
                        log.info("Removed " + i + "i")

                for i in tr:
                    try_stop(alsa_in_instances[i])
                    del alsa_in_instances[i]
            except Exception:
                print(traceback.format_exc())

            # HANDLE CREATING AND GC-ING things
            inp, op, midis = listSoundCardsByPersistentName()

            # Ignore all except MIDI
            if not useAdditionalSoundcards.lower() in ("true", "yes", 'on'):
                inp = {}
                op = {}

            # This is how we avoid constantky retrying to connect the same few
            # clients that fail, which might make a bad periodic click that nobody
            # wants to hear.
            startPulse = False
            if (inp, op, midis) == (oldi, oldo, oldmidis):

                # However some things we need to retry.
                # Device or resource busy being the main one
                for i in inp:
                    if i in toretry_in:
                        if time.monotonic() < toretry_in[i]:
                            continue
                        del toretry_in[i]
                        if not i in alsa_in_instances:
                            # Pulse likes to take over cards so we have to stop it, take the card, then start it. It sucks
                            startPulse = True
                            try:
                                subprocess.call(
                                    ['pulseaudio', '-k'], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                            except Exception:
                                print(traceback.format_exc())
                            time.sleep(2)

                            log.debug(
                                "Starting alsa_in process, for " + inp[i][0])
                            x = subprocess.Popen(["alsa_in"] + getIOOptionsForAdditionalSoundcard() + [
                                                 "-d", inp[i][0], "-j", i + "i"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            try:
                                subprocess.check_call(
                                    ['chrt', '-f', '-p', '70', str(x.pid)])
                            except Exception:
                                log.exception("Error getting RT")

                            alsa_in_instances[i] = x
                            log.info("Added " + i + "i at" + inp[i][1])

                for i in op:
                    if i in toretry_out:
                        if time.monotonic() < toretry_out[i]:
                            continue
                        del toretry_out[i]
                        if not i in alsa_out_instances:
                            startPulse = True
                            try:
                                subprocess.call(
                                    ['pulseaudio', '-k'], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                            except Exception:
                                print(traceback.format_exc())

                            log.debug(
                                "Starting alsa_out process for " + op[i][0])
                            x = subprocess.Popen(["alsa_out"] + getIOOptionsForAdditionalSoundcard() + [
                                                 "-d", op[i][0], "-j", i + "o"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            alsa_out_instances[i] = x

                            try:
                                subprocess.check_call(
                                    ['chrt', '-f', '-p', '70', str(x.pid)])
                            except Exception:
                                log.exception("Error getting RT")
                            log.info("Added " + i + "o")

                # If we stopped it, start it again
                if startPulse:
                    try:
                        setupPulse()
                    except Exception:
                        log.exception("Error restarting pulse, ignoring")
                if lastFullScan > time.monotonic() - 10:
                    return
                lastFullScan = time.monotonic()
            oldi, oldo, oldmidis = inp, op, midis

            # Look for ports with the a2jmidid naming pattern and give them persistant name aliases.
            x = _jackclient.get_ports(is_midi=True)
            for i in midis:
                for j in x:
                    number = "[" + str(midis[i][1]) + "]"
                    if number in j.name:
                        if i[0] in j.name:
                            try:
                                if not i in j.aliases:
                                    j.set_alias(i)
                            except Exception:
                                log.exception("Error setting MIDI alias")

            for i in inp:
                # HDMI doesn't do inputs as far as I know
                if not i.startswith("HDMI"):
                    if not i in alsa_in_instances:
                        if inp[i][0] == currentPrimaryDevice:
                            if not dummy:
                                # We don't do an alsa in for this card because it
                                # Is already the JACK backend
                                if usingDefaultCard:
                                    continue

                        log.debug("Starting alsa_in process for " + inp[i][0])
                        x = subprocess.Popen(["alsa_in"] + getIOOptionsForAdditionalSoundcard() + [
                                             "-d", inp[i][0], "-j", i + "i"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                        try:
                            subprocess.check_call(
                                ['chrt', '-f', '-p', '70', str(x.pid)])
                        except Exception:
                            log.exception("Error getting RT")
                        alsa_in_instances[i] = x
                        log.info("Added " + i + "i at " + inp[i][1])

            for i in op:
                if not i.startswith("HDMI"):
                    if not i in alsa_out_instances:
                        # We do not want to mess with the
                        if op[i][0] == currentPrimaryDevice:
                            if not dummy:
                                if usingDefaultCard:
                                    continue

                        log.debug("Starting alsa_out process, for " + op[i][0])
                        x = subprocess.Popen(["alsa_out"] + getIOOptionsForAdditionalSoundcard() + [
                                             "-d", op[i][0], "-j", i + 'o'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                        try:
                            subprocess.check_call(
                                ['chrt', '-f', '-p', '70', str(x.pid)])
                        except Exception:
                            log.exception("Error getting RT")
                        alsa_out_instances[i] = x
                        log.info("Added " + i + "o at " + op[i][1])

            # In case alsa_in doesn't properly tell us about a removed soundcard
            # Check for things that no longer exist.
            try:
                tr = []
                for i in alsa_out_instances:
                    if not i in op:
                        tr.append(i)
                for i in tr:
                    log.warning("Removed " + i +
                                "o because the card was removed")
                    try:
                        closeAlsaProcess(alsa_out_instances[i])
                    except Exception:
                        log.exception("Error closing process")
                    del alsa_out_instances[i]

                tr = []
                for i in alsa_in_instances:
                    if not i in inp:
                        tr.append(i)
                for i in tr:
                    log.warning("Removed " + i +
                                "i because the card was removed")
                    try:
                        closeAlsaProcess(alsa_in_instances[i])
                    except Exception:
                        log.exception("Error closing process")
                    del alsa_in_instances[i]
            except Exception:
                log.exception("Exception in loop")
        finally:
            lock.release()


def work():
    global _reconnecterThreadObjectStopper

    # Wait 10s before actually doing anything to avoid nuisiance chattering errors.
    # This thread mostly only fixes crashed stuff.
    for i in range(100):
        if not _reconnecterThreadObjectStopper[0]:
            return
        time.sleep(0.1)

    failcounter = 0
    while(_reconnecterThreadObjectStopper[0]):
        try:
            # The _checkJack stuf won't block, because we already have the lock
            if lock.acquire(timeout=2):
                failcounter=0
                try:
                    if manageJackProcess:
                        _checkJack()
                    _checkJackClient()
                    if useAdditionalSoundcards:
                        handleManagedSoundcards()
                finally:
                    lock.release()
                # _ensureConnections()
            else:
                if(_reconnecterThreadObjectStopper[0]):
                    # Might be worth logging
                    failcounter +=1
                    if failcounter>4:
                        failcounter=0
                        try_unstuck()
                    raise RuntimeError("Could not get lock,retrying in 5s")

                else:
                    # Already stopping anyway, ignore
                    pass
            time.sleep(5)
        except Exception:
            logging.exception("Error in jack manager")


_reconnecterThreadObject = None
_reconnecterThreadObjectStopper = [0]




def startJackProcess(p=None, n=None):
    with lock:
        global jackShouldBeRunning
        jackShouldBeRunning = True

        for i in range(10):
            try:
                _stopJackProcess()
                # Only log on the last attempt
                _startJackProcess(p, n, logErrs=i == 9)
                break
            except Exception:
                log.exception("Failed to start JACK?")
                time.sleep(0.5)
                if i == 9:
                    raise


def startManaging(p=None, n=None):
    "Start mananaging JACK in whatever way was configured."
    import jack
    import re
    global _jackclient
    global _reconnecterThreadObject

    with lock:
        # Stop the old thread if needed
        _reconnecterThreadObjectStopper[0] = 0
        try:
            if _reconnecterThreadObject:
                _reconnecterThreadObject.join()
        except Exception:
            pass

        if manageJackProcess:
            try:
                startJackProcess()
            except Exception:
                log.exception("Could not start JACK, retrying later")

        _reconnecterThreadObjectStopper[0] = 1
        _reconnecterThreadObject = threading.Thread(target=work)
        _reconnecterThreadObject.name = "JackReconnector"
        _reconnecterThreadObject.daemon = True
        _reconnecterThreadObject.start()


def stopManaging():
    with lock:
        # Stop the old thread if needed
        _reconnecterThreadObjectStopper[0] = 0
        try:
            if _reconnecterThreadObject:
                _reconnecterThreadObject.join()
        except Exception:
            pass
        _reconnecterThreadObject = None

        if manageJackProcess:
            stopJackServer()


jack_output = b''


def _checkJack():
    global jackp, jack_output
    if lock.acquire(timeout=10):
        try:
            if manageJackProcess:
                if jackp:
                    try:
                        jack_output += readAllSoFar(jackp)
                        jack_output += readAllErrSoFar(jackp)
                    except Exception:
                        print(traceback.format_exc())
                        print(jack_output)

                        try:
                            print("Killing jack process, read fail")
                            jackp.kill()
                        except Exception:
                            pass
                        jackp = None

                    if b"\n" in jack_output or len(jack_output) > 1024:
                        print("jackd:")
                        print(jack_output)
                        jack_output = b''

                if manageJackProcess and (not jackp) or (jackp and jackp.poll() != None):
                    global prevJackStatus
                    if not jackp:
                        if prevJackStatus:
                            prevJackStatus = False
                            onJackFailure()
                    if time.monotonic() - lastJackStartAttempt > 10:
                        log.warning(
                            "JACK appears to have stopped. Attempting restart.")
                        _stopJackProcess()
                        if jackShouldBeRunning:
                            _startJackProcess()
        finally:
            lock.release()

postedCheck = False

firstConnect = False

def _checkJackClient(err=True):
    global _jackclient, realConnections,postedCheck,firstConnect
    import jack
    if lock.acquire(timeout=10):
        try:

            t = _jackclient.get_ports()

            if not t:
                if firstConnect:
                    raise RuntimeError("JACK Server not started or client not connected, will try connect ")
                firstConnect = True

            if not postedCheck:
                postedCheck=True
                messagebus.postMessage("/system/jack/started", "")
            
            return True
        except Exception:
            postedCheck=False
            
            if firstConnect:
                print(traceback.format_exc())
                firstConnect = True

            print("Remaking client")
            try:
                _jackclient.close()
                _jackclient = None
            except Exception:
                pass


            with portsListLock:
                portsList.clear()
                _realConnections = {}


            try:
                _jackclient = JackClientProxy()
            except Exception:
                if err:
                    log.exception("Error creating JACK client")
                return

            _jackclient.get_ports()
            getPorts()
            time.sleep(0.5)
            findReal()
            return True
        finally:
            lock.release()

    if not _jackclient:
        return False


def getPortsListCache():
    "We really should not need to have this refreser, it is only there in case of erro, hence the 1 hour."
    global portsList, portsCacheTime
    if time.monotonic() - portsCacheTime < 3600:
        return portsList
    portsCacheTime = time.monotonic()
    getPorts()
    return portsList


portsCacheTime = 0


lastCheckedClientFromGetPorts = 0

def getPorts(*a, maxWait=10, **k):
    global portsList,_jackclient,lastCheckedClientFromGetPorts

    if lock.acquire(timeout=maxWait):
        try:
            if not _jackclient:
                #MOstly here so we can use this standalone from a unit test
                if(lastCheckedClientFromGetPorts< time.monotonic()-120):
                    lastCheckedClientFromGetPorts=time.monotonic()
                    workers.do(_checkJackClient)
                return []
            ports = []
            x = _jackclient.get_ports(*a, **k)

            with portsListLock:
                #No filters means this must be the full list
                if not a and not k:
                    portsList.clear()
                for port in x:
                    portsList[port.name] = port

            return x
        finally:
            lock.release()


def getPortNamesWithAliases(*a, **k):
    if lock.acquire(timeout=10):
        try:
            if not _jackclient:
                return []
            ports = []
            x = _jackclient.get_ports(*a, **k)
            for i in x:
                for j in i.aliases:
                    if not j in ports:
                        ports.append(j)
                if not i.name in ports:
                    ports.append(i.name)
            return ports
        finally:
            lock.release()
    else:
        logging.error("JACK seems to be blocked up. Killing processes")
        try_unstuck()


def getConnections(name, *a, **k):
    if lock.acquire(timeout=10):
        try:
            if not _jackclient:
                return []
            try:
                return _jackclient.get_all_connections(name)
            except Exception:
                log.exception("Error getting connections")
                return []
        finally:
            lock.release()
    else:
        logging.error("JACK seems to be blocked up. Killing processes")
        try_unstuck()

exclude_until = [0]
def try_unstuck():
    print("******Big Jack Problem! starting everything over*******************")
    # It seems that it is actually possible for connect() calls to hang.  This is used to stio
    subprocess.call(['killall', '-9', 'alsa_in'])
    subprocess.call(['killall', '-9', 'alsa_out'])
    subprocess.call(['killall', '-9', 'jackd'])
    exclude_until[0]=time.monotonic()+10


def check_exclude():
    if time.monotonic()<exclude_until[0]:
        raise RuntimeError("That is not allowed, trying to auto-fix")

def disconnect(f, t):
    global realConnections
    if lock.acquire(timeout=30):
        try:
            if not _jackclient:
                _checkJack()

            if not isConnected(f, t):
                return

            try:
                if isinstance(f, PortInfo):
                    f = f.name
                if isinstance(t, PortInfo):
                    t = t.name


                # This feels race conditionful but i think it is important so that we don't try to double-disconnect.
                # Be defensive with jack, the whole thing seems britttle
                  #Let other side handle figuring out which is which
                for i in range(24):
                    #For unknown reasons it is possible to completely clog up the jack client.
                    # We must make a new one and retry should this ever happen
                    try:
                        _jackclient.disconnect(f,t,timeout=5)
                        break
                    except TimeoutError:
                        if(i%6)==5:
                            try_unstuck()
                            time.sleep(5)
                        _jackclient.worker.kill()
                        _checkJackClient()

                with portsListLock:
                    try:
                        del _realConnections[f, t]
                        realConnections = _realConnections.copy()
                    except KeyError:
                        pass

                    try:
                        del _realConnections[t, f]
                        realConnections = _realConnections.copy()
                    except KeyError:
                        pass

            except Exception:
                print(traceback.format_exc())
        finally:
            lock.release()
    else:
        logging.error("JACK seems to be blocked up. Killing processes")
        try_unstuck()

#This is an easy place to get a bazillion sounds queued up all waiting on the lock. This stops that.
awaiting=[0]
awaitingLock = threading.Lock()

def connect(f, t,ts=None):
    ts = ts or time.monotonic()

    global realConnections,_jackclient
    check_exclude()
    with awaitingLock:
        if awaiting[0]>8:
            time.sleep(1)

        if awaiting[0]>12:
            raise RuntimeError("Too many threads are waiting to make JACK connections")

        awaiting[0]+=1

    try:
        if lock.acquire(timeout=10):
            try:
                if not _jackclient:
                    _checkJack()

                if isConnected(f, t):
                    return

                try:
                    if isinstance(f, PortInfo):
                        f = f.name
                    if isinstance(t, PortInfo):
                        t = t.name
                except Exception:
                    return

                try:
                    #Let other side handle figuring out which is which
                    for i in range(3):
                        #For unknown reasons it is possible to completely clog up the jack client.
                        # We must make a new one and retry should this ever happen
                        try:
                            _jackclient.connect(t, f,timeout=10)
                            break
                        except TimeoutError:
                            if i==2:
                                try_unstuck()
                                time.sleep(5)
                            _jackclient.worker.kill()
                            _checkJackClient()
                    with portsListLock:
                        try:
                            _realConnections[f, t] = True
                            realConnections = _realConnections.copy()
                        except KeyError:
                            pass
                except Exception:
                    print(traceback.format_exc())
            finally:
                lock.release()
        else:
            logging.error("JACK seems to be blocked up. Killing processes")
            try_unstuck()
    finally:
        with awaitingLock:
            awaiting[0]-=1

# startManagingJack()
