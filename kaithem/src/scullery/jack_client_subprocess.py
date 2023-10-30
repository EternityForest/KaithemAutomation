
_didPatch = False
import jack
import re
import time

# This is NixOS compatibility stuff, we could be running as an output from setup.py
# Or we could be running directly with python3 file.py
try:
    from . import jsonrpyc
except ImportError:
    import jsonrpyc


import traceback
import weakref
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


def portToInfo(p):
    return PortInfo(p.name, p.is_input, p.shortname, p.is_audio, list(p.aliases))


import threading
lock = threading.Lock()


def f():
    global _didPatch
    if True:
        if not _didPatch:
            def _get_ports_fix(self, name_pattern='', is_audio=False, is_midi=False,
                               is_input=False, is_output=False, is_physical=False,
                               can_monitor=False, is_terminal=False):
                if name_pattern:
                    re.compile(name_pattern)

                return jack.Client._get_ports(self, name_pattern, is_audio, is_midi,
                                              is_input, is_output, is_physical,
                                              can_monitor, is_terminal)

            jack.Client._get_ports = jack.Client.get_ports
            jack.Client.get_ports = _get_ports_fix
            _didPatch = True


f()


# We can't ship port objects on the wire, we have to do this instead.
# Anything that would normally take a port object must take a name instead.
class JackClientProxy():
    def __getattr__(self, attr):
        def f(*a, **k):
            x = getattr(self.clientObj, attr)(*a, **k)
            if isinstance(x, jack.Port):
                x = portToInfo(x).toDict()
            return x
        return f

    def get_ports(self, *a, **k):
        x = self.clientObj.get_ports(*a, **k)
        x = [portToInfo(i).toDict() for i in x]
        return x

    def get_all_connections(self, p):
        p = self.clientObj.get_port_by_name(p)
        x = self.clientObj.get_all_connections(p)
        x = [portToInfo(i).toDict() for i in x]
        return x

    def init(self, *a, **k):
        self.clientObj = jack.Client(
            "Overseer" + str(time.monotonic()), no_start_server=True)
        self.clientObj.set_port_connect_callback(onPortConnect)
        self.clientObj.set_port_registration_callback(
            onPortRegistered, only_available=False)
        self.clientObj.activate()

    def __init__(self) -> None:
        self.clientObj = None

    def disconnect(self, f, t):
        global realConnections
        if lock.acquire(timeout=30):

            try:
                f = self.clientObj.get_port_by_name(f)
                t = self.clientObj.get_port_by_name(t)
            except jack.JackError:
                return

            try:
                if not self.clientObj:
                    return
                try:
                    # This feels race conditionful but i think it is important so that we don't try to double-disconnect.
                    # Be defensive with jack, the whole thing seems britttle
                    self.clientObj.disconnect(f, t)

                except Exception:
                    pass
            finally:
                lock.release()

    def connect(self, f, t):
        global realConnections
        if lock.acquire(timeout=10):
            try:
                if not self.clientObj:
                    return

                # Ignore the nuisance of no longer existing ports. Airwires will get them if they come back.
                try:
                    f = self.clientObj.get_port_by_name(f)
                    t = self.clientObj.get_port_by_name(t)
                except jack.JackError:
                    return

                f_input = f.is_input

                if f.is_input:
                    if not t.is_output:
                        # Do a retry, there seems to be a bug somewhere
                        try:
                            f = self.clientObj.get_port_by_name(f.name)
                            t = self.clientObj.get_port_by_name(t.name)
                        except Exception:
                            return
                        if f.is_input:
                            if not t.is_output:
                                raise ValueError(
                                    "Cannot connect two inputs", str((f, t)))
                else:
                    if t.is_output:
                        raise ValueError(
                            "Cannot connect two outputs", str((f, t)))
                f = f.name
                t = t.name
                try:
                    if f_input:
                        self.clientObj.connect(t, f)
                    else:
                        self.clientObj.connect(f, t)
                except Exception:
                    print(traceback.format_exc())
            finally:
                lock.release()


def onPortRegistered(port, registered):
    if not port:
        return
    try:
        rpc.call('onPortRegistered', [port.name, port.is_input,
                 port.shortname, port.is_audio, registered])
    except Exception:
        print(traceback.format_exc())
        raise


def onPortConnect(a, b, c):
    rpc.call("onPortConnected", [a.is_output, a.name, b.name, c])


jackclient = None
rpc = None


def main():
    global jackclient
    global rpc
    jackclient = JackClientProxy()

    rpc = jsonrpyc.RPC(jackclient)

    import os
    import sys

    ppid = os.getppid()

    # https://stackoverflow.com/questions/568271/how-to-check-if-there-exists-a-process-with-a-given-pid-in-python
    def check_pid(pid):
        """ Check For the existence of a unix pid. """
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        else:
            return True

    while 1:
        time.sleep(10)
        if not check_pid(ppid):
            sys.exit()
        if not ppid == os.getppid():
            sys.exit()


if __name__ == '__main__':
    main()
