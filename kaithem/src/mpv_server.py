from thirdparty import jsonrpyc
import mpv



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
while 1:
    time.sleep(5)