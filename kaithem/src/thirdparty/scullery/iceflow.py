

import threading,os,weakref



def stopAllJackUsers():
    #No longer needed, occasional subprocess segfaults stay contained
    pass
import os

#Can't pass GST elements, have to pass IDs
class eprox():
    def __init__(self,parent,id) -> None:
        self.parent=parent
        self.id=id

    def set_property(self,p,v):
        self.parent.setProperty(self.id,p,v)

pipes = weakref.WeakValueDictionary()

class GStreamerPipeline():
    def __getattr__(self,attr):
        if  self.ended or not self.worker.poll() is None:
            raise RuntimeError("This process is already dead")
        def f(*a,**k):
            try:
                return self.rpc.call(attr,args=a,kwargs=k,block=0.001)
            except:
                self.worker.kill()
                raise

        return f 

    def __del__(self):
        self.worker.kill()

    def addElement(self,*a,**k):
        if self.ended or not self.worker.poll() is None:
            raise RuntimeError("This process is already dead")
        for i in k:
            if isinstance(k[i],eprox):
                k[i]=k[i].id
        return eprox(self,self.rpc.call("addElementRemote",args=a,kwargs=k,block=0.0001))

    def setProperty(self,*a,**k):
        if  self.ended or not self.worker.poll() is None:
            raise RuntimeError("This process is already dead")
        for i in k:
            if isinstance(k[i],eprox):
                k[i]=k[i].id
        a = [i.id if isinstance(i,eprox) else i for i in a]
        return eprox(self,self.rpc.call("setProperty",args=a,kwargs=k,block=0.0001))


    def stop(self):
        if self.ended:
            return
            
        self.ended=True
        if not self.worker.poll() is None:
            return
        try:
            return self.rpc.call("stop")
        except:
            self.worker.kill()
            raise

    def addJackMixerSendElements(self, *a,**k):
       a,b= self.rpc.call('addJackMixerSendElements',args=a,kwargs=k,block=0.0001)
       return(eprox(self,a),eprox(self,b))

    def __init__(self, *a,**k):
        # -*- coding: utf-8 -*-
        from jsonrpyc import RPC
        from subprocess import Popen, PIPE, STDOUT
        pipes[id(self)]=self
        self.ended=False
        f = os.path.join(os.path.dirname(os.path.abspath(__file__)),"iceflow_server.py")
        #Unusued, the lock is for compatibility wiith the old not-rpc based iceflow
        self.lock=threading.RLock()
        env={}
        env.update(os.environ)
        env['GST_DEBUG']='0'

        self.worker = Popen(['python3', f], stdout=PIPE, stdin=PIPE, stderr=STDOUT, env=env)
        self.rpc = RPC(target=self,stdin=self.worker.stdout, stdout=self.worker.stdin)

    def print(self,s):
        print(s)

GstreamerPipeline=GStreamerPipeline
