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
import functools
import os
import time
import subprocess
import threading
import traceback
import sys
import weakref



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
from . import workers

# This is an acceptable dependamcy, it will be part of libkaithem if such a thing exists
from . import messagebus, iceflow


# These events have to happen in a consistent order, the same order that the actual JACK callbacks happen.
# We can't do them within the jack callback becauuse that could do a deadlock.

jackEventHandlingQueue = []
jackEventHandlingQueueLock = threading.Lock()

portInfoByID = weakref.WeakValueDictionary()


class PortInfo():
    def __init__(self, name, isInput, sname, isAudio, aliases=None):
        self.isOutput = self.is_output = not isInput
        self.isInput = self.is_input = isInput
        self.isAudio = self.is_audio = isAudio
        self.name = name
        self.shortname = sname
        self.clientName = name[:-len(":" + sname)]
        portInfoByID[id(self)] = self
        self.aliases = aliases or []

    def toDict(self):
        return ({
            'name': self.name,
            'isInput': self.is_input,
            'sname': self.shortname,
            'isAudio': self.isAudio,
            'aliases': self.aliases
        })


class JackClientProxy():
    def __getattr__(self, attr):
        if self.ended or not self.worker.poll() is None:
            raise RuntimeError("This process is already dead")
        check_exclude()

        def f(*a, timeout=10, **k):
            try:
                # Can't serialize ports
                a = [i.name if isinstance(i, PortInfo) else i for i in a]
                x = self.rpc.call(attr, args=a, kwargs=k,
                                  block=0.001, timeout=timeout)
                if isinstance(x, dict):
                    x = PortInfo(**x)

                return x
            except TimeoutError:
                if timeout > 8:
                    print(traceback.format_exc())
                    self.worker.terminate()
                    self.worker.kill()
                    workers.do(self.worker.wait)
                raise
            except Exception:
                print(traceback.format_exc())
                raise

        return f

    def get_all_connections(self, *a, **k):
        check_exclude()

        a = [i.name if isinstance(i, PortInfo) else i for i in a]
        x = self.rpc.call("get_all_connections", args=a, kwargs=k, block=0.001)
        x = [PortInfo(**i) for i in x]
        return x

    def get_ports(self, *a, **k):
        check_exclude()

        if self.ended or not self.worker.poll() is None:
            raise RuntimeError("This process is already dead")
        try:
            a = [i.name if isinstance(i, PortInfo) else i for i in a]
            x = self.rpc.call("get_ports", args=a, kwargs=k, block=0.001)
            x = [PortInfo(**i) for i in x]
            return x

        except TimeoutError:
            print(traceback.format_exc())
            self.worker.terminate()
            self.worker.kill()
            workers.do(self.worker.wait)
            raise

    def __del__(self):
        if self.worker:
            self.worker.terminate()
            self.worker.kill()
            workers.do(self.worker.wait)

    def onPortRegistered(self, name, is_input, shortname, is_audio, registered):
        def f():
            try:
                global realConnections
                "Same function for register and unregister"
                # if not port:
                #     return

                p = PortInfo(name, is_input, shortname, is_audio)

                if registered:
                    # log.debug("JACK port registered: "+port.name)
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

        self.ended = True
        if not self.worker.poll() is None:
            return
        try:
            x = self.rpc.call("close")
            self.rpc.stopFlag = True
        except Exception:
            self.rpc.stopFlag = True
            self.worker.terminate()
            self.worker.kill()
            workers.do(self.worker.wait)
            raise

    def __init__(self, *a, **k):
        # -*- coding: utf-8 -*-
        # If del can't find this it would to an infinite loop
        self.worker = None

        from .jsonrpyc import RPC
        from subprocess import PIPE, STDOUT, Popen
        self.ended = False
        f = os.path.join(os.path.dirname(os.path.abspath(
            __file__)), "jack_client_subprocess.py")
        env = {}
        env.update(os.environ)

        # Always use installed version.
        # TODO this will cause using the old one
        # if the new one isn't there, but is needed
        # for nixos et al compatibility
        if which("kaithem._jackmanager_server"):
            self.worker = Popen(["kaithem._jackmanager_server"],
                                stdout=PIPE, stdin=PIPE, stderr=STDOUT, env=env)
        else:
            self.worker = Popen(["python3", f], stdout=PIPE,
                                stdin=PIPE, stderr=STDOUT, env=env)
        self.rpc = RPC(target=self, stdin=self.worker.stdout,
                       stdout=self.worker.stdin, daemon=True)
        self.rpc.call("init")

    def print(self, s):
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


