from mako.lookup import TemplateLookup
from src import devices, alerts, scheduling, messagebus, workers
import subprocess
import os
import mako
import time
import threading
import logging
import weakref
import base64
import traceback
import shutil
import socket
import uuid

from src import widgets

logger = logging.Logger("plugins.dlnarender")

templateGetter = TemplateLookup(os.path.dirname(__file__))


defaultSubclassCode = """
class CustomDeviceType(DeviceType):
    pass
"""


class DLNARenderAgent(devices.Device):
    deviceTypeName = 'DLNARenderAgent'
    readme = os.path.join(os.path.dirname(__file__), "README.md")
    defaultSubclassCode = defaultSubclassCode
    description ="Create an instance of gmediarender to recieve media. Audio is piped to JACK."
    def close(self):
        devices.Device.close(self)
        try:
            with self.plock:
                self.closed = True
                self.process.terminate()
        except:
            print(traceback.format_exc())

    def __del__(self):
        self.close()

    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)
        self.closed = False
        self.plock = threading.RLock()
        try:

            def f(*a):
                with self.plock:
                    if self.closed:
                        return
                    x = ['gmediarender', '--gstout-videosink', 'glimagesink', '--gstout-audiopipe',
                         'jackaudiosink slave-method=0 port-pattern="jkhjkjhkhkhkhkjhk" client-name='+data.get("device.advertiseName", 'DLNA')]

                    x += ['-f', data.get("device.advertiseName",
                                         socket.gethostname()) or socket.gethostname()]
                    x += ['-u', data.get("device.uuid",
                                         str(uuid.uuid4())) or str(uuid.uuid4())]

                    self.process = subprocess.Popen(x)
            self.restart = f

            messagebus.subscribe("/system/jack/started", f)

            f()
        except:
            self.handleException()

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["DLNARenderAgent"] = DLNARenderAgent
