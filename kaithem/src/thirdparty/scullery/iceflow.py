

import threading,os,weakref

from . import workers

def stopAllJackUsers():
    #No longer needed, occasional subprocess segfaults stay contained
    pass
import os

import base64

#Can't pass GST elements, have to pass IDs
class eprox():
    def __init__(self,parent,id) -> None:
        #This was making a bad GC loop issue.
        self.parent=weakref.ref(parent)
        self.id=id

    def set_property(self,p,v,maxWait=10):
        self.parent().setProperty(self.id,p,v,maxWait=maxWait)

    def pullBuffer(self,element,timeout=0.1):
        return base64.b64decode(self.parent().pullBuffer(self.id, timeout))



pipes = weakref.WeakValueDictionary()

class GStreamerPipeline():
    def __getattr__(self,attr):
        if  self.ended or not self.worker.poll() is None:
            raise RuntimeError("This process is already dead")
        def f(*a,**k):
            try:
                return self.rpc.call(attr,args=a,kwargs=k,block=0.001)
            except Exception:
                self.worker.kill()
                workers.do(self.worker.wait)
                raise

        return f 

    def __del__(self):
        self.worker.kill()
        workers.do(self.worker.wait)


    def addElement(self,*a,**k):

        #This has to do with setup and I suppose we probably shouldn't just let the error pass by.
        if self.ended or not self.worker.poll() is None:
            raise RuntimeError("This process is already dead")

        for i in k:
            if isinstance(k[i],eprox):
                k[i]=k[i].id

        if 'connectToOutput' in k and isinstance(k['connectToOutput'],(list,tuple)):
            k['connectToOutput'] = [(i.id if isinstance(i, eprox) else i) for i in k['connectToOutput'] ]
        return eprox(self,self.rpc.call("addElementRemote",args=a,kwargs=k,block=0.0001))

    def setProperty(self,*a,maxWait=10,**k):

        #Probably Just Not Important enough to raise an error for this.
        if  self.ended or not self.worker.poll() is None:
            print("Prop set in dead process")
            self.ended=True
            return
        for i in k:
            if isinstance(k[i],eprox):
                k[i]=k[i].id
        a = [i.id if isinstance(i,eprox) else i for i in a]
        return eprox(self,self.rpc.call("setProperty",args=a,kwargs=k,block=0.0001,timeout=maxWait))

    def onAppsinkData(self,elementName,data,*a,**k):
        return
    def _onAppsinkData(self,elementName,data):
        self.onAppsinkData(elementName,base64.b64decode(data))


    def onMotionBegin(self,*a,**k):
        print("Motion start")

    def onMotionEnd(self,*a,**k):
        print("Motion end")


    def onBarcode(self,type, data):
        print("Barcode: ", type, data)
        
    def stop(self):
        if self.ended:
            return
            
        self.ended=True
        if not self.worker.poll() is None:
            self.rpc.stopFlag=True
            self.ended=True
            return
        try:
            x=self.rpc.call("stop")
            self.rpc.stopFlag=True
            self.worker.kill()

        except Exception:
            self.rpc.stopFlag=True
            self.worker.kill()
            workers.do(self.worker.wait)
            raise

    def addJackMixerSendElements(self, *a,**k):
       a,b= self.rpc.call('addJackMixerSendElements',args=a,kwargs=k,block=0.0001)
       return(eprox(self,a),eprox(self,b))

    def __init__(self, *a,**k):
        # -*- coding: utf-8 -*-

        #If del can't find this it would to an infinite loop
        self.worker = None


        from scullery.jsonrpyc import RPC
        from subprocess import PIPE, STDOUT
        from reap import Popen
        pipes[id(self)]=self
        self.ended=False
        f = os.path.join(os.path.dirname(os.path.abspath(__file__)),"iceflow_server.py")
        #Unusued, the lock is for compatibility wiith the old not-rpc based iceflow
        self.lock=threading.RLock()
        env={}
        env.update(os.environ)
        env['GST_DEBUG']='3'


        self.rpc=None
        self.worker = Popen(['python3', f], stdout=PIPE, stdin=PIPE, stderr=STDOUT, env=env)
        self.rpc = RPC(target=self,stdin=self.worker.stdout, stdout=self.worker.stdin,daemon=True)

    def print(self,s):
        print(s)

GstreamerPipeline=GStreamerPipeline