# No other lock should ever be gotten under this, to ensure anti deadlock ordering.

# This also protects the list of connections.  There is a theoretical race condition currently,
# Siomeone else could disconnect a port right as we connect it, and we currently mark things connected by ourselves
# without waiting for jack to tell us, to avoid double connects if at all possible on the "Don't touch the scary server" principle.

# However, in basically all intended use cases there will never be any external things changing anything around, other than manual users who can quicky fix au
# misconnections.
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


ensureConnectionsQueued = [0]


def _ensureConnections(*a, **k):
    "Auto restore connections in the connection list"

    # Someone else is already gonna run this
    # It is ok to have excess runs, but there must always be atleast 1 run after every change
    if ensureConnectionsQueued[0]:
        return
    ensureConnectionsQueued[0] = 1

    try:
        with lock:
            # Avoid race conditions, set flag BEFORE we check.
            # So we can't miss anything.  The other way would cause them to think we would check,
            # so they exit, but actually we already did.
            ensureConnectionsQueued[0] = 0
            x = list(allConnections.keys())
        for i in x:
            try:
                allConnections[i].reconnect()
            except KeyError:
                pass
            except Exception:
                print(traceback.format_exc())
    except Exception:
        ensureConnectionsQueued[0] = 0
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
        global realConnections, _realConnections
        with portsListLock:
            _realConnections = pl
            realConnections = _realConnections.copy()


errlog = []


latestAirWireForGivenPair = weakref.WeakValueDictionary()


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
        self.tupleid = (orig, to)
        latestAirWireForGivenPair[self.tupleid] = self

    def disconnect(self, force=True):
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

        # outPorts = _jackclient.get_ports(f+":*",is_output=True,is_audio=True)
        # inPorts = _jackclient.get_ports(t+":*",is_input=True,is_audio=True)
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

    def disconnect(self, force=True):
        check_exclude()

        if hasattr(self, "noNeedToDisconnect"):
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
                    t = t[:-1]

                if f.endswith("*"):
                    f = f[:-1]

                outPorts = []
                inPorts = []
                with portsListLock:
                    for i in portsList:
                        if i.startswith(f + ":"):
                            if portsList[i].is_output and portsList[i].is_audio:
                                outPorts.append(i)
                        if i.startswith(t):
                            if portsList[i].is_input and portsList[i].is_audio:
                                inPorts.append(i)

                # Connect all the ports
                for i in outPorts:
                    for j in inPorts:
                        if not isConnected(i, j):
                            connect(i, j)

            finally:
                lock.release()

    def disconnect(self, force=False):
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
                    t = t[:-1]

                if f.endswith("*"):
                    f = f[:-1]

                outPorts = []
                inPorts = []
                with portsListLock:
                    for i in portsList:
                        if i.startswith(f + ":"):
                            if portsList[i].is_output and portsList[i].is_audio:
                                outPorts.append(i)
                        if i.startswith(t):
                            if portsList[i].is_input and portsList[i].is_audio:
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


def work():
    global _reconnecterThreadObjectStopper

    # Wait 10s before actually doing anything to avoid nuisiance chattering errors.
    # This thread mostly only fixes crashed stuff.
    for i in range(100):
        if not _reconnecterThreadObjectStopper[0]:
            return
        time.sleep(0.1)

    failcounter = 0
    while (_reconnecterThreadObjectStopper[0]):
        try:
            # The _checkJack stuf won't block, because we already have the lock
            if lock.acquire(timeout=2):
                failcounter = 0
                try:
                    _checkJackClient()
                finally:
                    lock.release()
                # _ensureConnections()
            else:
                if (_reconnecterThreadObjectStopper[0]):
                    raise RuntimeError("Could not get lock,retrying in 5s")

                else:
                    # Already stopping anyway, ignore
                    pass
            time.sleep(5)
        except Exception:
            time.sleep(30)
            logging.exception("Error in jack manager")


