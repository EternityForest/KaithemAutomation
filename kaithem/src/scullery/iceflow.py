import threading, os, weakref
from .jsonrpyc import RPC
from subprocess import PIPE, STDOUT
from subprocess import Popen
from . import workers


def stop_allJackUsers():
    # No longer needed, occasional subprocess segfaults stay contained
    pass


import os

import base64

import functools
import sys
import os
import time


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


# Can't pass GST elements, have to pass IDs
class eprox:
    def __init__(self, parent, id) -> None:
        # This was making a bad GC loop issue.
        self.parent = weakref.ref(parent)
        self.id = id

    def set_property(self, p, v, maxWait=10):
        self.parent().setProperty(self.id, p, v, maxWait=maxWait)

    def pullBuffer(self, timeout=0.1):
        return base64.b64decode(self.parent().pullBuffer(self.id, timeout))

    def pullToFile(self, f):
        return self.parent().pullToFile(self.id, f)


pipes = weakref.WeakValueDictionary()


class GStreamerPipeline:
    def __getattr__(self, attr):
        if self.ended or not self.worker.poll() is None:
            raise RuntimeError("This process is already dead")

        def f(*a, **k):
            try:
                return self.rpc.call(attr, args=a, kwargs=k, block=0.001, timeout=15)
            except Exception:
                self.worker.terminate()
                self.worker.kill()
                workers.do(self.worker.wait)
                raise

        return f

    def pullToFile(self, *a, **k):
        if self.ended or not self.worker.poll() is None:
            raise RuntimeError("This process is already dead")

        try:
            return self.rpc.call(
                "pullToFile", args=a, kwargs=k, block=0.001, timeout=0.5
            )
        except Exception:
            self.worker.terminate()
            self.worker.kill()
            workers.do(self.worker.wait)
            raise

    def __del__(self):
        self.worker.terminate()
        self.worker.kill()
        workers.do(self.worker.wait)

    def addElement(self, *a, **k):
        # This has to do with setup and I suppose we probably shouldn't just let the error pass by.
        if self.ended or not self.worker.poll() is None:
            raise RuntimeError("This process is already dead")

        for i in k:
            if isinstance(k[i], eprox):
                k[i] = k[i].id

        if "connectToOutput" in k and isinstance(k["connectToOutput"], (list, tuple)):
            k["connectToOutput"] = [
                (i.id if isinstance(i, eprox) else i) for i in k["connectToOutput"]
            ]
        return eprox(
            self,
            self.rpc.call(
                "addElementRemote", args=a, kwargs=k, block=0.0001, timeout=5
            ),
        )

    def setProperty(self, *a, maxWait=10, **k):
        # Probably Just Not Important enough to raise an error for this.
        if self.ended or not self.worker.poll() is None:
            print("Prop set in dead process")
            self.ended = True
            return
        for i in k:
            if isinstance(k[i], eprox):
                k[i] = k[i].id
        a = [i.id if isinstance(i, eprox) else i for i in a]
        return eprox(
            self,
            self.rpc.call(
                "setProperty", args=a, kwargs=k, block=0.0001, timeout=maxWait
            ),
        )

    def addPILCapture(self, *a, **k):
        # Probably Just Not Important enough to raise an error for this.
        if self.ended or not self.worker.poll() is None:
            print("Prop set in dead process")
            self.ended = True
            return
        return eprox(
            self,
            self.rpc.call(
                "addRemotePILCapture", args=a, kwargs=k, block=0.0001, timeout=10
            ),
        )

    def onAppsinkData(self, elementName, data, *a, **k):
        return

    def _onAppsinkData(self, elementName, data):
        self.onAppsinkData(elementName, base64.b64decode(data))

    def onMotionBegin(self, *a, **k):
        print("Motion start")

    def onMotionEnd(self, *a, **k):
        print("Motion end")

    def onMultiFileSinkFile(self, fn, *a, **k):
        print("MultiFileSink", fn)

    def onBarcode(self, type, data):
        print("Barcode: ", type, data)

    def stop(self):
        if self.ended:
            return

        self.ended = True
        if not self.worker.poll() is None:
            self.rpc.stopFlag = True
            self.ended = True
            return
        try:
            x = self.rpc.call("stop", block=0.01, timeout=10)
            self.rpc.stopFlag = True
            self.worker.terminate()
            time.sleep(0.5)
            self.worker.kill()

        except Exception:
            self.rpc.stopFlag = True
            self.worker.terminate()
            time.sleep(0.5)
            self.worker.kill()
            workers.do(self.worker.wait)
            

    def addJackMixerSendElements(self, *a, **k):
        a, b = self.rpc.call(
            "addJackMixerSendElements", args=a, kwargs=k, block=0.0001, timeout=10
        )
        return (eprox(self, a), eprox(self, b))

    def __init__(self, *a, **k):
        # -*- coding: utf-8 -*-

        # If del can't find this it would to an infinite loop
        self.worker = None

        pipes[id(self)] = self
        self.ended = False
        f = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "iceflow_server.py"
        )
        # Unusued, the lock is for compatibility wiith the old not-rpc based iceflow
        self.lock = threading.RLock()
        env = {}
        env.update(os.environ)
        env["GST_DEBUG"] = "*:1"

        self.rpc = None
        if which("kaithem._iceflow_server") and False:
            self.worker = Popen(
                ["kaithem._iceflow_server"],
                stdout=PIPE,
                stdin=PIPE,
                stderr=STDOUT,
                env=env,
            )
        else:
            self.worker = Popen(
                ["python3", f], stdout=PIPE, stdin=PIPE, stderr=STDOUT, env=env
            )

        self.rpc = RPC(
            target=self, stdin=self.worker.stdout, stdout=self.worker.stdin, daemon=True
        )
        # We have no way of knowing when it's actually ready and listening for commands if gstreamer
        # needs to load
        time.sleep(1)

    def print(self, s):
        print(s)

    def onPresenceValue(self, v):
        print(v)


GstreamerPipeline = GStreamerPipeline
