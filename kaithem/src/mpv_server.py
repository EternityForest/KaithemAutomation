from thirdparty import jsonrpyc
from thirdparty import python_mpv_jsonipc as mpv

import os
import sys
import time

ppid = os.getppid()


# https://stackoverflow.com/questions/568271/how-to-check-if-there-exists-a-process-with-a-given-pid-in-python
def check_pid(pid):
    """Check For the existence of a unix pid."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True


class Proxy:
    def __init__(self, obj):
        self.obj = obj

    def call(self, m, *a):
        return getattr(self.obj, m)(*a)

    def get(self, m):
        return getattr(self.obj, m)

    def set(self, m, v):
        return setattr(self.obj, m, v)


mpv = mpv.MPV()
p = Proxy(mpv)

rpc = jsonrpyc.RPC(target=p)


while not rpc.threadStopped:
    time.sleep(10)
    if not check_pid(ppid):
        sys.exit()
