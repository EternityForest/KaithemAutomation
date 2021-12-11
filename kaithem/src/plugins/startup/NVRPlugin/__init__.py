from mako.lookup import TemplateLookup
from src import tagpoints
from src import devices, alerts, scheduling, messagebus, workers
from scullery import iceflow, workers,sip
import os
import mako
import time
import threading
import logging 
import weakref
import base64
import traceback
import shutil
import reap

from src import widgets, pages

logger = logging.Logger("plugins.nvr")

templateGetter = TemplateLookup(os.path.dirname(__file__))


defaultSubclassCode = """
class CustomDeviceType(DeviceType):
    def onIncomingCall(self,number):
        # Uncomment to accept all incoming calls
        # self.accept()
        pass
"""


#Make a GST launch string
def getGstreamerSourceData(s):
    
    #The source is an HLS stream
    if s.endswith(".m3u8"):
        s= "souphttpsrc location="+s+" ! hlsdemux ! tsdemux ! parsebin"

    #Make a video test src just for this purpose
    if not s:
        s = "videotestsrc is-live=true ! video/x-raw, format=I420, width=320, height=240 ! videoconvert ! x264enc ! h264parse"  


    #Make a video test src just for this purpose
    if s=="test":
        s = "videotestsrc pattern=checkers-8 is-live=true ! video/x-raw, format=I420, width=240, height=160 ! videoconvert ! x264enc ! h264parse"  

    if s=="webcam":
        s="v4l2src ! videoconvert ! queue ! x264enc tune=zerolatency sliced-threads=true  ! h264parse"

    #Tested
    #rtspsrc location=rtsp://192.168.1.6:8080/h264_pcm.sdp latency=100 ! queue ! rtph264depay ! h264parse

    return s  

    
mediaFolders = weakref.WeakValueDictionary()


from src import kaithemobj

class NVRPlugin(devices.Device):
    deviceTypeName = 'NVRPlugin'
    readme = os.path.join(os.path.dirname(__file__), "README.md")
    defaultSubclassCode = defaultSubclassCode

    def close(self):
        devices.Device.close(self)
        try:
            self.process.kill()
        except:
            print(traceback.format_exc())

        try:
            shutil.rmtree("/dev/shm/knvr/"+self.name)
        except:
            pass

        try:
            self.checker.unregister()
        except:
            logger.exception("Unregistering")
    def __del__(self):
        self.close()


    def connect(self):
        if time.monotonic()-self.lastStart<15:
            return
        self.lastStart=time.monotonic()
        try:
            os.makedirs("/dev/shm/knvr/"+self.name)
        except:
            pass


        try:
            os.chmod("/dev/shm/knvr/"+self.name,0o755)
        except:
            pass


        #Exec is needed so we can kill it
        self.process = reap.Popen("exec gst-launch-1.0 -q "+getGstreamerSourceData(self.data.get('device.source','')) +"! hlssink2 location="+ os.path.join("/dev/shm/knvr/",self.name,r"segment%05d.ts")+" playlist-location="+os.path.join("/dev/shm/knvr/",self.name,'playlist.m3u8')+" target-duration=1",shell=True)


    def check(self):
        with self.streamLock:
            if self.process and self.process.poll() is None:
                self.tagpoints['running'].value=1
                return
            else:
                self.tagpoints['running'].value=0

                if self.tagpoints['streamOn'].value:
                    self.connect()

    def commandState(self,v,t,a):
        with self.streamLock:
            if not v:
                if self.process:
                        self.process.kill()
            else:
                self.check()






    def webHandler(self,*path,**kwargs):
        if path[0]=="live":
            pages.require("users.nvr.view")
            kaithemobj.kaithem.web.serveFile(os.path.join("/dev/shm/knvr/",self.name,*(path[1:])))



    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)
        try:
            self.tagpoints['streamOn']= tagpoints.Tag("/devices/"+self.name+".streamOn")
            self.tagpoints['streamOn'].default = 1
            self.tagpoints['streamOn'].subscribe(self.commandState)
            
            self.tagpoints['running']= tagpoints.Tag("/devices/"+self.name+".running")

            self.streamLock = threading.RLock()
            self.lastStart =0

            mediaFolders[name]=self


            self.connect()
            self.check()
            from src import scheduling
            self.checker = scheduling.scheduler.every(self.check,5)


        except:
            self.handleException()


    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["NVRPlugin"] = NVRPlugin
