from thirdparty import jsonrpyc
import python_mpv_jsonipc as mpv

import os
import sys

ppid = os.getppid()


#https://stackoverflow.com/questions/568271/how-to-check-if-there-exists-a-process-with-a-given-pid-in-python
def check_pid(pid):        
    """ Check For the existence of a unix pid. """
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True


class proxy():
    def call(self,m,*a):
        return getattr(self.obj,m)(*a)
    def get(self,m):
        return getattr(self.obj,m)
    def set(self,m,v):
        return setattr(self.obj,m,v)
p=proxy()
mpv=mpv.MPV()
p.obj=mpv

rpc = jsonrpyc.RPC(target=p)
import time


while not rpc.threadStopped:
    time.sleep(10)
    if not check_pid(ppid):
        sys.exit()