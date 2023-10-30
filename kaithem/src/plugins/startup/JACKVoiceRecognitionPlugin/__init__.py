from mako.lookup import TemplateLookup
from kaithem.src import devices, alerts, scheduling, messagebus, workers
from kaithem.src.scullery import iceflow,workers
import os
import mako
import time
import threading
import logging
import weakref
import base64
import traceback
import shutil

from kaithem.src import widgets

logger = logging.Logger("plugins.voice")

templateGetter = TemplateLookup(os.path.dirname(__file__))

try:
    shutil.rmtree("/dev/shm/kaithem_voice_keyword_files")
except:
    pass

try:
    shutil.rmtree("/dev/shm/kaithem_voice_dict_files")
except:
    pass


class JackVoicePipeline(iceflow.GStreamerPipeline):
    def __init__(self, name, keywords='',dictionary=''):
        iceflow.GStreamerPipeline.__init__(self, name)

        if keywords:
            v = keywords.replace("\r",'').split("\n")
            with open("/dev/shm/kaithem_kw_file_"+name, 'w') as f:
                for i in v:
                    f.write(i.strip() + ("/1e-20/" if not "/" in i else '')+"\n")


        if dictionary:
            v = keywords.replace("\r",'')
            with open("/dev/shm/kaithem_dict_file_"+name, 'w') as f:
                f.write(v)

        self.src = self.addElement("jackaudiosrc", buffer_time=10, latency_time=10,
                                   port_pattern="fgfcghfhftyrtw5ew453xvrt", client_name=name+"_in", connect=0)

        self.capsfilter = self.addElement(
            "capsfilter", caps="audio/x-raw,channels="+str(1))
        self.cnv = self.addElement("audioconvert")
        self.rs = self.addElement("audioresample")
        self.q = self.addElement("queue")

        self.pocketsphinx = self.addElement(
            "pocketsphinx", 
            kws=("/dev/shm/kaithem_kw_file_"+name) if keywords else None,
            dict=("/dev/shm/kaithem_dict_file_"+name) if dictionary else '/usr/share/pocketsphinx/model/en-us/cmudict-en-us.dict',
            )
   
        self.addElement("fakesink", sync=False)

    def on_message(self, bus, message, userdata):
        s = message.get_structure()
        if not s:
            return True
        msgtype = s.get_name()

        # Speech recognition, forward it on to the message bus.
        if msgtype == 'pocketsphinx':
            if message.get_structure().get_value('hypothesis'):
                messagebus.postMessage("/devices/"+self.name+"/hypothesis",
                                       (message.get_structure().get_value('hypothesis'),))

            if message.get_structure().get_value('final'):
                self.controller().print(str((message.get_structure().get_value(
                    'hypothesis'), message.get_structure().get_value('confidence'))))
                messagebus.postMessage("/devices/"+self.name+"/final",
                                       (message.get_structure().get_value('hypothesis'), message.get_structure().get_value('confidence')))
        return True

class VoiceRecognition(devices.Device):
    deviceTypeName = 'VoiceRecognition'
    readme = os.path.join(os.path.dirname(__file__), "README.md")

    def close(self):
        devices.Device.close(self)
        try:
            self.ps.stop()
        except:
            pass

    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)
        try:
            self.ps = JackVoicePipeline(name,data.get("device.keywords","hello\nworld"))
            self.ps.controller = weakref.ref(self)
            def f():
                try:
                    self.ps.start(timeout=60)
                except:
                    self.handleException()
            workers.do(f)
        except:
            self.handleException()


    # @staticmethod
    # def getCreateForm():
    #     return templateGetter.get_template("createform_gateway.html").render()

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["VoiceRecognition"] = VoiceRecognition