_reconnecterThreadObject = None
_reconnecterThreadObjectStopper = [0]


def startManaging(p=None, n=None):
    "Start mananaging JACK in whatever way was configured."

    global _jackclient
    global _reconnecterThreadObject

    with lock:

        try:
            _jackclient = JackClientProxy()
        except Exception:
            log.exception("Error creating JACK client, retry later")

        try:
            findReal()
        except:
            pass


        # Stop the old thread if needed
        _reconnecterThreadObjectStopper[0] = 0
        try:
            if _reconnecterThreadObject:
                _reconnecterThreadObject.join()
        except Exception:
            pass

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

postedCheck = False

firstConnect = False


def _checkJackClient(err=True):
    global _jackclient, realConnections, postedCheck, firstConnect
    import jack
    if lock.acquire(timeout=10):
        try:

            t = _jackclient.get_ports()

            if not t:
                if firstConnect:
                    raise RuntimeError(
                        "JACK Server not started or client not connected, will try connect ")
                firstConnect = True

            if not postedCheck:
                postedCheck = True
                messagebus.postMessage("/system/jack/started", "")

            return True
        except Exception:
            postedCheck = False

            if firstConnect:
                print(traceback.format_exc())
                firstConnect = True

            print("Remaking client")
            print(traceback.format_exc())
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
    global portsList, _jackclient, lastCheckedClientFromGetPorts

    if lock.acquire(timeout=maxWait):
        try:
            if not _jackclient:
                # MOstly here so we can use this standalone from a unit test
                if (lastCheckedClientFromGetPorts < time.monotonic() - 120):
                    lastCheckedClientFromGetPorts = time.monotonic()
                    workers.do(_checkJackClient)
                return []
            ports = []
            x = _jackclient.get_ports(*a, **k)

            with portsListLock:
                # No filters means this must be the full list
                if not a and not k:
                    portsList.clear()
                for port in x:
                    portsList[port.name] = port

            return x
        finally:
            lock.release()
    return []


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
        pass


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
        pass


exclude_until = [0]



def check_exclude():
    if time.monotonic() < exclude_until[0]:
        raise RuntimeError("That is not allowed, trying to auto-fix")


def disconnect(f, t):
    global realConnections
    if lock.acquire(timeout=30):
        try:
            if not isConnected(f, t):
                return

            try:
                if isinstance(f, PortInfo):
                    f = f.name
                if isinstance(t, PortInfo):
                    t = t.name

                # This feels race conditionful but i think it is important so that we don't try to double-disconnect.
                # Be defensive with jack, the whole thing seems britttle
                  # Let other side handle figuring out which is which
                for i in range(24):
                    # For unknown reasons it is possible to completely clog up the jack client.
                    # We must make a new one and retry should this ever happen
                    try:
                        _jackclient.disconnect(f, t, timeout=5)
                        break
                    except TimeoutError:
                        if (i % 6) == 5:
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
        lpass

# This is an easy place to get a bazillion sounds queued up all waiting on the lock. This stops that.
awaiting = [0]
awaitingLock = threading.Lock()


def connect(f, t, ts=None):
    ts = ts or time.monotonic()

    global realConnections, _jackclient
    check_exclude()
    with awaitingLock:
        if awaiting[0] > 8:
            time.sleep(1)

        if awaiting[0] > 12:
            raise RuntimeError(
                "Too many threads are waiting to make JACK connections")

        awaiting[0] += 1

    try:
        if lock.acquire(timeout=10):
            try:
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
                    # Let other side handle figuring out which is which
                    for i in range(3):
                        # For unknown reasons it is possible to completely clog up the jack client.
                        # We must make a new one and retry should this ever happen
                        try:
                            _jackclient.connect(t, f, timeout=10)
                            break
                        except TimeoutError:
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
            pass
    finally:
        with awaitingLock:
            awaiting[0] -= 1
